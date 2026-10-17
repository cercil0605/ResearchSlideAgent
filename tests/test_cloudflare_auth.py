import time
from dataclasses import replace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from research_slide_agent.app import create_app
from research_slide_agent.auth import AuthError
from research_slide_agent.sample import sample_spec
from research_slide_agent.worker import process_one


@pytest.fixture
def cloudflare(settings):
    settings = replace(
        settings, dev=False, auth_mode="cloudflare", base_url="https://slides.example.org",
        cf_team_domain="https://lab.cloudflareaccess.com", cf_audience="application-aud",
        allowed_emails=frozenset({"alice@example.org", "bob@example.org"}), session_key="s" * 48,
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = create_app(settings)

    class Keys:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": key.public_key()})()

    app.state.auth.jwks = Keys()

    def token(_drop=(), **changes):
        claims = {
            "iss": settings.cf_team_domain, "aud": [settings.cf_audience],
            "sub": "alice-id", "email": "alice@example.org", "type": "app",
            "iat": int(time.time()), "exp": int(time.time()) + 600, **changes,
        }
        return jwt.encode({k: v for k, v in claims.items() if k not in _drop}, key, algorithm="RS256")

    return app, settings, token


def rpc(client, method, params=None):
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
    }, headers={"Accept": "application/json, text/event-stream"})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def call(client, name, **arguments):
    return rpc(client, "tools/call", {"name": name, "arguments": arguments})


def test_cloudflare_generation_and_browser_approval(cloudflare):
    app, settings, token = cloudflare
    with TestClient(app, base_url=settings.base_url, headers={"Cf-Access-Jwt-Assertion": token()}) as client:
        profile = call(client, "get_profile")["structuredContent"]
        assert profile["id"] == "cloudflare:alice-id"
        tools = rpc(client, "tools/list")["tools"]
        assert all(t["_meta"]["securitySchemes"] == [{"type": "oauth2", "scopes": []}] for t in tools)
        pid = call(client, "create_project")["structuredContent"]["id"]
        spec = sample_spec(pid, 1)
        saved = call(client, "save_slide_spec", presentation_id=pid, spec=spec.model_dump(), expected_version=0)
        assert not saved.get("isError")
        assert call(client, "enqueue_generation", presentation_id=pid)["isError"]
        for stage, slide_id in [("outline", ""), ("slide", spec.slides[0].slide_id)]:
            review = call(client, "request_approval", presentation_id=pid, stage=stage, slide_id=slide_id)
            path = "/review/" + review["structuredContent"]["review_id"]
            assert client.get(path).status_code == 200
            cookie = app.state.auth.unsign("browser", client.cookies["rsa_session"])
            assert cookie["owner"] == profile["id"]
            assert client.post(path, json={}).status_code == 401
            assert client.post(path, json={}, headers={
                "X-CSRF": cookie["csrf"], "Origin": "https://attacker.example",
            }).status_code == 401
            assert client.post(path, json={}, headers={
                "X-CSRF": cookie["csrf"], "Origin": settings.base_url,
            }).status_code == 200
        job = call(client, "enqueue_generation", presentation_id=pid)["structuredContent"]
        assert process_one(app.state.store, settings)
        assert call(client, "get_job", job_id=job["id"])["structuredContent"]["state"] == "completed"
        cap = app.state.auth.sign("artifact", {
            "owner": profile["id"], "job": job["id"], "name": "presentation.pptx",
        })
        download = client.get(f"/artifact/{job['id']}/presentation.pptx?cap={cap}")
        assert download.status_code == 200 and download.content.startswith(b"PK")


@pytest.mark.parametrize("change", [
    {"iss": "https://other.cloudflareaccess.com"}, {"aud": ["another-app"]},
    {"email": "intruder@example.org"}, {"email": None}, {"email": ["alice@example.org"]},
    {"sub": ""}, {"sub": None}, {"type": "org"}, {"exp": 0}, {"iat": int(time.time()) + 3600},
])
def test_invalid_cloudflare_claims_rejected(cloudflare, change):
    app, settings, token = cloudflare
    with TestClient(app, base_url=settings.base_url) as client:
        assert client.post("/mcp", headers={"Cf-Access-Jwt-Assertion": token(**change)}).status_code == 401


def test_cloudflare_signature_missing_claims_and_service_tokens_rejected(cloudflare):
    app, settings, token = cloudflare
    claims = jwt.decode(token(), options={"verify_signature": False})
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid = ["", "oauth:opaque-access-token", jwt.encode(claims, other_key, algorithm="RS256")]
    invalid.append(jwt.encode(claims, "not-an-rsa-key" * 4, algorithm="HS256"))
    for required in ("email", "sub", "exp", "iat", "iss", "aud", "type"):
        invalid.append(token(_drop=(required,)))
    invalid.append(token(sub="", email="", common_name="service-token.access"))
    with TestClient(app, base_url=settings.base_url) as client:
        for assertion in invalid:
            assert client.get("/", headers={"Cf-Access-Jwt-Assertion": assertion}).status_code == 401
        assert client.get("/", headers={
            "Cf-Access-Authenticated-User-Email": "alice@example.org", "Authorization": "Bearer " + token(),
        }).status_code == 401


def test_cloudflare_cookies_and_capabilities_cannot_bypass_identity(cloudflare):
    app, settings, token = cloudflare
    owner = "cloudflare:alice-id"
    pid = app.state.store.create(owner)["id"]
    cap = app.state.auth.sign("upload", {"owner": owner, "project": pid})
    path = f"/upload/{pid}?cap={cap}"
    with TestClient(app, base_url=settings.base_url, headers={"Cf-Access-Jwt-Assertion": token()}) as client:
        assert client.get("/project/" + pid).status_code == 200
        browser_cookie = client.cookies["rsa_session"]
        assert client.put(path, content=b"a,b\n1,2", headers={"X-Filename": "data.csv"}).status_code == 201
        # A valid second identity cannot use Alice's session or signed upload URL.
        client.headers["Cf-Access-Jwt-Assertion"] = token(sub="bob-id", email="bob@example.org")
        assert client.put(path, content=b"a,b", headers={"X-Filename": "other.csv"}).status_code == 401
        assert client.post("/review/anything", json={}).status_code == 401
        # An old session and capability without a fresh Access assertion grant no access.
        del client.headers["Cf-Access-Jwt-Assertion"]
        assert client.get("/project/" + pid).status_code == 401
        assert client.put(path, content=b"a,b", headers={"X-Filename": "other.csv"}).status_code == 401
        assert client.cookies["rsa_session"] == browser_cookie
        # Revoking an email is enforced even while the browser session remains valid.
        client.headers["Cf-Access-Jwt-Assertion"] = token()
        settings.allowed_emails = frozenset({"bob@example.org"})
        assert client.get("/project/" + pid).status_code == 401


def test_cloudflare_discovery_health_and_login(cloudflare):
    app, settings, token = cloudflare
    with TestClient(app, base_url=settings.base_url) as client:
        assert client.get("/health").json() == {"status": "ok", "mode": "cloudflare"}
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            metadata = client.get(path).json()
            assert metadata["resource"] == settings.base_url + "/mcp"
            assert metadata["authorization_servers"] == [settings.base_url]
            assert metadata["scopes_supported"] == []
        denied = client.post("/mcp")
        assert denied.status_code == 401
        assert 'resource_metadata="https://slides.example.org/.well-known/oauth-protected-resource"' in denied.headers["www-authenticate"]
        assert "slides:write" not in denied.headers["www-authenticate"]
        assert client.get("/login").status_code == 401
        client.headers["Cf-Access-Jwt-Assertion"] = token(email="ALICE@example.org")
        logged_in = client.get("/login?next=https://attacker.example", follow_redirects=False)
        assert logged_in.status_code == 303 and logged_in.headers["location"] == "/"
        cookie = logged_in.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert client.get("/oauth/callback").status_code == 404


@pytest.mark.parametrize("change", [
    {"auth_mode": "none"}, {"cf_team_domain": "https://attacker.example"},
    {"cf_team_domain": "https://lab.cloudflareaccess.com@attacker.example"},
    {"cf_team_domain": "http://lab.cloudflareaccess.com"},
    {"cf_team_domain": "https://lab.cloudflareaccess.com/path"}, {"cf_audience": ""},
    {"allowed_emails": frozenset()}, {"allowed_emails": frozenset({"*@example.org", "bad"})},
    {"session_key": "short"}, {"base_url": "http://slides.example.org"},
])
def test_cloudflare_config_fails_closed(cloudflare, change):
    _, settings, _ = cloudflare
    with pytest.raises(ValueError):
        replace(settings, **change).validate()


def test_cloudflare_jwks_failure_is_auth_failure(cloudflare):
    app, _, token = cloudflare

    class UnavailableKeys:
        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientConnectionError("Unavailable")

    app.state.auth.jwks = UnavailableKeys()
    with pytest.raises(AuthError):
        app.state.auth.cloudflare_owner(token())
