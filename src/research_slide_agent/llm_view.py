"""Compact views of server data for the LLM. Generation keeps reading the full profile.

The template profile stores raw run properties (style_xml), shape geometry and package
parts so the engine can clone pages. A spec only names slots, paragraph indices and, for
paragraphs that mix styles, style_run indices. Everything else is dropped here so the model
does not reread tens of thousands of characters of XML on every turn.
"""

from __future__ import annotations

import re
from typing import Any

from .engine import template_info as _full_template_info

_DROP_SLOT_KEYS = {"shape_id", "box"}
_DROP_PROTOTYPE_KEYS = {"part"}
_VOLATILE = re.compile(r'\s(?:dirty|err|smtClean)="[^"]*"')


def describe_style(style_xml: str | None) -> str:
    """Summarize run properties as size, weight and color, e.g. '26pt bold #000000'."""
    if not style_xml:
        return "inherited"
    head = style_xml.split(">", 1)[0]
    parts = []
    if size := re.search(r'\bsz="(\d+)"', head):
        parts.append(f"{int(size.group(1)) / 100:g}pt")
    if re.search(r'\bb="1"', head):
        parts.append("bold")
    if re.search(r'\bi="1"', head):
        parts.append("italic")
    if re.search(r'\bu="(?!none)[^"]+"', head):
        parts.append("underline")
    if color := re.search(r'<a:solidFill><a:srgbClr val="([0-9A-Fa-f]{6})"', style_xml):
        parts.append("#" + color.group(1).upper())
    elif scheme := re.search(r'<a:solidFill><a:schemeClr val="(\w+)"', style_xml):
        parts.append(scheme.group(1))
    return " ".join(parts) or "inherited"


def _paragraph(paragraph: dict) -> dict:
    runs = paragraph.get("runs") or []
    compact = {k: v for k, v in paragraph.items() if k != "runs"}
    signatures = {_VOLATILE.sub("", r.get("style_xml") or "") for r in runs}
    if len(signatures) > 1:
        # Mixed styles: the spec must pick style_run indices, so keep them with a readable label.
        compact["runs"] = [{"index": r["index"], "example": r["example"],
                            "style": describe_style(r.get("style_xml"))} for r in runs]
    elif runs:
        compact["style"] = describe_style(runs[0].get("style_xml"))
    return compact


def _slot(slot: dict) -> dict:
    compact = {k: v for k, v in slot.items() if k not in _DROP_SLOT_KEYS and k != "paragraphs"}
    if "paragraphs" in slot:
        compact["paragraphs"] = [_paragraph(p) for p in slot["paragraphs"]]
    return compact


def compact_template_info(info: dict[str, Any]) -> dict[str, Any]:
    """Keep every key the spec needs; replace raw style XML with short labels."""
    prototypes = []
    for prototype in info.get("prototypes", []):
        entry = {k: v for k, v in prototype.items() if k not in _DROP_PROTOTYPE_KEYS and k != "slots"}
        if "slots" in prototype:
            entry["slots"] = [_slot(s) for s in prototype["slots"]]
        prototypes.append(entry)
    return {**info, "prototypes": prototypes}


def template_info(path) -> dict[str, Any]:
    """The template catalog as the LLM sees it via get_template_info."""
    return compact_template_info(_full_template_info(path))
