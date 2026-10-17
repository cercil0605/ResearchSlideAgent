import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "deploy_poll", Path(__file__).resolve().parents[1] / "scripts/deploy_poll.py"
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def test_missing_auth_configuration_defers_startup():
    assert "RSA_CF_AUDIENCE" in deploy.missing_settings('RSA_CF_AUDIENCE=""\n')
    configured = "\n".join(f"{key}=configured" for key in deploy.REQUIRED)
    assert not deploy.missing_settings(configured)


def test_only_immutable_application_images_are_accepted():
    image = "ghcr.io/cercil0605/researchslideagent:" + "a" * 40
    assert deploy.deployment_image("  image: " + image + "\n") == image
    for invalid in ["ghcr.io/cercil0605/researchslideagent:latest", "unrelated/app:" + "a" * 40]:
        with pytest.raises(ValueError):
            deploy.deployment_image("  image: " + invalid + "\n")


def test_project_and_environment_are_explicit():
    command = deploy.compose_command(Path("/runtime/compose.yaml"), Path("/private/env"))
    assert command == ["docker", "compose", "--project-name", "research-slide-agent",
                       "--env-file", "/private/env", "--file", "/runtime/compose.yaml"]
