"""仅提供账号会话接口；模型 API Key 仍由原有凭据接口管理。"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr

from .accounts import public_account

router = APIRouter(prefix="/auth", tags=["账号认证"])


class Credentials(BaseModel):
    username: str
    password: SecretStr


@router.get("/health")
async def health(request: Request):
    return {"service": "agentscope-web", "authentication": "cookie-session",
            "registration_open": request.app.state.auth_service.settings.registration_open}


@router.get("/ready")
async def ready(request: Request):
    state = request.app.state
    await state.auth_service.accounts.check_ready()
    await state.auth_service.sessions.redis.ping()
    await state.business_redis.ping()
    return {"status": "ready"}


@router.post("/register", status_code=201)
async def register(body: Credentials, request: Request):
    service = request.app.state.auth_service
    account = await service.register(body.username, body.password.get_secret_value(), request.client.host)
    return {"user": public_account(account)}


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response):
    service = request.app.state.auth_service
    password = body.password.get_secret_value()
    if len(body.username) > 128 or len(password) > 128:
        raise HTTPException(401, "用户名或密码错误。")
    account, token, session = await service.login(body.username, password, request.client.host)
    previous = request.state.auth
    if previous is not None:
        # 同一浏览器重新登录时轮换旧会话，旧 Cookie 不应在切换账号后继续有效。
        await service.sessions.revoke(previous["token"])
    settings = service.settings
    response.set_cookie(settings.cookie_name, token, max_age=settings.session_ttl,
                        httponly=True, secure=settings.secure_cookie, samesite="lax", path="/")
    return {"user": public_account(account), "csrf_token": session["csrf_token"], "expires_at": session["expires_at"]}


@router.get("/me")
async def me(request: Request):
    auth = request.state.auth
    return {"user": public_account(auth["account"]), "csrf_token": auth["session"]["csrf_token"],
            "expires_at": auth["session"]["expires_at"]}


@router.post("/logout", status_code=204)
async def logout(request: Request):
    service, auth = request.app.state.auth_service, request.state.auth
    if auth is not None:
        await service.sessions.revoke(auth["token"])
        # 语音连接不再发起 HTTP 请求，因此登出时主动关闭该用户的已建立连接。
        connections = getattr(request.app.state, "realtime_connections", {})
        for key, runner in list(connections.items()):
            if key[0] == auth["account"]["storage_user_id"]:
                await runner.close()
    response = Response(status_code=204)
    response.delete_cookie(service.settings.cookie_name, path="/", secure=service.settings.secure_cookie,
                           httponly=True, samesite="lax")
    return response
