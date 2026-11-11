"""Demonstration plan schema (plan.json).

A plan is a list of scenes. Each scene has narration (spoken in the cloned
voice) and browser actions that run *while* the narration plays. A scene lasts
max(actions, narration) + pad, so the voice is never cut off and the screen
never races ahead of the explanation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destructive: bool = Field(
        False,
        description="Marks irreversible actions (delete, purchase, deploy). "
        "Recording refuses to run these without --allow-destructive.",
    )
    note: str | None = None


class Goto(_Base):
    type: Literal["goto"]
    url: str


class Click(_Base):
    type: Literal["click"]
    selector: str


class TypeText(_Base):
    type: Literal["type"]
    selector: str
    text: str | None = None
    secret_env: str | None = Field(
        None, description="Read the text from this env var; it is never logged."
    )
    delay_ms: int = 55
    clear: bool = True

    @model_validator(mode="after")
    def _one_source(self):
        if (self.text is None) == (self.secret_env is None):
            raise ValueError("type action needs exactly one of 'text' or 'secret_env'")
        return self


class Press(_Base):
    type: Literal["press"]
    key: str
    selector: str | None = None


class Hover(_Base):
    type: Literal["hover"]
    selector: str
    ms: int = 600


class Scroll(_Base):
    type: Literal["scroll"]
    selector: str | None = Field(None, description="Scroll this element into view")
    y: int | None = Field(None, description="Or scroll the page by this many pixels")
    ms: int = 900

    @model_validator(mode="after")
    def _one_target(self):
        if (self.selector is None) == (self.y is None):
            raise ValueError("scroll action needs exactly one of 'selector' or 'y'")
        return self


class Select(_Base):
    type: Literal["select"]
    selector: str
    value: str


class Wait(_Base):
    type: Literal["wait"]
    ms: int


class WaitFor(_Base):
    type: Literal["wait_for"]
    selector: str | None = None
    url_contains: str | None = None
    timeout_ms: int = 15000


class Highlight(_Base):
    type: Literal["highlight"]
    selector: str
    ms: int = 1500


class Title(_Base):
    type: Literal["title"]
    heading: str
    subheading: str | None = None


Action = Annotated[
    Union[Goto, Click, TypeText, Press, Hover, Scroll, Select, Wait, WaitFor, Highlight, Title],
    Field(discriminator="type"),
]


class Expect(BaseModel):
    """Completion criteria checked at the end of a scene. A failed check aborts
    the recording, so a broken demo is never presented as finished."""

    model_config = ConfigDict(extra="forbid")
    selector_visible: str | None = None
    text_visible: str | None = None
    url_contains: str | None = None


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str | None = None
    narration: str
    actions: list[Action] = Field(default_factory=list)
    expect: Expect | None = None
    pad_after_s: float = Field(0.6, ge=0, le=10)
    min_duration_s: float = Field(0, ge=0)
    lead_in_s: float = Field(
        0.3, ge=0, le=10, description="Delay between scene start and first action"
    )

    @field_validator("id")
    @classmethod
    def _safe_id(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError("scene id must be alphanumeric, '-' or '_'")
        return v

    @field_validator("narration")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("narration must not be empty")
        return v.strip()


class Viewport(BaseModel):
    width: int = 1920
    height: int = 1080


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    slug: str
    goal: str | None = None
    audience: str | None = None
    viewport: Viewport = Field(default_factory=Viewport)
    redact: list[str] = Field(
        default_factory=list, description="CSS selectors blurred throughout the recording"
    )
    approved: bool = Field(
        False, description="Set true only after the user approved the plan. "
        "Recording refuses unapproved plans."
    )
    scenes: list[Scene]

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", v):
            raise ValueError("slug must be lowercase letters, digits and '-'")
        return v

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [s.id for s in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene ids must be unique")
        if not self.scenes:
            raise ValueError("plan needs at least one scene")
        return self

    def destructive_actions(self) -> list[tuple[str, str]]:
        return [
            (s.id, a.type)
            for s in self.scenes
            for a in s.actions
            if a.destructive
        ]

    def secret_envs(self) -> list[str]:
        return [
            a.secret_env
            for s in self.scenes
            for a in s.actions
            if isinstance(a, TypeText) and a.secret_env
        ]


def load_plan(path: Path) -> Plan:
    return Plan.model_validate(json.loads(Path(path).read_text()))
