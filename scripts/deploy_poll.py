"""Poll the CI deployment branch and report the running image to GitHub."""

import base64
import fcntl
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "RSA_BASE_URL", "RSA_CF_TEAM_DOMAIN", "RSA_CF_AUDIENCE",
    "RSA_SESSION_KEY",
)
GITHUB_API = "https://api.github.com/repos/cercil0605/ResearchSlideAgent"


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


def env_value(path, key):
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name == key:
            return value.strip().strip("\"'")
    return ""


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
        report_pending_deployment()
        manifest = github_get_manifest()
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
                    ensure_github_deployment_report(image)
                    return
        candidate = state_dir / "candidate.compose.yaml"
        candidate.write_text(manifest)
        command = compose_command(candidate, env_file)
        run_command(command + ["config", "--quiet"], timeout=30)
        # Pull first so a registry outage leaves the current containers running.
        run_command(command + ["pull"], timeout=900)
        # Stop both services together and respect the worker's ten-minute grace period.
        run_command(command + ["stop"], timeout=660)
        run_command(command + ["up", "-d", "--wait", "--wait-timeout", "120"], timeout=300)
        candidate.replace(state_dir / "active.compose.yaml")
        temporary = state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state) + "\n")
        temporary.replace(state_file)
        print("Deployed: " + image)
        record_github_deployment(image)


def run_command(args, timeout):
    subprocess.run(args, check=True, timeout=timeout)


def github_token():
    return env_value(ROOT / ".env.deploy", "RSA_DEPLOY_GITHUB_TOKEN")


def github_request(method, path, payload=None):
    token = github_token()
    if not token:
        raise RuntimeError("RSA_DEPLOY_GITHUB_TOKEN is missing from .env.deploy")
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        GITHUB_API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read()) if response.status != 204 else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {method} {path}") from None


def github_get_manifest():
    response = github_request("GET", "/contents/compose.yaml?ref=deploy/production")
    return base64.b64decode(response["content"]).decode()


def record_github_deployment(image):
    """Create a GitHub deployment for the image that has just started on this Pi."""
    pending = ROOT / "var/deploy/github-pending.json"
    temporary = pending.with_suffix(".tmp")
    temporary.write_text(json.dumps({"image": image}) + "\n")
    temporary.replace(pending)
    report_pending_deployment()


def ensure_github_deployment_report(image):
    reported = ROOT / "var/deploy/github-reported.json"
    if reported.exists() and json.loads(reported.read_text()).get("image") == image:
        return
    if not (ROOT / "var/deploy/github-pending.json").exists():
        record_github_deployment(image)


def report_pending_deployment():
    """Mark the deployment successful; retain its ID to retry if GitHub is unavailable."""
    pending = ROOT / "var/deploy/github-pending.json"
    if not pending.exists():
        return
    item = json.loads(pending.read_text())
    image = item["image"]
    try:
        if "id" not in item:
            result = github_request(
                "POST", "/deployments",
                {
                    "ref": image.rsplit(":", 1)[1],
                    "environment": "production",
                    "auto_merge": False,
                    "required_contexts": [],
                    "description": "Raspberry Pi started this image",
                    "transient_environment": False,
                    "production_environment": True,
                },
            )
            item["id"] = result["id"]
            pending.write_text(json.dumps(item) + "\n")
        github_request(
            "POST", f"/deployments/{item['id']}/statuses",
            {
                "state": "success",
                "description": "Raspberry Pi containers are running this image",
                "log_url": "https://github.com/cercil0605/ResearchSlideAgent/deployments",
                "environment": "production",
                "auto_inactive": True,
            },
        )
        pending.unlink()
        (ROOT / "var/deploy/github-reported.json").write_text(
            json.dumps({"image": image}) + "\n"
        )
        print("Reported to GitHub: " + image)
    except (OSError, KeyError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        # Keep the local record for the next five-minute run; deployment itself succeeded.
        print(f"GitHub deployment report pending: {exc}")


def compose_command(compose_file, env_file):
    return ["docker", "compose", "--project-name", "research-slide-agent",
            "--env-file", str(env_file), "--file", str(compose_file)]


if __name__ == "__main__":
    main()
