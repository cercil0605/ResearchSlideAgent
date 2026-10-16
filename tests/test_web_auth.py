import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from research_slide_agent.app import create_app
from research_slide_agent.auth import Auth, AuthError
from research_slide_agent.config import Settings
from research_slide_agent.sample import sample_spec


def test_browser_approval_requires_session_csrf_and_origin(settings):
    app = create_app(settings)
    with TestClient(app, base_url=settings.base_url, client=("127.0.0.1", 1234)) as client:
        p = app.state.store.create("dev-user")
        app.state.store.save_spec("dev-user", p["id"], sample_spec(p["id"]), 0)
        review = app.state.store.review("dev-user", p["id"], "outline")
        url = "/review/" + review["review_id"]
        assert client.post(url, json={}).status_code == 401
        assert client.get(url).status_code == 200
        assert client.post(url, json={}, headers={"Origin": settings.base_url}).status_code == 401
        _, csrf = app.state.auth.browser(type("Request", (), {"cookies": client.cookies})())
        assert (
            client.post(
                url, json={}, headers={"X-CSRF": csrf, "Origin": "https://attacker.example"}
            ).status_code
            == 401
        )
        assert (
            client.post(url, json={}, headers={"X-CSRF": csrf, "Origin": settings.base_url}).status_code
            == 200
        )
        assert (
            client.post(url, json={}, headers={"X-CSRF": csrf, "Origin": settings.base_url}).status_code
            == 400
        )


def test_upload_capability_and_expired_artifact(settings):
    app = create_app(settings)
    with TestClient(app, base_url=settings.base_url, client=("127.0.0.1", 1234)) as client:
        store = app.state.store
        p = store.create("dev-user")
        cap = app.state.auth.sign("upload", {"owner": "dev-user", "project": p["id"]})
        response = client.put(
            "/upload/" + p["id"] + "?cap=" + cap, content=b"a,b\n1,2", headers={"X-Filename": "data.csv"}
        )
        assert response.status_code == 201
        other = store.create("other")
        assert (
            client.put(
                "/upload/" + other["id"] + "?cap=" + cap, content=b"a,b", headers={"X-Filename": "data.csv"}
            ).status_code
            == 401
        )
        bad = app.state.auth.sign(
            "artifact", {"owner": "dev-user", "job": "x", "name": "slide-1.png"}, ttl=-1
        )
        assert client.get("/artifact/x/slide-1.png?cap=" + bad).status_code == 401


def test_production_fail_closed():
    with pytest.raises(ValueError):
        Settings(dev=False).validate()
    with pytest.raises(ValueError):
        Settings(dev=True, base_url="http://0.0.0.0:8000").validate()


def test_jwt_issuer_audience_scope_and_allowlist(settings):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.issuer = "https://auth.example/realms/lab"
    settings.audience = "https://slides.example/mcp"
    settings.allowed_subs = frozenset(["alice"])
    auth = Auth(settings)

    class Keys:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": key.public_key()})()

    auth.jwks = Keys()
    claims = {
        "iss": settings.issuer,
        "aud": settings.audience,
        "sub": "alice",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "scope": "slides:write",
        "typ": "Bearer",
    }

    def sign(d):
        return jwt.encode(d, key, algorithm="RS256")

    assert auth.token_owner(sign(claims)) == "alice"
    for change in [
        {"iss": "https://accounts.google.com"},
        {"aud": "other"},
        {"sub": "bob"},
        {"scope": "openid"},
        {"exp": 0},
        {"token_use": "id"},
    ]:
        with pytest.raises(AuthError):
            auth.token_owner(sign({**claims, **change}))
