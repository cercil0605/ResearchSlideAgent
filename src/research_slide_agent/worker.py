import hashlib
import json
import logging
import signal
import subprocess
import threading
import time
from logging.handlers import TimedRotatingFileHandler

from .engine import LayoutError, generate, inspect_pptx, patch_text
from .models import SlideSpec
from .previews import preview_files
from .store import StateError

log = logging.getLogger("rsa.worker")


def process_one(store, settings):
    job = store.claim()
    if not job:
        return False
    started = time.monotonic()
    path = store.root / job["project"] / "jobs" / job["id"] / job["lease_token"]
    path.mkdir(parents=True, exist_ok=True)
    pptx = path / "presentation.pptx"
    try:
        payload = job["payload"]
        if payload["kind"] == "preview":
            _, preview = preview_files(store, job["owner"], payload["source_job_id"], create=True,
                                       expected_sha=payload["pptx_sha256"])
            store.finish(job["id"], job["lease_token"], "validating")
            store.finish(job["id"], job["lease_token"], "completed",
                         output={"source_job_id": payload["source_job_id"], "pptx_sha256": preview["pptx_sha256"]})
        elif payload["kind"] == "generate":
            if hashlib.sha256(settings.template.read_bytes()).hexdigest() != payload["template_sha256"]:
                raise StateError("TEMPLATE_CHANGED_RESAVE_REQUIRED")
            spec = SlideSpec.model_validate(payload["spec"])
            images = {
                f["id"]: store.file(job["owner"], job["project"], f["id"])["path"]
                for f in store.files(job["owner"], job["project"])
                if f["kind"] in {"png", "jpg", "jpeg"}
            }
            generate(settings.template, spec, pptx, images)
        else:
            source = store.file(job["owner"], job["project"], payload["file_id"])
            if (
                store.project(job["owner"], job["project"])["latest_pptx"] != source["id"]
                or source["sha"] != payload["file_sha256"]
            ):
                raise StateError("PATCH_BASE_CHANGED")
            patch_text(
                source["path"],
                pptx,
                [{k: v for k, v in c.items() if k != "previous_text"} for c in payload["changes"]],
            )
        if payload["kind"] != "preview":
            store.finish(job["id"], job["lease_token"], "validating")
            structure = inspect_pptx(pptx)
            output = {
                "pptx": str(pptx.relative_to(store.root)),
                "directory": str(path.relative_to(store.root)), "slide_count": len(structure),
            }
            store.finish(job["id"], job["lease_token"], "completed", output=output)
    except (LayoutError, StateError, ValueError) as exc:
        code = "LAYOUT_REQUIRES_USER_CHANGE" if isinstance(exc, LayoutError) else "INVALID_JOB_STATE"
        if job["payload"]["kind"] == "preview":
            code = str(exc).split(":", 1)[0] if str(exc).startswith("PREVIEW_") else "PREVIEW_RENDER_FAILED"
        output = {"guidance": str(exc)[:2000]}
        if getattr(exc, "problems", None):
            # Every failing slot with measured amounts, so one revision can address all of them.
            output["problems"] = exc.problems
        store.finish(job["id"], job["lease_token"], "failed", error=code, output=output)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        preview = job["payload"]["kind"] == "preview"
        store.finish(job["id"], job["lease_token"], "failed",
                     error="PREVIEW_RENDER_FAILED" if preview else "IO_FAILURE", transient=not preview)
    log.info(
        json.dumps(
            {
                "job_id": job["id"],
                "operation": job["payload"]["kind"],
                "attempt": job["attempts"],
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
    )
    return True


def run_forever(store, settings):
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    run_loop(store, settings, lambda: stopping)


def start_background(store, settings):
    """Local mode: run the same queue loop in this process. Signals stay with the MCP stdio main thread."""
    stopping = threading.Event()
    thread = threading.Thread(
        target=run_loop, args=(store, settings, stopping.is_set, stopping.wait),
        name="rsa-worker", daemon=True,
    )
    thread.start()
    return stopping


def run_loop(store, settings, should_stop, sleep=time.sleep):
    directory = store.root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        directory / "worker.log", when="midnight", interval=1, backupCount=6, utc=True, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    last_cleanup = 0
    while not should_stop():
        try:
            if time.time() - last_cleanup >= 3600:
                store.cleanup()
                log.info(json.dumps({"operation": "maintenance", "status": "completed"}))
                for old_log in directory.glob("worker.log.*"):
                    if old_log.stat().st_mtime < time.time() - 7 * 86400:
                        old_log.unlink()
                last_cleanup = time.time()
            if not process_one(store, settings):
                sleep(2)
        except Exception:
            log.error(json.dumps({"operation": "worker_or_cleanup", "error_code": "WORKER_CYCLE_FAILED"}))
            sleep(5)
