import pytest

from research_slide_agent.config import Settings
from research_slide_agent.engine import create_test_template
from research_slide_agent.sample import sample_spec
from research_slide_agent.store import Store


@pytest.fixture
def settings(tmp_path):
    template = tmp_path / "template.pptx"
    create_test_template(template)
    return Settings(data_dir=tmp_path / "data", template=template, dev=True, require_render=False)


@pytest.fixture
def store(settings):
    return Store(settings)


def approved_project(store, owner="alice", count=5):
    p = store.create(owner)
    spec = sample_spec(p["id"], count)
    store.save_spec(owner, p["id"], spec, 0)
    r = store.review(owner, p["id"], "outline")
    store.approve_from_browser(owner, r["review_id"])
    for slide in spec.slides:
        r = store.review(owner, p["id"], "slide", slide.slide_id)
        store.approve_from_browser(owner, r["review_id"])
    return p, spec
