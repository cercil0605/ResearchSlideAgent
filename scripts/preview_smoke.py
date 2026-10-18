"""Exercise the new narrative, immutable generation and real on-demand preview without an LLM."""

import json
import shutil
from pathlib import Path

from research_slide_agent.config import Settings
from research_slide_agent.models import SlideSpec
from research_slide_agent.previews import preview_files, preview_image
from research_slide_agent.store import Store
from research_slide_agent.worker import process_one

if __name__ == "__main__":
    destination = Path("artifacts/narrative-check")
    destination.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=destination / "data", template=Path("templates/lab-template.pptx"), dev=True)
    store = Store(settings)
    project = store.create("smoke")
    raw = json.loads(Path("examples/narrative.slidespec.json").read_text())
    raw["presentation_id"] = project["id"]
    spec = SlideSpec.model_validate(raw)
    store.save_spec("smoke", project["id"], spec, 0)
    job = store.enqueue("smoke", project["id"])
    assert process_one(store, settings)
    job = store.job("smoke", job["id"])
    assert job["state"] == "completed", job
    assert preview_files(store, "smoke", job["id"]) is None
    image, info = preview_image(store, "smoke", job["id"], overview=True)
    assert info["pages"] == [1, 2, 3, 4, 5, 6] and info["next_page"] == 7
    assert info["page_count"] == len(spec.slides)
    assert info["visual_review"] == "not_performed" and not info["powerpoint_verified"]
    (destination / "overview.png").write_bytes(image)
    image, single = preview_image(store, "smoke", job["id"], page=3)
    assert single["pptx_sha256"] == info["pptx_sha256"]
    (destination / "example.png").write_bytes(image)
    output = json.loads(job["output"])
    shutil.copyfile(store.root / output["pptx"], destination / "presentation.pptx")
    (destination / "preview-report.json").write_text(json.dumps(info, indent=2))
    print(json.dumps({"page_count": info["page_count"], "renderer": info["renderer"],
                      "pdf": str(preview_files(store, "smoke", job["id"])[0] / "presentation.pdf")}, indent=2))
