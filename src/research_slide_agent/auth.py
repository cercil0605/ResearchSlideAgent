import ipaddress
import secrets
import time
from urllib.parse import urlparse

import httpx
import jwt
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

SCOPE = "slides:write"


class AuthError(ValueError):
    pass


class Auth:
    def __init__(self, settings):
        self.settings = settings
        self.key = settings.session_key or secrets.token_urlsafe(48)
        jwks_url = (
            settings.cf_team_domain + "/cdn-cgi/access/certs" if settings.cloudflare else settings.jwks_url
        )
        self.jwks = (
            PyJWKClient(jwks_url, lifespan=300, timeout=10)
            if jwks_url
            else None
        )

    def token_owner(self, token):
        if not self.jwks:
            raise AuthError("OAuth is not configured")
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
            if (
                SCOPE not in claims.get("scope", "").split()
                or claims["sub"] not in self.settings.allowed_subs
            ):
                raise AuthError("Not allowed or missing scope")
            if claims.get("typ") in {"ID", "ID_TOKEN"} or claims.get("token_use") == "id":
                raise AuthError("ID tokens cannot authorize MCP")
            return claims["sub"]
        except (jwt.PyJWTError, KeyError, TypeError) as exc:
            raise AuthError("Invalid access token") from exc

    def cloudflare_owner(self, token):
        """Validate Access's origin assertion, never the opaque Managed OAuth bearer token."""
        if not self.settings.cloudflare or not self.jwks or not token:
            raise AuthError("Cloudflare Access assertion required")
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.cf_audience,
                issuer=self.settings.cf_team_domain,
                options={"require": ["sub", "email", "type", "exp", "iat", "iss", "aud"]},
            )
            email = claims["email"]
            if (
                claims["type"] != "app"
                or not isinstance(claims["sub"], str)
                or not claims["sub"].strip()
                or not isinstance(email, str)
                or email.casefold() not in self.settings.allowed_emails
            ):
                raise AuthError("Cloudflare user is not allowed")
            return "cloudflare:" + claims["sub"]
        except (jwt.PyJWTError, KeyError, TypeError) as exc:
            raise AuthError("Invalid Cloudflare Access assertion") from exc

    def check_owner(self, request, owner):
        if self.settings.dev:
            return
        if self.settings.cloudflare:
            current = request.scope.get("state", {}).get("rsa_owner")
            if not current or current != owner:
                raise AuthError("Authenticated user does not own this resource")
        elif owner not in self.settings.allowed_subs:
            raise AuthError("User no longer allowed")

    def sign(self, kind, claims, ttl=900):
        return jwt.encode(
            {**claims, "iss": "rsa", "aud": kind, "iat": int(time.time()), "exp": int(time.time()) + ttl},
            self.key,
            algorithm="HS256",
        )

    def unsign(self, kind, value):
        try:
            return jwt.decode(
                value,
                self.key,
                algorithms=["HS256"],
                audience=kind,
                issuer="rsa",
                options={"require": ["exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError("Expired or invalid capability/session") from exc

    def browser(self, request):
        claims = self.unsign("browser", request.cookies.get("rsa_session", ""))
        owner = claims["owner"]
        self.check_owner(request, owner)
        return owner, claims["csrf"]

    def browser_cookie(self, response, owner):
        response.set_cookie(
            "rsa_session",
            self.sign("browser", {"owner": owner, "csrf": secrets.token_urlsafe(32)}, 1800),
            max_age=1800,
            httponly=True,
            secure=not self.settings.dev,
            samesite="lax",
            path="/",
        )

    async def discovery(self):
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.get(
                self.settings.issuer.rstrip("/") + "/.well-known/openid-configuration"
            )
            response.raise_for_status()
            data = response.json()
        if data["issuer"] != self.settings.issuer:
            raise AuthError("OAuth issuer metadata mismatch")
        for key in ("authorization_endpoint", "token_endpoint"):
            if urlparse(data[key]).scheme != "https":
                raise AuthError("OAuth endpoints must use HTTPS")
        return data


def current_owner(ctx):
    request = ctx.request_context.request
    owner = request.scope.get("state", {}).get("rsa_owner") if request else None
    if not owner:
        raise AuthError("Authentication required")
    return owner


class AuthMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        is_mcp = path == "/mcp" or path.startswith("/mcp/")
        if self.auth.settings.cloudflare:
            if path in {
                "/health", "/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"
            }:
                return await self.app(scope, receive, send)
        elif not is_mcp:
            return await self.app(scope, receive, send)
        request = Request(scope)
        try:
            if self.auth.settings.cloudflare:
                owner = await run_in_threadpool(
                    self.auth.cloudflare_owner, request.headers.get("cf-access-jwt-assertion", "")
                )
            elif self.auth.settings.dev:
                client = scope.get("client")
                if not client or not ipaddress.ip_address(client[0]).is_loopback:
                    raise AuthError("Development MCP is loopback-only")
                owner = "dev-user"
            else:
                header = request.headers.get("authorization", "")
                if not header.startswith("Bearer "):
                    raise AuthError("Bearer access token required")
                owner = await run_in_threadpool(self.auth.token_owner, header[7:])
        except (AuthError, ValueError):
            challenge = (
                f'Bearer resource_metadata="{self.auth.settings.base_url}/.well-known/oauth-protected-resource", '
                'error="invalid_token", error_description="Sign in to continue"'
            )
            if not self.auth.settings.cloudflare:
                challenge += f', scope="{SCOPE}"'
            return await JSONResponse(
                {"error": "unauthorized"}, 401,
                headers={"Cache-Control": "no-store", **({"WWW-Authenticate": challenge} if is_mcp else {})},
            )(scope, receive, send)
        scope.setdefault("state", {})["rsa_owner"] = owner
        await self.app(scope, receive, send)
