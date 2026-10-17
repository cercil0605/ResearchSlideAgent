"""Poll the CI deployment branch from the Pi, using existing gh/Docker logins."""

import base64
import fcntl
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "RSA_BASE_URL", "RSA_CF_TEAM_DOMAIN", "RSA_CF_AUDIENCE",
    "RSA_ALLOWED_EMAILS", "RSA_SESSION_KEY",
)


def missing_settings(text):
    values = {}
    for line in text.splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and not key.startswith("#"):
            values[key] = value.strip().strip("\"'")
    return [key for key in REQUIRED if not values.get(key)]


def deployment_image(manifest):
    match = re.search(
        r"^  image: (ghcr\.io/cercil0605/researchslideagent:[0-9a-f]{40})$",
        manifest, re.MULTILINE,
    )
    if not match:
        raise ValueError("Deployment must pin the application image to a full commit SHA")
    return match.group(1)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    state_dir = ROOT / "var/deploy"
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "update.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another deployment is running; skipping.")
            return
        env_file = ROOT / ".env.cloudflare"
        env = env_file.read_text() if env_file.exists() else ""
        missing = missing_settings(env)
        if missing:
            print("Waiting for .env.cloudflare settings: " + ", ".join(missing))
            return
        response = subprocess.run(
            ["gh", "api", "repos/cercil0605/ResearchSlideAgent/contents/compose.yaml"
             "?ref=deploy/production"],
            check=True, capture_output=True, text=True, timeout=60,
        )
        manifest = base64.b64decode(json.loads(response.stdout)["content"]).decode()
        image = deployment_image(manifest)
        state = {"manifest": digest(manifest), "environment": digest(env), "image": image}
        state_file = state_dir / "state.json"
        if state_file.exists() and json.loads(state_file.read_text()) == state:
            # Also restart this project if its containers were removed or stopped.
            compose_file = state_dir / "active.compose.yaml"
            if compose_file.exists():
                result = subprocess.run(
                    compose_command(compose_file, env_file) + ["ps", "--status", "running", "--services"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                if set(result.stdout.split()) == {"api", "worker"}:
                    print("Deployment unchanged: " + image)
                    return
        candidate = state_dir / "candidate.compose.yaml"
        candidate.write_text(manifest)
        command = compose_command(candidate, env_file)
        subprocess.run(command + ["config", "--quiet"], check=True, timeout=30)
        # Pull first so a registry outage leaves the current containers running.
        subprocess.run(command + ["pull"], check=True, timeout=900)
        # Stop both services together and respect the worker's ten-minute grace period.
        subprocess.run(command + ["stop"], check=True, timeout=660)
        subprocess.run(command + ["up", "-d", "--wait", "--wait-timeout", "120"],
                       check=True, timeout=300)
        candidate.replace(state_dir / "active.compose.yaml")
        temporary = state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state) + "\n")
        temporary.replace(state_file)
        print("Deployed: " + image)


def compose_command(compose_file, env_file):
    return ["docker", "compose", "--project-name", "research-slide-agent",
            "--env-file", str(env_file), "--file", str(compose_file)]


if __name__ == "__main__":
    main()
