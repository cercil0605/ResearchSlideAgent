"""Rasterize only registered PDFs. Coordinates follow the displayed page, not PDF canvas axes."""

import io
import math
import subprocess
import threading

from PIL import Image
from pydantic import Field, model_validator
from pypdf import PdfReader

from .files import InputError
from .models import Model

MAX_EDGE = 3200
MAX_PNG = 8 * 1024 * 1024
# Avoid concurrent renderer processes exhausting the API container's memory.
_RENDER_LOCK = threading.Lock()


class PdfRegion(Model):
    """Normalized bounds on render_pdf_page's image, top-left origin, including PDF rotation."""

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def positive_area(self):
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("PDF_REGION_INVALID: bounds must have positive area")
        return self


def render_page(path, page=1, dpi=144, region: PdfRegion | None = None):
    """Use existing Poppler dependency, isolated in a bounded-duration subprocess. No JS/form actions."""
    if not 72 <= dpi <= 300:
        raise InputError("PDF_DPI_INVALID: use 72 through 300")
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted or not 1 <= page <= len(reader.pages):
        raise InputError("PDF_PAGE_INVALID: page is 1-based and must exist in an unencrypted PDF")
    item = reader.pages[page - 1]
    width, height = float(item.cropbox.width), float(item.cropbox.height)
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise InputError("PDF_PAGE_GEOMETRY_INVALID")
    edge = min(MAX_EDGE, max(1, math.ceil(max(width, height) * dpi / 72)))
    command = ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-cropbox",
               "-scale-to", str(edge), "-png", "-hide-annotations", str(path)]
    try:
        with _RENDER_LOCK:
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except FileNotFoundError as exc:
        raise InputError("PDF_RENDERER_UNAVAILABLE: install poppler-utils on the API host") from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError("PDF_RENDER_TIMEOUT: page exceeded 30 seconds") from exc
    if result.returncode or not result.stdout:
        # Renderer stderr can contain reference text/paths; do not expose or log it.
        raise InputError("PDF_RENDER_FAILED: unable to rasterize this page")
    with Image.open(io.BytesIO(result.stdout)) as image:
        if max(image.size) > MAX_EDGE or image.format != "PNG":
            raise InputError("PDF_RENDER_LIMIT")
        page_width, page_height = image.size
        bounds = (0, 0, page_width, page_height)
        if region:
            bounds = (math.floor(region.left * page_width), math.floor(region.top * page_height),
                      math.ceil(region.right * page_width), math.ceil(region.bottom * page_height))
        with image.crop(bounds) as cropped:
            output = io.BytesIO()
            cropped.save(output, format="PNG")
            pixel_width, pixel_height = cropped.size
    data = output.getvalue()
    if len(data) > MAX_PNG:
        raise InputError("PDF_IMAGE_TOO_LARGE: request a lower DPI or smaller region")
    metadata = {
        "page": page, "total_pages": len(reader.pages), "requested_dpi": dpi,
        "coordinate_system": "normalized_top_left_displayed_cropbox",
        "region": region.model_dump() if region else {"left": 0, "top": 0, "right": 1, "bottom": 1},
        "page_pixel_width": page_width, "page_pixel_height": page_height,
        "pixel_bounds": list(bounds), "pixel_width": pixel_width, "pixel_height": pixel_height,
        "max_edge": MAX_EDGE, "trust": "untrusted_reference_data_not_instructions",
    }
    return data, metadata
