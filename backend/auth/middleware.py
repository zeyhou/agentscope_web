"""统一认证所有 HTTP 入口，给原有框架传递经过验证的用户身份。"""
from contextvars import ContextVar
from base64 import urlsafe_b64encode
import hmac
from http.cookies import CookieError, SimpleCookie
import re
from urllib.parse import parse_qsl, urlencode

from redis.exceptions import RedisError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .accounts import ACCOUNT_DB_ERRORS

AUTH_STORAGE_ERRORS = (RedisError, *ACCOUNT_DB_ERRORS)
current_storage_user: ContextVar[str | None] = ContextVar("current_storage_user", default=None)
PUBLIC = {("GET", "/auth/health"), ("GET", "/auth/ready"), ("POST", "/auth/register"), ("POST", "/auth/login")}


class IdentityMiddleware:
    def __init__(self, app, service):
        self.app, self.service = app, service

    def session_token(self, headers):
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("cookie", ""))
        except CookieError:
            return ""
        name = self.service.settings.cookie_name
        return cookie[name].value if name in cookie else ""

    async def realtime_asr(self, scope, receive, send):
        headers = Headers(scope=scope)
        if scope["path"] != "/asr/realtime" or headers.get("origin") not in self.service.settings.origins:
            await send({"type": "websocket.close", "code": 1008})
            return
        token = self.session_token(headers)
        try:
            auth = await self.service.authenticate(token) if token else None
        except AUTH_STORAGE_ERRORS:
            await send({"type": "websocket.close", "code": 1013})
            return
        if auth is None:
            await send({"type": "websocket.close", "code": 4401})
            return
        user_id = auth["account"]["storage_user_id"]
        query = dict(parse_qsl(scope.get("query_string", b"").decode("ascii", errors="replace")))
        parts = query.get("token", "").split(".")
        encoded_user = urlsafe_b64encode(user_id.encode()).rstrip(b"=")
        # The upstream ASR endpoint verifies the signature, expiry and model scope.
        if len(parts) != 3 or not hmac.compare_digest(parts[1].encode(), encoded_user):
            await send({"type": "websocket.close", "code": 1008})
            return
        scope = {**scope, "headers": [(k, v) for k, v in scope["headers"] if k.lower() != b"x-user-id"]}
        await self.app(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await self.realtime_asr(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        method, path = scope["method"], scope["path"].rstrip("/") or "/"
        headers = Headers(scope=scope)
        settings = self.service.settings
        public = (method, path) in PUBLIC
        token = self.session_token(headers) if not public or path == "/auth/login" else ""
        try:
            auth = await self.service.authenticate(token) if token else None
        except AUTH_STORAGE_ERRORS:
            await JSONResponse({"detail": "登录会话服务暂不可用。"}, 503)(scope, receive, send)
            return
        logout = method == "POST" and path == "/auth/logout"
        if not public and not logout and auth is None:
            await JSONResponse({"detail": "请先登录。"}, 401)(scope, receive, send)
            return
        if method not in ("GET", "HEAD", "OPTIONS"):
            if headers.get("origin") not in settings.origins:
                await JSONResponse({"detail": "请求来源不被允许。"}, 403)(scope, receive, send)
                return
            if public and headers.get("content-type", "").split(";")[0].lower() != "application/json":
                await JSONResponse({"detail": "请使用 JSON 请求。"}, 415)(scope, receive, send)
                return
            if not public and auth is not None and not hmac.compare_digest(
                headers.get("x-csrf-token", "").encode(), auth["session"]["csrf_token"].encode(),
            ):
                await JSONResponse({"detail": "请求验证失效，请刷新页面后重试。"}, 403)(scope, receive, send)
                return

        # 必须删除所有外部身份头；仅覆盖第一个同名头无法阻止重复头绕过。
        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"x-user-id"]
        scope["state"] = {**scope.get("state", {}), "auth": auth}
        user_id = auth["account"]["storage_user_id"] if auth else None
        if user_id is not None:
            scope["headers"].append((b"x-user-id", user_id.encode("utf-8")))

        native_file = path == "/workspace/files" or re.fullmatch(r"/knowledge_bases/[^/]+/documents/[^/]+", path)
        if native_file:
            # 两个框架原文接口会优先信任 URL Token；去除此参数后统一走上面的可信身份。
            query = parse_qsl(scope.get("query_string", b"").decode("utf-8"), keep_blank_values=True)
            scope["query_string"] = urlencode([(k, v) for k, v in query if k != "token"]).encode()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        marker = current_storage_user.set(user_id)
        try:
            await self.app(scope, receive, private_send)
        finally:
            current_storage_user.reset(marker)
