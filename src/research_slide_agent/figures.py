"""Figure numbers in captions: readers must be able to find each cropped figure in the paper."""

from __future__ import annotations

import json
import re

# "Fig. 7(b)", "Figure 3", "Table 2", "図3", "表 1", optionally "Fig. 7(a)–(c)".
FIGURE_NUMBER = re.compile(
    r"(?:Fig(?:ure)?s?\.?|Table|Algorithm|図|表)\s*[A-Z]?\d+[a-z]?(?:\s*\([a-z](?:\s*[-–,]\s*[a-z])?\))?",
    re.IGNORECASE,
)


def figure_number(text: str) -> str | None:
    match = FIGURE_NUMBER.search(text or "")
    return match.group(0).strip() if match else None


def _prefix_in_paragraphs(paragraphs, old, new):
    """Replace the caption inside an explicit 図題 replacement; False when it is split across runs."""
    for paragraph in paragraphs:
        if old in (paragraph.text or ""):
            paragraph.text = paragraph.text.replace(old, new, 1)
            return True
        for run in paragraph.runs:
            if old in run.text:
                run.text = run.text.replace(old, new, 1)
                return True
    return False


def number_captions(spec, sources) -> list[dict]:
    """Require a paper figure/table number on every image cropped from a PDF.

    The number may come from the caption itself or from the citation locator for that image
    (e.g. "p.5 Fig.7(a)"); in the latter case the caption is prefixed in place. Uploaded photos
    that are not PDF crops are left alone. Returns what was added, for save feedback.
    """
    from .store import StateError

    added = []
    for slide in spec.slides:
        for image in slide.image_references:
            origin = sources.get(image.source_id, {}).get("origin")
            if not origin or json.loads(origin).get("operation") != "pdf_crop_v1":
                continue
            if figure_number(image.caption):
                continue
            locators = [c.source.locator for c in slide.citations if c.target_id == image.id]
            number = next((n for n in map(figure_number, locators) if n), None)
            if not number:
                raise StateError(
                    f"FIGURE_NUMBER_REQUIRED: slide {slide.slide_id} image {image.id}: put the paper's figure "
                    "or table number (e.g. Fig. 3, Table 2) in the caption or in its citation locator")
            caption = f"{number} {image.caption}"
            explicit = slide.replacements.get("図題")
            if explicit and not _prefix_in_paragraphs(explicit, image.caption, caption):
                raise StateError(
                    f"FIGURE_NUMBER_REQUIRED: slide {slide.slide_id} image {image.id}: write {number} into the "
                    "caption; the 図題 text does not contain the caption as one run")
            image.caption = caption
            added.append({"slide_id": slide.slide_id, "image_id": image.id, "caption": caption})
    return added
