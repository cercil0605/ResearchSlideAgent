import os
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
    issuer: str = field(default_factory=lambda: os.getenv("RSA_OAUTH_ISSUER", ""))
    audience: str = field(default_factory=lambda: os.getenv("RSA_OAUTH_AUDIENCE", ""))
    jwks_url: str = field(default_factory=lambda: os.getenv("RSA_JWKS_URL", ""))
    client_id: str = field(default_factory=lambda: os.getenv("RSA_WEB_CLIENT_ID", "research-slide-web"))
    allowed_subs: frozenset[str] = field(
        default_factory=lambda: frozenset(filter(None, os.getenv("RSA_ALLOWED_SUBS", "").split(",")))
    )
    session_key: str = field(default_factory=lambda: os.getenv("RSA_SESSION_KEY", ""))
    require_render: bool = True
    worker_limit: int = field(default_factory=lambda: int(os.getenv("RSA_WORKER_LIMIT", "1")))
    lease_seconds: int = 1800

    def validate(self):
        url = urlparse(self.base_url)
        if self.dev:
            if url.hostname not in {"127.0.0.1", "localhost", "::1"} or os.getenv("RSA_ENV") == "production":
                raise ValueError("Development authentication is restricted to loopback")
        elif (
            url.scheme != "https"
            or not all([self.issuer, self.audience, self.jwks_url, self.allowed_subs])
            or len(self.session_key) < 32
        ):
            raise ValueError(
                "Production requires HTTPS, OAuth configuration, allowed subjects and a 32+ character session key"
            )
        if not self.dev and (
            urlparse(self.issuer).scheme != "https"
            or urlparse(self.jwks_url).scheme != "https"
            or urlparse(self.issuer).hostname == "accounts.google.com"
        ):
            raise ValueError(
                "Use a dedicated OAuth authorization server with Google federation, never Google's ID-token issuer"
            )
        if not 1 <= self.worker_limit <= 2:
            raise ValueError("Worker limit must be 1 or 2")
