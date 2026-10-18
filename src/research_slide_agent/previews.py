"""Queue isolated-worker previews and serve cached images; rendering is not visual review."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .engine import render
from .store import StateError

_RENDER_SLOT = threading.BoundedSemaphore(1)


def preview_files(store, owner, job_id, *, create=False, expected_sha=None):
    """Only the isolated worker calls create=True; the API reads completed render jobs."""
    job = store.job(owner, job_id)
    if job["state"] != "completed":
        if create:
            raise StateError("JOB_NOT_COMPLETED")
        return None
    output = json.loads(job["output"])
    pptx = (store.root / output["pptx"]).resolve()
    if not pptx.is_relative_to(store.root.resolve()):
        raise StateError("INVALID_OUTPUT_PATH")
    if create:
        from pptx import Presentation

        if not 1 <= len(Presentation(pptx).slides) <= 40:
            raise StateError("PREVIEW_PAGE_LIMIT: preview supports 1 to 40 pages; PPTX remains available")
    directory = pptx.parent / "preview"
    with pptx.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if expected_sha is not None and expected_sha != digest:
        raise StateError("PREVIEW_SOURCE_CHANGED")

    def cached():
        try:
            result = json.loads((directory / "preview.json").read_text())
            files = [result["pdf"], *result["images"]]
            if result["pptx_sha256"] == digest and all(
                Path(name).name == name and (directory / name).is_file() for name in files
            ):
                return result
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    result = cached()
    if not create:
        queued = store.preview_job(owner, job_id) if result is not None else None
        return (directory, result) if result is not None and queued and queued["state"] == "completed" else None
    if result is not None:
        return directory, result
    if not _RENDER_SLOT.acquire(blocking=False):
        raise StateError("PREVIEW_BUSY: retry after the current rendering finishes")
    try:
        result = cached()
        if result is None:
            with tempfile.TemporaryDirectory(prefix="preview-", dir=pptx.parent) as temporary:
                staging = Path(temporary) / "pages"
                try:
                    result = render(pptx, staging)
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    raise StateError("PREVIEW_RENDER_FAILED: PPTX remains available; retry preview") from exc
                result.update(pptx_sha256=digest, visual_review="not_performed")
                (staging / "preview.json").write_text(json.dumps(result))
                # Recheck expiry after potentially slow conversion, before publishing anything.
                store.job(owner, job_id)
                if directory.exists():
                    shutil.rmtree(directory)
                staging.replace(directory)
        return directory, result
    finally:
        _RENDER_SLOT.release()


def preview_image(store, owner, job_id, page=1, overview=False):
    if not 1 <= page <= 40:
        raise StateError("PREVIEW_PAGE_OUT_OF_RANGE")
    job = store.job(owner, job_id)
    if job["state"] != "completed":
        raise StateError("JOB_NOT_COMPLETED")
    output = json.loads(job["output"])
    if "pptx" not in output:
        raise StateError("NOT_PRESENTATION_JOB")
    if output.get("slide_count") and page > output["slide_count"]:
        raise StateError("PREVIEW_PAGE_OUT_OF_RANGE")
    cached = preview_files(store, owner, job_id)
    if cached is None:
        queued = store.preview_job(owner, job_id, enqueue=True)
        return None, {"job_id": job_id, "preview_job_id": queued["id"], "state": queued["state"],
                      "error": queued["error"], "retry_after_seconds": 2, "visual_review": "not_performed",
                      "guidance": "Wait, then call get_slide_preview again. On failure use retry_job(preview_job_id)."}
    directory, result = cached
    if page > result["page_count"]:
        raise StateError("PREVIEW_PAGE_OUT_OF_RANGE")
    pages = list(range(page, min(page + (6 if overview else 1), result["page_count"] + 1)))
    if overview:
        # Six pages per sheet keep image responses bounded even for a 40-page presentation.
        sheet = Image.new("RGB", (1400, ((len(pages) + 1) // 2) * 550), "#eeeeee")
        draw = ImageDraw.Draw(sheet)
        for index, number in enumerate(pages):
            with Image.open(directory / result["images"][number - 1]) as image:
                thumbnail = ImageOps.contain(image.convert("RGB"), (680, 510))
            x, y = index % 2 * 700, index // 2 * 550
            sheet.paste(thumbnail, (x + 10, y + 30))
            draw.text((x + 10, y + 10), str(number), fill="black")
        import io

        buffer = io.BytesIO()
        sheet.save(buffer, format="PNG")
        data = buffer.getvalue()
    else:
        data = (directory / result["images"][page - 1]).read_bytes()
    metadata = {**{k: v for k, v in result.items() if k not in {"images", "pdf"}},
                "job_id": job_id, "state": "ready", "pages": pages, "overview": overview,
                "next_page": pages[-1] + 1 if pages[-1] < result["page_count"] else None}
    return data, metadata
