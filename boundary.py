import hashlib
import hmac
import re
from uuid import uuid4

from starlette.responses import JSONResponse

COOKIE = "shop_visitor"
MAX_CHAT_BODY = 16_384
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "connect-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def visitor(request, response, settings):
    def sign(identifier):
        return hmac.new(settings.secret.encode(), identifier.encode(), hashlib.sha256).hexdigest()

    cookie_name = "__Host-shop_visitor" if settings.production else COOKIE
    identifier, _, signature = request.cookies.get(cookie_name, "").partition(".")
    if re.fullmatch("[a-f0-9]{32}", identifier) and re.fullmatch("[a-f0-9]{64}", signature):
        if hmac.compare_digest(signature, sign(identifier)):
            return identifier
    identifier = uuid4().hex
    response.set_cookie(cookie_name, f"{identifier}.{sign(identifier)}", httponly=True,
                        secure=settings.production, samesite="strict", max_age=30 * 86400)
    return identifier


class RequestBoundary:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]
        headers = dict(scope["headers"])
        if self.settings.production and method in {"POST", "DELETE"}:
            if headers.get(b"origin") != self.settings.origin.encode():
                await JSONResponse({"detail": "请求来源不匹配"}, 403)(scope, receive, send)
                return

        async def send_with_headers(event):
            if event["type"] == "http.response.start":
                policy = [(b"x-content-type-options", b"nosniff"),
                          (b"referrer-policy", b"no-referrer"),
                          (b"x-frame-options", b"DENY"),
                          (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")]
                if path != "/docs" or self.settings.production:
                    policy.append((b"content-security-policy", CSP.encode()))
                if not path.startswith("/assets/"):
                    policy.append((b"cache-control", b"no-store"))
                else:
                    policy.append((b"cache-control", b"public, max-age=3600"))
                event["headers"] = [*event.get("headers", []), *policy]
            await send(event)

        if path.rstrip("/") == "/chat" and method == "POST":
            content_type = headers.get(b"content-type", b"").partition(b";")[0].strip().lower()
            if content_type != b"application/json":
                await JSONResponse({"detail": "只接受 JSON 请求"}, 415)(scope, receive, send_with_headers)
                return
            body = bytearray()
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                body.extend(event.get("body", b""))
                if len(body) > MAX_CHAT_BODY:
                    await JSONResponse({"detail": "请求体太大"}, 413)(scope, receive, send_with_headers)
                    return
                if not event.get("more_body"):
                    break

            async def buffered_receive():
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, buffered_receive, send_with_headers)
            return
        await self.app(scope, receive, send_with_headers)
