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
