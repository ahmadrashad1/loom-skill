"""End-to-end: plan → silent narration → Playwright recording → render → verify."""

import json
from pathlib import Path

import pytest

from loom.config import Settings
from loom.plan import Plan
from loom.recorder import RecordingError, record
from loom.renderer import render
from loom.tts import synthesize
from loom.verify import verify

APP = (Path(__file__).parent / "fixtures" / "demo_app.html").resolve().as_uri()


def make_plan(expect_text: str) -> Plan:
    return Plan.model_validate({
        "title": "E2E", "slug": "e2e", "approved": True, "redact": [".api-key"],
        "scenes": [
            {"id": "01", "narration": "Welcome to the test.",
             "actions": [{"type": "title", "heading": "E2E"}]},
            {"id": "02", "narration": "Now we add a task to the list and check it appears.",
             "actions": [{"type": "goto", "url": APP},
                         {"type": "type", "selector": "#task", "text": "Ship it", "delay_ms": 10},
                         {"type": "click", "selector": "#add"}],
             "expect": {"text_visible": expect_text}},
        ]})


def voice(plan, d, s):
    return {sc.id: synthesize(sc.narration, d / "narration" / f"{sc.id}.wav", s)["duration"]
            for sc in plan.scenes}


@pytest.mark.slow
def test_full_pipeline(tmp_path):
    s = Settings(tts_provider="silent", preset="ultrafast")
    plan = make_plan("Ship it")
    (tmp_path / "plan.json").write_text(plan.model_dump_json())
    tl = record(plan, voice(plan, tmp_path, s), tmp_path, s)
    assert tl["status"] == "ok" and [x["id"] for x in tl["scenes"]] == ["01", "02"]
    render(plan, tmp_path, s)
    rep = verify(plan, tmp_path, s)
    failed = [c for c in rep["checks"] if not c["ok"] and not c["warn_only"]]
    assert rep["passed"], failed
    assert (tmp_path / "raw" / "recording.webm").exists()
    assert len(rep["thumbnails"]) == 2


@pytest.mark.slow
def test_failed_expectation_aborts_and_blocks_render(tmp_path):
    s = Settings(tts_provider="silent")
    plan = make_plan("This text never appears")
    with pytest.raises(RecordingError, match="scene 02"):
        record(plan, voice(plan, tmp_path, s), tmp_path, s)
    tl = json.loads((tmp_path / "raw" / "timeline.json").read_text())
    assert tl["status"] == "failed"
    assert (tmp_path / "raw" / "failure-02.png").exists()
    from loom.renderer import RenderError
    with pytest.raises(RenderError):
        render(plan, tmp_path, s)
