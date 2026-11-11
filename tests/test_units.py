import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from loom.captions import build_cues, chunk_text, parse_srt, to_srt
from loom.config import Settings
from loom.plan import Plan
from loom.recorder import RecordingError, preflight
from loom.tts import TTSError, fish_tts, synthesize


def plan_dict(**kw):
    d = {"title": "T", "slug": "t", "approved": True,
         "scenes": [{"id": "01", "narration": "Hello there.", "actions": []}]}
    d.update(kw)
    return d


# -- plan --------------------------------------------------------------------

def test_plan_parses_all_action_types():
    p = Plan.model_validate(plan_dict(scenes=[{"id": "a", "narration": "x", "actions": [
        {"type": "goto", "url": "https://example.com"},
        {"type": "click", "selector": "#b"},
        {"type": "type", "selector": "#i", "text": "hi"},
        {"type": "type", "selector": "#p", "secret_env": "PW"},
        {"type": "press", "key": "Enter"},
        {"type": "hover", "selector": "#h"},
        {"type": "scroll", "y": 400},
        {"type": "select", "selector": "#s", "value": "v"},
        {"type": "wait", "ms": 100},
        {"type": "wait_for", "selector": "#w"},
        {"type": "highlight", "selector": "#x"},
        {"type": "title", "heading": "H"},
    ]}]))
    assert len(p.scenes[0].actions) == 12
    assert p.secret_envs() == ["PW"]


@pytest.mark.parametrize("bad", [
    {"slug": "Bad Slug"},
    {"scenes": []},
    {"scenes": [{"id": "1", "narration": "  "}]},
    {"scenes": [{"id": "1", "narration": "a"}, {"id": "1", "narration": "b"}]},
    {"scenes": [{"id": "1", "narration": "a", "actions": [{"type": "type", "selector": "#i"}]}]},
    {"scenes": [{"id": "1", "narration": "a", "actions": [{"type": "teleport"}]}]},
    {"unknown_field": 1},
])
def test_plan_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        Plan.model_validate(plan_dict(**bad))


# -- safeguards --------------------------------------------------------------

def test_preflight_requires_approval():
    p = Plan.model_validate(plan_dict(approved=False))
    with pytest.raises(RecordingError, match="not approved"):
        preflight(p, {"01": 1.0}, False)


def test_preflight_blocks_destructive_without_flag():
    p = Plan.model_validate(plan_dict(scenes=[{"id": "01", "narration": "x", "actions": [
        {"type": "click", "selector": "#delete", "destructive": True}]}]))
    with pytest.raises(RecordingError, match="destructive"):
        preflight(p, {"01": 1.0}, False)
    preflight(p, {"01": 1.0}, True)


def test_preflight_requires_narration_and_secrets(monkeypatch):
    p = Plan.model_validate(plan_dict(scenes=[{"id": "01", "narration": "x", "actions": [
        {"type": "type", "selector": "#p", "secret_env": "LOOM_TEST_SECRET"}]}]))
    with pytest.raises(RecordingError, match="no narration"):
        preflight(p, {}, False)
    monkeypatch.delenv("LOOM_TEST_SECRET", raising=False)
    with pytest.raises(RecordingError, match="secret"):
        preflight(p, {"01": 1.0}, False)


# -- captions ----------------------------------------------------------------

def test_chunk_text_respects_length_and_keeps_words():
    text = ("First, open the AWS Management Console, then navigate to the EC2 dashboard, "
            "where every running instance in the selected region is listed. Done.")
    chunks = chunk_text(text)
    assert all(len(c) <= 84 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_cues_cover_narration_duration_and_roundtrip():
    cues = build_cues([(0.0, 4.0, "One. Two three."), (5.0, 2.0, "Four.")])
    assert cues[0][0] == 0.0 and abs(cues[1][1] - 4.0) < 1e-9
    assert cues[2][0] == 5.0 and abs(cues[2][1] - 7.0) < 1e-9
    parsed = parse_srt(to_srt(cues))
    assert [c[2] for c in parsed] == ["One.", "Two three.", "Four."]
    assert abs(parsed[-1][1] - 7.0) < 0.002


# -- tts ---------------------------------------------------------------------

def test_synthesize_caches_by_text(tmp_path):
    s = Settings(tts_provider="silent")
    out = tmp_path / "01.wav"
    m1 = synthesize("one two three four five six", out, s)
    assert not m1["cached"] and m1["duration"] > 1
    assert synthesize("one two three four five six", out, s)["cached"]
    assert not synthesize("different text now", out, s)["cached"]


def test_fish_requires_credentials(tmp_path):
    with pytest.raises(TTSError, match="FISH_API_KEY"):
        fish_tts("hi", tmp_path / "x.wav", Settings())


def test_fish_request_shape_and_auth_error(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["model"] = req.headers["model"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(401, json={"status": 401, "message": "Invalid api key"})

    s = Settings(fish_api_key="k", fish_reference_id="voice123", fish_model="s2.1-pro")
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(TTSError, match="401.*Invalid api key"):
            fish_tts("Hello", tmp_path / "x.wav", s, client=c)
    assert seen["auth"] == "Bearer k" and seen["model"] == "s2.1-pro"
    assert seen["body"]["reference_id"] == "voice123"
    assert seen["body"]["format"] == "wav" and seen["body"]["text"] == "Hello"


def test_fish_success_writes_normalised_wav(tmp_path):
    # produce a real wav to serve as the "API response"
    src = tmp_path / "src.wav"
    synthesize("a b c d e", src, Settings(tts_provider="silent"))
    payload = src.read_bytes()
    s = Settings(fish_api_key="k", fish_reference_id="v")
    with httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=payload))) as c:
        fish_tts("Hello", tmp_path / "out.wav", s, client=c)
    assert (tmp_path / "out.wav").stat().st_size > 1000
