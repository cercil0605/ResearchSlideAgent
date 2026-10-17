import base64
import hashlib
import html
import ipaddress
import json
import logging
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urlparse

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from .auth import SCOPE, Auth, AuthError, AuthMiddleware
from .config import Settings
from .files import MAX_FILE, InputError
from .server import make_mcp
from .store import StateError, Store


async def limited_body(request, maximum=MAX_FILE):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise InputError("Request exceeds size limit")
    return bytes(body)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    settings.validate()
    # Library request logs can include signed URLs; only our allowlisted metadata logger is retained.
    for namespace in ("mcp", "httpx", "httpx2", "httpcore", "httpcore2", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(namespace)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
    auth, store = Auth(settings), Store(settings)
    mcp = make_mcp(store, settings, auth)
    from mcp.server.transport_security import TransportSecuritySettings

    url = urlparse(settings.base_url)
    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[url.netloc], allowed_origins=[settings.base_url]
        ),
    )
    origin = settings.base_url.rstrip("/")

    def csrf_check(request, csrf, value):
        if request.headers.get("origin") != origin or not secrets.compare_digest(csrf, value or ""):
            raise AuthError("CSRF validation failed")

    def page(title, body, script=""):
        nonce = secrets.token_urlsafe(24)
        content = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style nonce="{nonce}">body{{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 24px;background:#f6f7f9;color:#172333}}pre{{white-space:pre-wrap;background:white;padding:24px;overflow-wrap:anywhere}}button,input{{font:inherit;padding:10px;margin:6px}}button{{cursor:pointer}}a{{color:#245b9c}}</style>
<h1>{html.escape(title)}</h1>{body}<script nonce="{nonce}">{script}</script></html>'''
        return HTMLResponse(
            content,
            headers={
                "Content-Security-Policy": f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def browser_or_redirect(request):
        try:
            return auth.browser(request)
        except AuthError:
            return RedirectResponse("/login?" + urlencode({"next": request.url.path}), 303)

    async def health(request):
        return JSONResponse({
            "status": "ok", "mode": "loopback-development" if settings.dev else settings.auth_mode
        })

    async def metadata(request):
        return JSONResponse(
            {
                "resource": settings.base_url + "/mcp",
                "authorization_servers": (
                    [settings.base_url] if settings.cloudflare else [settings.issuer] if settings.issuer else []
                ),
                "scopes_supported": settings.oauth_scopes,
                "bearer_methods_supported": ["header"],
            }
        )

    async def login(request):
        next_path = request.query_params.get("next", "/")
        if not next_path.startswith("/project/"):
            next_path = "/"
        if settings.cloudflare:
            response = RedirectResponse(next_path, 303)
            auth.browser_cookie(response, request.state.rsa_owner)
            return response
        if settings.dev:
            client = request.client
            if not client or not ipaddress.ip_address(client.host).is_loopback:
                raise AuthError("Development browser login is loopback-only")
            response = RedirectResponse(next_path, 303)
            auth.browser_cookie(response, "dev-user")
            return response
        provider = await auth.discovery()
        state, verifier, nonce = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(48),
            secrets.token_urlsafe(32),
        )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params = {
            "client_id": settings.client_id,
            "redirect_uri": origin + "/oauth/callback",
            "response_type": "code",
            "scope": "openid " + SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "resource": settings.base_url + "/mcp",
        }
        response = RedirectResponse(provider["authorization_endpoint"] + "?" + urlencode(params), 303)
        response.set_cookie(
            "rsa_oauth",
            auth.sign(
                "oauth_state", {"state": state, "verifier": verifier, "nonce": nonce, "next": next_path}, 600
            ),
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=600,
        )
        return response

    async def callback(request):
        if settings.cloudflare:
            return Response(status_code=404)
        state = auth.unsign("oauth_state", request.cookies.get("rsa_oauth", ""))
        if not secrets.compare_digest(state["state"], request.query_params.get("state", "")):
            raise AuthError("OAuth state mismatch")
        if request.query_params.get("iss", settings.issuer) != settings.issuer:
            raise AuthError("OAuth response issuer mismatch")
        provider = await auth.discovery()
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "code": request.query_params.get("code", ""),
            "redirect_uri": origin + "/oauth/callback",
            "code_verifier": state["verifier"],
            "resource": settings.base_url + "/mcp",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = await client.post(provider["token_endpoint"], data=data)
            if response.status_code != 200:
                raise AuthError("OAuth token exchange failed")
            tokens = response.json()
        owner = await run_in_threadpool(auth.token_owner, tokens["access_token"])
        # Verify OIDC nonce and audience separately from the MCP access token.
        import jwt

        key = await run_in_threadpool(auth.jwks.get_signing_key_from_jwt, tokens["id_token"])
        claims = jwt.decode(
            tokens["id_token"],
            key.key,
            algorithms=["RS256"],
            audience=settings.client_id,
            issuer=settings.issuer,
            options={"require": ["sub", "exp", "iat", "nonce"]},
        )
        if claims["nonce"] != state["nonce"] or claims["sub"] != owner:
            raise AuthError("OIDC nonce or subject mismatch")
        result = RedirectResponse(state["next"], 303)
        auth.browser_cookie(result, owner)
        result.delete_cookie("rsa_oauth")
        return result

    async def home(request):
        return page(
            "Research Slide Agent",
            "<p>MCP endpoint: <code>/mcp</code></p><p>ChatGPTでプロジェクトを作成し、ツールが返したURLで資料を登録します。</p>",
        )

    async def project_page(request):
        session = browser_or_redirect(request)
        if isinstance(session, Response):
            return session
        owner, csrf = session
        pid = request.path_params["project"]
        p = store.project(owner, pid)
        files = store.files(owner, pid)
        body = f"""<p>Project: {html.escape(pid)} / Version: {p["version"]}</p>
<p>最大10ファイル、各20 MiB、合計100 MiB。資料は7日後に削除します。再アップロードしたPPTXを最新版として扱います。</p>
<form id="upload"><input id="file" type="file" required accept=".pdf,.pptx,.png,.jpg,.jpeg,.csv,.xlsx"><br>
<label>引用著者（不明なら空欄）<input id="author"></label><label>年<input id="year" type="number"></label><button>登録</button></form>
<p id="status" role="status"></p><pre>{html.escape(json.dumps(files, ensure_ascii=False, indent=2))}</pre>
<p>登録後、チャットから get_project を呼び直してください。引用メタデータは資料と照合して入力してください。</p>"""
        for f in files:
            fid = html.escape(f["id"])
            body += f'<form class="metadata" data-id="{fid}"><label>資料 {html.escape(f["name"])} の著者<input name="author" required></label><label>年<input name="year" type="number" required></label><button>引用情報を確認して保存</button></form>'
        script = f"""document.getElementById('upload').onsubmit=async e=>{{e.preventDefault();const file=document.getElementById('file').files[0];
const h={{'X-Filename':encodeURIComponent(file.name),'X-CSRF':{json.dumps(csrf)},'X-Author':encodeURIComponent(document.getElementById('author').value),'X-Year':document.getElementById('year').value}};
const r=await fetch(location.pathname+'/upload',{{method:'PUT',headers:h,body:file}});document.getElementById('status').textContent=JSON.stringify(await r.json());if(r.ok)location.reload();}};"""
        script += f"""document.querySelectorAll('form.metadata').forEach(form=>form.onsubmit=async e=>{{e.preventDefault();const r=await fetch(location.pathname+'/source/'+form.dataset.id+'/metadata',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF':{json.dumps(csrf)}}},body:JSON.stringify({{author:form.elements.author.value,year:Number(form.elements.year.value)}})}});document.getElementById('status').textContent=JSON.stringify(await r.json());if(r.ok)location.reload();}});"""
        return page("資料登録", body, script)

    async def upload(request):
        from urllib.parse import unquote

        pid = request.path_params["project"]
        if "cap" in request.query_params:
            cap = auth.unsign("upload", request.query_params["cap"])
            if cap["project"] != pid:
                raise AuthError("Capability project mismatch")
            owner, author, year = cap["owner"], None, None
            auth.check_owner(request, owner)
        else:
            owner, csrf = auth.browser(request)
            csrf_check(request, csrf, request.headers.get("x-csrf"))
            author = unquote(request.headers.get("x-author", "")) or None
            year = int(request.headers["x-year"]) if request.headers.get("x-year") else None
        store.project(owner, pid)
        name = unquote(request.headers.get("x-filename", ""))
        data = await limited_body(request)
        result = await run_in_threadpool(store.register, owner, pid, name, data, author, year)
        return JSONResponse(result, 201)

    async def source_metadata(request):
        owner, csrf = auth.browser(request)
        csrf_check(request, csrf, request.headers.get("x-csrf"))
        data = json.loads(await limited_body(request, 4096))
        return JSONResponse(
            store.source_metadata(
                owner,
                request.path_params["project"],
                request.path_params["source"],
                data["author"],
                int(data["year"]),
            )
        )

    async def artifact(request):
        job_id, name = request.path_params["job"], request.path_params["name"]
        claims = auth.unsign("artifact", request.query_params.get("cap", ""))
        if claims["job"] != job_id or claims["name"] != name:
            raise AuthError("Artifact capability mismatch")
        auth.check_owner(request, claims["owner"])
        job = store.job(claims["owner"], job_id)
        if job["state"] != "completed":
            raise StateError("ARTIFACT_NOT_READY")
        output = json.loads(job["output"])
        if name == "presentation.pptx":
            path = store.root / output["pptx"]
            filename = "research-slides.pptx"
        else:
            raise StateError("Unknown artifact")
        return FileResponse(
            path,
            filename=filename,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def error(request, exc):
        status = 401 if isinstance(exc, AuthError) else 400
        return JSONResponse({"error": str(exc)[:400]}, status, headers={"Cache-Control": "no-store"})

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/", home),
            Route("/health", health),
            Route("/.well-known/oauth-protected-resource", metadata),
            Route("/.well-known/oauth-protected-resource/mcp", metadata),
            Route("/login", login),
            Route("/oauth/callback", callback),
            Route("/project/{project}", project_page),
            Route("/project/{project}/upload", upload, methods=["PUT"]),
            Route("/project/{project}/source/{source}/metadata", source_metadata, methods=["POST"]),
            Route("/upload/{project}", upload, methods=["PUT"]),
            Route("/artifact/{job}/{name}", artifact),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
        exception_handlers={AuthError: error, StateError: error, InputError: error, ValueError: error},
    )
    app.state.store, app.state.auth, app.state.mcp = store, auth, mcp
    app.add_middleware(AuthMiddleware, auth=auth)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(settings.base_url).hostname])
    return app
