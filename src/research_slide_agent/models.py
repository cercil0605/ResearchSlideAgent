"""Semantic specifications. Coordinates and client-supplied approvals are deliberately absent."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RESEARCH_CONTENT_ROLES = {
    "overview": {"purpose", "approach", "result"},
    "background": {"problem", "context"},
    "related": {"purpose", "approach", "result", "gap"},
    "objective": {"purpose", "approach", "novelty"},
    "method": {"input", "process", "output"},
    "experiment": {"purpose", "conditions"},
    "results": {"result"},
    "discussion": {"achievement", "interpretation", "limitation"},
    "summary": {"purpose", "approach", "result", "future"},
}


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


class ImageRef(Model):
    id: str
    source_id: str
    caption: str = Field(min_length=1, max_length=200)


class PrototypeRun(Model):
    text: str = Field(min_length=1, max_length=1800)
    style_run: int = Field(default=0, ge=0)


class PrototypeParagraph(Model):
    """Select an existing paragraph/run style; clients cannot supply formatting."""

    prototype_paragraph: int = Field(default=0, ge=0)
    text: str = Field(default="", max_length=1800)
    runs: list[PrototypeRun] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def check_content(self):
        if bool(self.text) == bool(self.runs):
            raise ValueError("Specify either text or runs; use an empty paragraph list to clear a slot")
        return self


class Slide(Model):
    slide_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    slide_order: int = Field(ge=1, le=40)
    prototype_id: str = Field(min_length=1, max_length=80)
    section: Literal[
        "cover", "overview", "example", "background", "related", "objective", "method",
        "experiment", "metric", "results", "discussion", "summary",
    ]
    part: Literal["main", "appendix"] = "main"
    composition: Literal["canonical", "text_visual", "table_visual", "two_images"] = "canonical"
    paper_section: str = Field(default="", max_length=200)
    content_map: dict[Literal[
        "purpose", "approach", "novelty", "problem", "context", "gap", "input", "process", "output",
        "conditions", "metric", "result", "interpretation", "achievement", "limitation", "future",
    ], list[str]] = Field(default_factory=dict)
    replacements: dict[str, list[PrototypeParagraph]] = Field(default_factory=dict)
    title: str = Field(min_length=1, max_length=180)
    diagram_spec: Diagram | None = None
    table_spec: Table | None = None
    image_references: list[ImageRef] = Field(default_factory=list, max_length=2)
    citations: list[Citation] = Field(default_factory=list, max_length=12)
    source_references: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_ids(self):
        ids = [i.id for i in self.image_references]
        if len(ids) != len(set(ids)) or set(ids) & {"diagram", "table"}:
            raise ValueError("Duplicate or reserved block IDs")
        targets = {*ids, *self.replacements, "diagram", "table"}
        if any(c.target_id not in targets for c in self.citations):
            raise ValueError("Citation target does not exist")
        if (
            sum(x is not None for x in [self.diagram_spec, self.table_spec])
            + bool(self.image_references)
            > 1
        ) and self.composition != "table_visual":
            raise ValueError("Multiple evidence types require table_visual composition")
        if self.composition != "canonical" and self.prototype_id != "method":
            raise ValueError("Compositions use the method prototype and its original text styles")
        if self.composition == "table_visual" and (
            not self.table_spec or bool(self.diagram_spec) == bool(self.image_references)
        ):
            raise ValueError("table_visual requires a table and one diagram or original image")
        if self.composition == "two_images" and (
            len(self.image_references) != 2 or self.diagram_spec or self.table_spec
        ):
            raise ValueError("two_images requires exactly two original images")
        if self.composition != "two_images" and len(self.image_references) > 1:
            raise ValueError("Two original images require two_images composition")
        if self.composition == "text_visual" and (
            bool(self.diagram_spec) == bool(self.image_references) or self.table_spec
        ):
            raise ValueError("text_visual requires one diagram or original image")
        for role, slots in self.content_map.items():
            if not slots or len(slots) != len(set(slots)):
                raise ValueError(f"Content role {role} needs distinct nonempty content targets")
            for slot in slots:
                if slot == "table" and self.table_spec and any(any(row) for row in self.table_spec.rows):
                    continue
                paragraphs = self.replacements.get(slot, [])
                if not any(p.text or any(r.text for r in p.runs) for p in paragraphs):
                    raise ValueError(f"Content role {role} must point to populated content: {slot}")
        if self.source_references and not self.citations:
            raise ValueError("Slide source references require citations")
        refs = {r.source_id for r in self.source_references}
        refs |= {i.source_id for i in self.image_references}
        if not {c.source.source_id for c in self.citations}.issubset(refs):
            raise ValueError("Citation must reference a declared uploaded source")
        for image in self.image_references:
            if not any(c.target_id == image.id for c in self.citations):
                raise ValueError("Each image requires a citation targeting its image ID")
        for target, visual in {"diagram": self.diagram_spec, "table": self.table_spec}.items():
            if refs and visual and not any(c.target_id == target for c in self.citations):
                raise ValueError("Sourced visual requires a citation")
        return self


class Metadata(Model):
    title: str = Field(min_length=1, max_length=200)
    audience: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(ge=1, le=180)
    language: str = "ja"


class SlideSpec(Model):
    schema_version: Literal["1.3"] = "1.3"
    presentation_id: str
    template_id: str = "lab"
    purpose_mode: Literal["research", "general"] = "research"
    spec_version: int = Field(ge=1)
    presentation_metadata: Metadata
    slides: list[Slide] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def check_order(self):
        if len({s.slide_id for s in self.slides}) != len(self.slides):
            raise ValueError("Duplicate slide ID")
        if sorted(s.slide_order for s in self.slides) != list(range(1, len(self.slides) + 1)):
            raise ValueError("Slide order must be contiguous from 1")
        ordered = sorted(self.slides, key=lambda s: s.slide_order)
        if any((s.section == "cover") != (s.prototype_id == "cover") for s in ordered):
            raise ValueError("Cover sections use the cover prototype, which is reserved for covers")
        if any(a.part == "appendix" and b.part == "main" for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Appendices must follow the main presentation")
        if self.purpose_mode == "research":
            main = [s.section for s in ordered if s.part == "main"]
            required = {"cover", "overview", "background", "related", "objective", "method",
                        "experiment", "results", "discussion", "summary"}
            if not required.issubset(main):
                raise ValueError("Research main presentation needs all research sections")
            if not any(s.section == "results" and s.part == "main" and
                       (s.diagram_spec or s.table_spec or s.image_references) for s in ordered):
                raise ValueError("Research main presentation needs a result figure or table")
            if main[:2] != ["cover", "overview"] or main.count("cover") != 1 or main.count("overview") != 1:
                raise ValueError("Research main presentation starts with one cover and one overview")
            if main[-1] != "summary":
                raise ValueError("Research main presentation must end with a summary before appendices")
            if any(s.section in {"cover", "overview"} for s in ordered if s.part == "appendix"):
                raise ValueError("Appendices cannot contain a cover or overview")
            self.check_research_content(ordered)
        return self

    def check_research_content(self, ordered):
        main = [s for s in ordered if s.part == "main"]
        ranks = {name: i for i, name in enumerate([
            "cover", "overview", "background", "related", "objective", "method", "experiment",
            "metric", "results", "discussion", "summary",
        ])}
        previous = 0
        for slide in main:
            if slide.section == "example":
                if previous != ranks["method"]:
                    raise ValueError("Research examples belong in the method section after the objective")
                continue
            rank = ranks[slide.section]
            if rank < previous and not (slide.section == "experiment" and previous >= ranks["results"]):
                raise ValueError("Research sections must follow background, related, objective, method, experiments")
            previous = rank
        for slide in main:
            if slide.section != "cover" and (not slide.paper_section or not slide.content_map):
                raise ValueError("Research pages need a paper_section and content_map tied to displayed content")
        for section, roles in RESEARCH_CONTENT_ROLES.items():
            present = {role for s in main if s.section == section for role in s.content_map}
            if roles - present:
                raise ValueError(f"Missing {section} content roles: {', '.join(sorted(roles - present))}")
        if not any("metric" in s.content_map for s in main if s.section in {"experiment", "metric"}):
            raise ValueError("Experiments need a metric explained in experiment or metric pages")

    def digest(self) -> str:
        value = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def outline(self) -> dict:
        return {
            "metadata": self.presentation_metadata.model_dump(),
            "slides": [
                {
                    "slide_id": s.slide_id,
                    "slide_order": s.slide_order,
                    "title": s.title,
                    "paper_section": s.paper_section,
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
