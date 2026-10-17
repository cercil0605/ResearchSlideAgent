import json
from pathlib import Path

from jsonschema import Draft202012Validator

from research_slide_agent.models import SlideSpec

ROOT = Path(__file__).resolve().parents[1]


def test_official_plugin_schemas():
    plugin = ROOT / "plugins/research-slide-agent"
    for kind in ["plugin", "mcp"]:
        schema = json.loads((ROOT / f"schemas/agent-plugins-{kind}-1.0.0.json").read_text())
        Draft202012Validator(schema).validate(json.loads((plugin / f"{kind}.json").read_text()))
    assert (plugin / "skills/research-slides/SKILL.md").is_file()


def test_slidespec_schema_is_current():
    assert json.loads((ROOT / "schemas/slidespec.json").read_text()) == SlideSpec.model_json_schema()
