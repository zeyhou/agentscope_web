"""两个需要目录凭据的 MCPHub 共用 HTTP 生命周期与单段 ID 编码。"""

import base64
import json
import re
from typing import Any

import httpx

from agentscope.app.hub import HubError, MCPHubBase


def encode_id(*parts: str) -> str:
    """上游名称可能包含斜杠，现有框架路由只接受单段卡片 ID。"""
    data = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def decode_id(card_id: str, size: int) -> list[str]:
    try:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", card_id):
            raise ValueError("无效编码")
        data = base64.b64decode(card_id + "=" * (-len(card_id) % 4), altchars=b"-_", validate=True)
        parts = json.loads(data.decode("utf-8"))
        if not isinstance(parts, list) or len(parts) != size or not all(isinstance(p, str) and p for p in parts):
            raise ValueError("无效来源身份")
        if encode_id(*parts) != card_id:
            raise ValueError("非规范编码")
        return parts
    except (ValueError, UnicodeError) as exc:
        raise KeyError(card_id) from exc


class AuthenticatedMCPHub(MCPHubBase):
    """目录 Token 只发给固定的目录 API，不进入 MCP 的连接配置或前端。"""

    def __init__(self, *args: Any, api_token: str, base_url: str, timeout: float = 30.0):
        super().__init__(*args)
        self.api_token = api_token.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            # 凭据仅按请求附加，避免连接池默认头被意外复用到其他地址。
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def __aenter__(self):
        self._http()
        return self

    async def __aexit__(self, *exc: Any):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, *, missing_key: str | None = None, **kwargs: Any) -> dict:
        if not self.api_token:
            raise HubError(self.hub_id, 401, f"尚未配置 {self.display_name} 的目录 API Token。")
        try:
            response = await self._http().request(
                method, f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.api_token}", "Accept": "application/json"},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            # 不回显请求或上游正文，其中可能包含凭据或个人连接地址。
            raise HubError(self.hub_id, 502, f"无法访问 {self.display_name} 目录。") from exc
        if response.status_code == 404 and missing_key is not None:
            raise KeyError(missing_key)
        if not response.is_success:
            message = {
                401: "目录认证失败，请检查后端 Token。",
                403: "目录访问被拒绝，请检查 Token 权限或平台访问限制。",
                429: "目录请求已限流，请稍后重试。",
            }.get(response.status_code, "目录请求失败。")
            raise HubError(self.hub_id, response.status_code, f"{self.display_name}：{message}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise HubError(self.hub_id, 502, "目录返回了无效 JSON。") from exc
        if not isinstance(payload, dict):
            raise HubError(self.hub_id, 502, "目录响应必须为 JSON 对象。")
        return payload
