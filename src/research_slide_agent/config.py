import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("RSA_DATA_DIR", "var")))
    template: Path = field(
        default_factory=lambda: Path(os.getenv("RSA_TEMPLATE", "templates/lab-template.pptx"))
    )
    base_url: str = field(default_factory=lambda: os.getenv("RSA_BASE_URL", "http://127.0.0.1:8000"))
    dev: bool = field(default_factory=lambda: os.getenv("RSA_DEV", "0") == "1")
    auth_mode: str = field(default_factory=lambda: os.getenv("RSA_AUTH_MODE", "oauth"))
    cf_team_domain: str = field(
        default_factory=lambda: os.getenv("RSA_CF_TEAM_DOMAIN", "").rstrip("/")
    )
    cf_audience: str = field(default_factory=lambda: os.getenv("RSA_CF_AUDIENCE", ""))
    issuer: str = field(default_factory=lambda: os.getenv("RSA_OAUTH_ISSUER", ""))
    audience: str = field(default_factory=lambda: os.getenv("RSA_OAUTH_AUDIENCE", ""))
    jwks_url: str = field(default_factory=lambda: os.getenv("RSA_JWKS_URL", ""))
    client_id: str = field(default_factory=lambda: os.getenv("RSA_WEB_CLIENT_ID", "research-slide-web"))
    allowed_subs: frozenset[str] = field(
        default_factory=lambda: frozenset(filter(None, os.getenv("RSA_ALLOWED_SUBS", "").split(",")))
    )
    session_key: str = field(default_factory=lambda: os.getenv("RSA_SESSION_KEY", ""))
    worker_limit: int = field(default_factory=lambda: int(os.getenv("RSA_WORKER_LIMIT", "1")))
    lease_seconds: int = 1800
    # Local mode: one user on their own machine over MCP stdio. No HTTP listener and no OAuth;
    # the client process that launches the server is the only caller.
    local: bool = False
    input_dirs: tuple[Path, ...] = ()
    output_dir: Path | None = None

    @property
    def cloudflare(self):
        return not self.dev and not self.local and self.auth_mode == "cloudflare"

    @property
    def oauth_scopes(self):
        return [] if self.cloudflare else ["slides:write"]

    def validate(self):
        if self.local:
            if not self.input_dirs or self.output_dir is None:
                raise ValueError("Local mode requires at least one input directory and an output directory")
            if not 1 <= self.worker_limit <= 2:
                raise ValueError("Worker limit must be 1 or 2")
            return
        url = urlparse(self.base_url)
        if self.auth_mode not in {"oauth", "cloudflare"}:
            raise ValueError("RSA_AUTH_MODE must be oauth or cloudflare")
        if self.dev:
            if url.hostname not in {"127.0.0.1", "localhost", "::1"} or os.getenv("RSA_ENV") == "production":
                raise ValueError("Development authentication is restricted to loopback")
        elif self.cloudflare:
            if (
                url.scheme != "https" or not url.hostname or url.netloc != url.hostname
                or url.path or url.query or url.fragment or len(self.session_key) < 32
            ):
                raise ValueError("Cloudflare requires a public HTTPS origin and a 32+ character session key")
            if not re.fullmatch(
                r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.cloudflareaccess\.com",
                self.cf_team_domain,
            ):
                raise ValueError("RSA_CF_TEAM_DOMAIN must be https://<team>.cloudflareaccess.com")
            if not self.cf_audience:
                raise ValueError("Cloudflare requires an application AUD")
        elif (
            url.scheme != "https"
            or not all([self.issuer, self.audience, self.jwks_url, self.allowed_subs])
            or len(self.session_key) < 32
        ):
            raise ValueError(
                "Production requires HTTPS, OAuth configuration, allowed subjects and a 32+ character session key"
            )
        if not self.dev and not self.cloudflare and (
            urlparse(self.issuer).scheme != "https"
            or urlparse(self.jwks_url).scheme != "https"
            or urlparse(self.issuer).hostname == "accounts.google.com"
        ):
            raise ValueError(
                "Use a dedicated OAuth authorization server with Google federation, never Google's ID-token issuer"
            )
        if not 1 <= self.worker_limit <= 2:
            raise ValueError("Worker limit must be 1 or 2")
