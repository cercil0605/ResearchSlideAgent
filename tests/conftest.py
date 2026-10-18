import pytest

from research_slide_agent.config import Settings
from research_slide_agent.engine import create_test_template
from research_slide_agent.sample import sample_spec
from research_slide_agent.store import Store


@pytest.fixture
def settings(tmp_path):
    template = tmp_path / "template.pptx"
    create_test_template(template)
    return Settings(data_dir=tmp_path / "data", template=template, dev=True)


@pytest.fixture
def store(settings):
    return Store(settings)


def saved_project(store, owner="alice", count=5):
    p = store.create(owner)
    spec = sample_spec(p["id"], count)
    store.save_spec(owner, p["id"], spec, 0)
    return p, spec


@pytest.fixture
def preview_renderer(monkeypatch):
    """Deterministic renderer for API/cache tests; actual conversion is tested separately."""
    from PIL import Image
    from pptx import Presentation
    from pypdf import PdfWriter

    from research_slide_agent import previews

    calls = []

    def render(path, directory):
        calls.append(path)
        directory.mkdir(parents=True)
        writer = PdfWriter()
        images = []
        for i in range(len(Presentation(path).slides)):
            name = f"slide-{i + 1}.png"
            Image.new("RGB", (320, 240), (i * 10, 100, 150)).save(directory / name)
            images.append(name)
            writer.add_blank_page(width=320, height=240)
        writer.write(directory / "presentation.pdf")
        return {"pdf": "presentation.pdf", "images": images, "page_count": len(images),
                "renderer": "test", "fidelity": "approximate", "powerpoint_verified": False}

    monkeypatch.setattr(previews, "render", render)
    return calls
