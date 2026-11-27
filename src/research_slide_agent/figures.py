"""Figure numbers in captions: readers must be able to find each cropped figure in the paper."""

from __future__ import annotations

import json
import re

# "Fig. 7(b)", "Figure 3", "Figure 2.1", "Table 2", "図3", "表 1", optionally "Fig. 7(a)–(c)".
FIGURE_NUMBER = re.compile(
    r"(?:Fig(?:ure)?s?\.?|Table|Algorithm|図|表)\s*[A-Z]?\d+(?:\.\d+)*[a-z]?(?:\s*\([a-z](?:\s*[-–,]\s*[a-z])?\))?",
    re.IGNORECASE,
)


CAPTION_LIMIT = 200  # ImageRef.caption max_length


def figure_number(text: str) -> str | None:
    match = FIGURE_NUMBER.search(text or "")
    return match.group(0).strip() if match else None


class _CaptionText:
    """Walk the explicit 図題 text in order, so each image's caption is matched once, left to right."""

    def __init__(self, paragraphs):
        self.pieces = []
        for paragraph in paragraphs:
            if paragraph.text:
                self.pieces.append((paragraph, "text"))
            self.pieces.extend((run, "text") for run in paragraph.runs)
        self.cursor = (0, 0)

    def find(self, caption, replacement=None):
        index, offset = self.cursor
        for i in range(index, len(self.pieces)):
            owner, attr = self.pieces[i]
            text = getattr(owner, attr)
            at = text.find(caption, offset if i == index else 0)
            if at < 0:
                continue
            new = replacement if replacement is not None else caption
            setattr(owner, attr, text[:at] + new + text[at + len(caption):])
            self.cursor = (i, at + len(new))
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
        explicit = slide.replacements.get("図題")
        text = _CaptionText(explicit) if explicit else None
        for image in slide.image_references:
            origin = sources.get(image.source_id, {}).get("origin")
            if not origin or json.loads(origin).get("operation") != "pdf_crop_v1":
                if text:
                    text.find(image.caption)  # an uploaded photo's caption still occupies its place
                continue
            if figure_number(image.caption):
                if text:
                    text.find(image.caption)  # keep the walk in step with already-numbered captions
                continue
            locators = [c.source.locator for c in slide.citations if c.target_id == image.id]
            number = next((n for n in map(figure_number, locators) if n), None)
            if not number:
                raise StateError(
                    f"FIGURE_NUMBER_REQUIRED: slide {slide.slide_id} image {image.id}: put the paper's figure "
                    "or table number (e.g. Fig. 3, Table 2) in the caption or in its citation locator")
            caption = f"{number} {image.caption}"
            if len(caption) > CAPTION_LIMIT:
                raise StateError(
                    f"FIGURE_NUMBER_REQUIRED: slide {slide.slide_id} image {image.id}: adding {number} makes the "
                    f"caption longer than {CAPTION_LIMIT} characters; shorten it and include the number")
            if text and not text.find(image.caption, caption):
                raise StateError(
                    f"FIGURE_NUMBER_REQUIRED: slide {slide.slide_id} image {image.id}: write {number} into the "
                    "caption; the 図題 text does not contain the caption as one run")
            image.caption = caption
            added.append({"slide_id": slide.slide_id, "image_id": image.id, "caption": caption})
    return added
