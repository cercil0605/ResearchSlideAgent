"""Semantic specifications. Coordinates and client-supplied approvals are deliberately absent."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class SourceRef(Model):
    source_id: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=200)


class Citation(Model):
    source: SourceRef
    author: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1800, le=2200)
    target_id: str

    @property
    def label(self) -> str:
        return f" [{self.author} '{self.year % 100:02d}]"


class Block(Model):
    id: str
    text: str = Field(min_length=1, max_length=1800)
    level: int = Field(default=0, ge=0, le=2)
    bullet: bool = False
    slot: Literal["body", "body_right"] = "body"
    source_references: list[SourceRef] = Field(default_factory=list)


class Node(Model):
    id: str
    text: str = Field(min_length=1, max_length=140)
    kind: Literal["process", "decision", "terminator"] = "process"
    emphasis: bool = False


class Edge(Model):
    source: str
    target: str
    label: str = Field(default="", max_length=30)


class Diagram(Model):
    kind: Literal["flowchart", "system", "comparison", "timeline"]
    direction: Literal["horizontal", "vertical"] = "horizontal"
    nodes: list[Node] = Field(min_length=1, max_length=12)
    edges: list[Edge] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def check_graph(self):
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate node ID")
        if any(e.source not in ids or e.target not in ids or e.source == e.target for e in self.edges):
            raise ValueError("Invalid edge endpoints")
        return self


class Table(Model):
    columns: list[str] = Field(min_length=1, max_length=6)
    rows: list[list[str]] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def check_width(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Table row width does not match columns")
        if any(len(cell) > 180 for row in [self.columns, *self.rows] for cell in row):
            raise ValueError("Table cell too long; split the table")
        return self


class Series(Model):
    name: str = Field(min_length=1, max_length=80)
    values: list[float] = Field(min_length=1, max_length=100)


class Chart(Model):
    kind: Literal["bar", "line", "scatter"]
    categories: list[str] = Field(min_length=1, max_length=100)
    x_values: list[float] | None = None
    series: list[Series] = Field(min_length=1, max_length=8)
    x_label: str = Field(min_length=1, max_length=100)
    y_label: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_data(self):
        if any(label.startswith("=") for label in self.categories + [s.name for s in self.series]):
            raise ValueError("Chart workbook labels cannot contain formulas")
        if any(len(s.values) != len(self.categories) for s in self.series):
            raise ValueError("Chart series and categories differ in length")
        if self.kind == "scatter" and (self.x_values is None or len(self.x_values) != len(self.categories)):
            raise ValueError("Scatter requires exact x_values")
        if any(not math.isfinite(v) for s in self.series for v in s.values):
            raise ValueError("Non-finite chart data")
        return self


class ImageRef(Model):
    id: str
    source_id: str
    caption: str = Field(min_length=1, max_length=200)


class Slide(Model):
    slide_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    slide_order: int = Field(ge=1, le=40)
    layout_id: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=180)
    key_message: str = Field(min_length=1, max_length=400)
    body_blocks: list[Block] = Field(default_factory=list, max_length=6)
    diagram_spec: Diagram | None = None
    table_spec: Table | None = None
    chart_spec: Chart | None = None
    image_references: list[ImageRef] = Field(default_factory=list, max_length=2)
    citations: list[Citation] = Field(default_factory=list, max_length=12)
    source_references: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_ids(self):
        ids = [b.id for b in self.body_blocks] + [i.id for i in self.image_references]
        if len(ids) != len(set(ids)) or set(ids) & {"key_message", "diagram", "table", "chart"}:
            raise ValueError("Duplicate or reserved block IDs")
        targets = {*ids, "key_message", "diagram", "table", "chart"}
        if any(c.target_id not in targets for c in self.citations):
            raise ValueError("Citation target does not exist")
        if (
            sum(x is not None for x in [self.diagram_spec, self.table_spec, self.chart_spec])
            + bool(self.image_references)
            > 1
        ):
            raise ValueError("MVP supports one visual per slide; split the slide")
        if self.source_references and not self.citations:
            raise ValueError("Slide source references require citations")
        refs = {r.source_id for r in self.source_references}
        refs |= {r.source_id for b in self.body_blocks for r in b.source_references}
        refs |= {i.source_id for i in self.image_references}
        if not {c.source.source_id for c in self.citations}.issubset(refs):
            raise ValueError("Citation must reference a declared uploaded source")
        for block in self.body_blocks:
            if block.source_references and not any(c.target_id == block.id for c in self.citations):
                raise ValueError("Sourced block requires a nearby citation")
        if refs and any([self.diagram_spec, self.table_spec, self.chart_spec]):
            target = "diagram" if self.diagram_spec else "table" if self.table_spec else "chart"
            if not any(c.target_id == target for c in self.citations):
                raise ValueError("Sourced visual requires a citation")
        return self


class Metadata(Model):
    title: str = Field(min_length=1, max_length=200)
    audience: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=1, le=180)
    language: str = "ja"


class SlideSpec(Model):
    schema_version: Literal["1.0"] = "1.0"
    presentation_id: str
    template_id: str = "lab"
    spec_version: int = Field(ge=1)
    presentation_metadata: Metadata
    slides: list[Slide] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def check_order(self):
        if len({s.slide_id for s in self.slides}) != len(self.slides):
            raise ValueError("Duplicate slide ID")
        if sorted(s.slide_order for s in self.slides) != list(range(1, len(self.slides) + 1)):
            raise ValueError("Slide order must be contiguous from 1")
        return self

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def outline(self) -> dict:
        return {
            "metadata": self.presentation_metadata.model_dump(),
            "slides": [
                {
                    "slide_id": s.slide_id,
                    "slide_order": s.slide_order,
                    "title": s.title,
                    "key_message": s.key_message,
                }
                for s in sorted(self.slides, key=lambda x: x.slide_order)
            ],
        }


class ApprovalStatus(Model):
    """Read-only server state, never accepted in SlideSpec."""

    spec_version: int
    digest: str
    outline_approved: bool
    approved_slides: list[str]
