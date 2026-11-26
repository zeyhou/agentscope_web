"""通过 FastAPI 扩展点安装项目认证，不修改 AgentScope 源码。"""
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import AuthenticationError, RedisError

from .accounts import ACCOUNT_DB_ERRORS, AccountStore
from .config import AuthSettings
from .middleware import IdentityMiddleware
from .router import router
from .service import AuthService
from .sessions import LoginSessions


def install_auth(app, accounts: AccountStore, settings: AuthSettings, redis=None, *, business_pool=None):
    redis = redis if redis is not None else Redis.from_url(settings.redis_url, decode_responses=True)
    service = AuthService(accounts, LoginSessions(redis, settings), settings)
    app.state.auth_service = service
    app.state.business_redis = Redis(connection_pool=business_pool) if business_pool is not None else redis
    app.include_router(router)
    app.add_middleware(IdentityMiddleware, service=service)
    # 最后添加的中间件最先执行，让预检及认证错误都带上正确的 CORS 响应。
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins), allow_credentials=True,
                       allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "Range", "Accept"],
                       expose_headers=["Content-Disposition", "Content-Length", "Content-Range"])

    @app.exception_handler(RedisError)
    async def unavailable(_request, _error):
        return JSONResponse({"detail": "服务暂不可用，请稍后重试。"}, 503)

    for error_class in ACCOUNT_DB_ERRORS:
        app.add_exception_handler(error_class, unavailable)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # 默认校验错误可能包含原始请求；认证表单错误不能回显密码。
        if request.url.path.rstrip("/") in ("/auth/login", "/auth/register"):
            return JSONResponse({"detail": "请填写有效的用户名和密码。"}, 422)
        return await request_validation_exception_handler(request, error)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with AsyncExitStack() as stack:
            stack.push_async_callback(accounts.close)
            stack.push_async_callback(redis.aclose)
            if business_pool is not None:
                stack.push_async_callback(business_pool.aclose)
                try:
                    await application.state.business_redis.ping()
                except AuthenticationError:
                    raise RuntimeError(
                        "业务 Redis 认证失败。请检查 AGENTSCOPE_REDIS_URL 中的凭据，"
                        "或为默认本机 Redis 设置 AGENTSCOPE_REDIS_PASSWORD。"
                    ) from None
            await stack.enter_async_context(previous_lifespan(application))
            yield

    app.router.lifespan_context = lifespan
    return service
