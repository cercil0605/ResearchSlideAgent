"""Fewer and smaller LLM round trips: rules in parts, compact save feedback, slide patches, waiting jobs."""

from __future__ import annotations

import re
import time

from .paper import estimate_tokens
from .rules import authoring_context

RULE_PART_TOKENS = 18_000  # below common MCP client output limits (Claude Code: about 25k tokens)
GENERATION_WAIT_SECONDS = 120
PREVIEW_WAIT_SECONDS = 180
ISSUE_KEYS = ("missing_page_roles", "inherited_headings", "shared_content_targets", "fit_problems")


def _chunks(document):
    """Split one long document at level-2 headings so each piece fits a part."""
    text = document["text"]
    if estimate_tokens(text) <= RULE_PART_TOKENS:
        return [document]
    sections = re.split(r"(?m)^(?=## )", text)
    pieces, current = [], ""
    for section in sections:
        if current and estimate_tokens(current + section) > RULE_PART_TOKENS:
            pieces.append(current)
            current = ""
        current += section
    pieces.append(current)
    return [{**document, "text": piece, "piece": f"{i}/{len(pieces)}"} for i, piece in enumerate(pieces, 1)]


def rule_parts():
    context = authoring_context()
    parts, current, used = [], [], 0
    for document in context["documents"]:
        for piece in _chunks(document):
            cost = estimate_tokens(piece["text"]) + 50
            if current and used + cost > RULE_PART_TOKENS:
                parts.append(current)
                current, used = [], 0
            current.append(piece)
            used += cost
    parts.append(current)
    return context, parts


def authoring_context_part(part: int = 1) -> dict:
    from .store import StateError

    context, parts = rule_parts()
    if not 1 <= part <= len(parts):
        raise StateError(f"PART_INVALID: use 1..{len(parts)}")
    return {**{k: v for k, v in context.items() if k != "documents"},
            "part": part, "parts": len(parts), "next_part": part + 1 if part < len(parts) else None,
            "documents": parts[part - 1]}


def compact_feedback(feedback: dict, changed: set[str] | None = None, detail: bool = False) -> dict:
    """Keep only pages that need attention; the LLM already has the text it just sent."""
    warnings = [w for w in feedback["warnings"] if changed is None or w["slide_id"] in changed]
    warned = {w["slide_id"] for w in warnings}
    pages = []
    considered = [p for p in feedback["pages"] if changed is None or p["slide_id"] in changed]
    for page in considered:
        if detail:
            pages.append(page)
            continue
        issues = {k: page[k] for k in ISSUE_KEYS if page.get(k)}
        if issues or page["slide_id"] in warned:
            pages.append({"slide_id": page["slide_id"], "page": page["page"], "title": page["title"], **issues})
    rest = {k: v for k, v in feedback.items() if k not in {"pages", "warnings"}}
    if not detail:
        # Identical guidance repeats for every page with the same code; send it once per code. A code whose
        # guidance differs between pages (it names another slide, or a different remedy) keeps it per warning.
        texts = {}
        for warning in warnings:
            texts.setdefault(warning["code"], set()).add(warning.get("guidance"))
        shared = {code: next(iter(found)) for code, found in texts.items() if len(found) == 1 and None not in found}
        warnings = [{k: v for k, v in w.items() if not (k == "guidance" and w["code"] in shared)} for w in warnings]
        rest["guidance"] = shared
    return {**rest, "pages": pages, "warnings": warnings, "pages_checked": len(considered),
            "pages_without_issues": len(considered) - len({p["slide_id"] for p in pages} | warned)
            if not detail else None}


def merge_slides(current: dict | None, slides: list[dict], remove_ids: list[str], expected_version: int):
    """Apply slide replacements, insertions and removals to the saved spec.

    A patched slide's slide_order is its final position (moved or inserted there); the unchanged slides
    keep their relative order around it, and the order is renumbered from 1.
    """
    from .models import Slide, SlideSpec
    from .store import StateError

    if not current:
        raise StateError("SPEC_REQUIRED: save the whole spec once with save_slide_spec")
    if not slides and not remove_ids:
        raise StateError("PATCH_EMPTY: give slides or remove_slide_ids")
    patched = [Slide.model_validate(slide).model_dump() for slide in slides]
    ids = [s["slide_id"] for s in patched]
    if len(ids) != len(set(ids)) or set(ids) & set(remove_ids):
        raise StateError("PATCH_DUPLICATE_SLIDE_ID")
    existing = {s["slide_id"] for s in current["slides"]}
    if set(remove_ids) - existing:
        raise StateError(f"SLIDE_NOT_FOUND: {sorted(set(remove_ids) - existing)}")
    keep = sorted((s for s in current["slides"] if s["slide_id"] not in set(ids) | set(remove_ids)),
                  key=lambda s: s["slide_order"])
    total = len(keep) + len(patched)
    # Each patched slide's slide_order is its final position; unchanged slides fill the rest in order.
    positions = {}
    for slide in sorted(patched, key=lambda s: s["slide_order"]):
        position = min(max(slide["slide_order"], 1), total)
        while position in positions:
            position += 1
        if position > total:
            position = max(p for p in range(1, total + 1) if p not in positions)
        positions[position] = slide
    unchanged = iter(keep)
    merged = [{**(positions[n] if n in positions else next(unchanged)), "slide_order": n}
              for n in range(1, total + 1)]
    spec = SlideSpec.model_validate({**current, "spec_version": expected_version + 1, "slides": merged})
    return spec, set(ids)


def wait_for(fetch, seconds: float, interval: float = 0.5):
    """Poll a job until it settles or the wait ends; the caller reports a still-running job."""
    deadline = time.monotonic() + seconds
    while True:
        job = fetch()
        if job["state"] in {"completed", "failed"} or time.monotonic() >= deadline:
            return job
        time.sleep(interval)
