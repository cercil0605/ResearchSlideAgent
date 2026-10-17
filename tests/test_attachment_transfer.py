import socket

import httpx
import pytest
from test_pdf_assets import paper_bytes

from research_slide_agent import server
from research_slide_agent.files import MAX_FILE
from research_slide_agent.server import OpenAIFile, attachment_name, download_attachment
from research_slide_agent.store import StateError


@pytest.fixture
def attachment():
    return OpenAIFile(download_url="https://files.example.org/paper?secret=do-not-expose", file_id="file-1")


def mock_download(monkeypatch, handler):
    monkeypatch.setenv("RSA_ATTACHMENT_HOSTS", " files.example.org ")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    original = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(server.httpx, "AsyncClient", client)


@pytest.mark.asyncio
async def test_optional_filename_transfer_and_safe_fallback(monkeypatch, attachment):
    data = paper_bytes()

    def handler(request):
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, content=data)

    mock_download(monkeypatch, handler)
    received = await download_attachment(attachment)
    assert received == data
    assert attachment_name(attachment, received).endswith(".pdf")
    assert "/" not in attachment_name(attachment, received)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(302, "REDIRECT_REFUSED"), (401, "HTTP_401"),
                                        (403, "HTTP_403"), (404, "HTTP_404"), (500, "HTTP_500")])
async def test_transfer_status_is_actionable_without_leaking_url(monkeypatch, attachment, status, code):
    mock_download(monkeypatch, lambda request: httpx.Response(status, headers={"Location": "https://evil.invalid"}))
    with pytest.raises(StateError, match=code) as caught:
        await download_attachment(attachment)
    assert "secret" not in str(caught.value) and "do-not-expose" not in str(caught.value)


@pytest.mark.asyncio
async def test_transfer_unconfigured_private_and_oversize(monkeypatch, attachment):
    monkeypatch.delenv("RSA_ATTACHMENT_HOSTS", raising=False)
    with pytest.raises(StateError, match="ORIGIN_NOT_ALLOWED.*files.example.org"):
        await download_attachment(attachment)
    mock_download(monkeypatch, lambda request: httpx.Response(200, content=b"a" * (MAX_FILE + 1)))
    with pytest.raises(StateError, match="TOO_LARGE"):
        await download_attachment(attachment)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(StateError, match="ADDRESS_FORBIDDEN"):
        await download_attachment(attachment)


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://files.example.org/a", "https://user:pass@files.example.org/a",
                                 "https://files.example.org:444/a", "https://files.example.org.evil.invalid/a"])
async def test_transfer_never_accepts_arbitrary_origins(monkeypatch, url):
    monkeypatch.setenv("RSA_ATTACHMENT_HOSTS", "files.example.org")
    with pytest.raises(StateError, match="ORIGIN_NOT_ALLOWED"):
        await download_attachment(OpenAIFile(download_url=url, file_id="f"))


@pytest.mark.asyncio
@pytest.mark.parametrize("error,code", [(httpx.ReadTimeout("secret-url"), "TIMEOUT"),
                                       (httpx.ConnectError("secret-url"), "NETWORK_FAILED")])
async def test_network_errors_are_sanitized(monkeypatch, attachment, error, code):
    def handler(request):
        raise error

    mock_download(monkeypatch, handler)
    with pytest.raises(StateError, match=code) as caught:
        await download_attachment(attachment)
    assert "secret-url" not in str(caught.value)
