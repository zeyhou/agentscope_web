"""项目认证配置；所有相对文件路径都以 backend 为基准。"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=False, interpolate=False)


def business_redis_url() -> str:
    password = os.getenv("AGENTSCOPE_REDIS_PASSWORD")
    credentials = f":{quote(password, safe='')}@" if password else ""
    return os.getenv("AGENTSCOPE_REDIS_URL", f"redis://{credentials}localhost:6379/0")


def _auth_redis_url() -> str:
    return os.getenv("AUTH_REDIS_URL") or business_redis_url()


def backend_path(name: str, default: str) -> Path:
    return BACKEND_DIR / os.getenv(name, default)


@dataclass
class AuthSettings:
    mysql_url: str = field(default_factory=lambda: os.getenv("AUTH_MYSQL_URL", ""), repr=False)
    redis_url: str = field(default_factory=_auth_redis_url, repr=False)
    prefix: str = "agentscope-web:auth:v1:"
    session_ttl: int = field(default_factory=lambda: int(os.getenv("AUTH_SESSION_TTL", "43200")))
    secure_cookie: bool = field(default_factory=lambda: os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true")
    registration_open: bool = field(default_factory=lambda: os.getenv("AUTH_REGISTRATION_OPEN", "true").lower() == "true")
    origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        value.strip() for value in os.getenv("AUTH_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if value.strip()
    ))
    cookie_name: str = "agentscope_web_session"

    def __post_init__(self):
        if self.secure_cookie:
            self.cookie_name = "__Host-" + self.cookie_name
        if self.session_ttl <= 0 or not self.origins or "*" in self.origins:
            raise ValueError("认证需要正数会话有效期和明确的前端来源白名单。")
