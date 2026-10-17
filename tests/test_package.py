import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from jsonschema import Draft202012Validator

from research_slide_agent.models import SlideSpec
from research_slide_agent.rules import authoring_context

ROOT = Path(__file__).resolve().parents[1]


def test_official_plugin_schemas():
    plugin = ROOT / "plugins/research-slide-agent"
    for kind in ["plugin", "mcp"]:
        schema = json.loads((ROOT / f"schemas/agent-plugins-{kind}-1.0.0.json").read_text())
        Draft202012Validator(schema).validate(json.loads((plugin / f"{kind}.json").read_text()))
    assert (plugin / "skills/research-slides/SKILL.md").is_file()


def test_slidespec_schema_is_current():
    assert json.loads((ROOT / "schemas/slidespec.json").read_text()) == SlideSpec.model_json_schema()


def test_wheel_serves_complete_rules_without_plugin_checkout(tmp_path):
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is required for the distribution build smoke test")
    subprocess.run([uv, "build", "--wheel", "--out-dir", str(tmp_path)],
                   cwd=ROOT, check=True, capture_output=True, timeout=120)
    wheel = next(tmp_path.glob("*.whl"))
    expected = authoring_context()
    with ZipFile(wheel) as archive:
        for document in expected["documents"]:
            filename = document["path"].removeprefix("references/")
            assert archive.read("research_slide_agent/authoring_rules/" + filename).decode() == document["text"]
    # Import the wheel itself from a directory with no plugins/ or source checkout.
    result = subprocess.run(
        [sys.executable, "-c", "import json; from research_slide_agent.rules import authoring_context; "
         "print(json.dumps(authoring_context()))"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(wheel)},
        check=True, capture_output=True, text=True, timeout=30,
    )
    assert json.loads(result.stdout) == expected
