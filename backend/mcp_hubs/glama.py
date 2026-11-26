"""Glama 远程连接器目录；当前自动安装仅覆盖无需服务端认证的连接器。"""

import re
from datetime import datetime
from urllib.parse import quote

from agentscope.app.hub import HubError, MCPCard, MCPHubPage

from ._authenticated import AuthenticatedMCPHub, decode_id, encode_id
from ._icons import mcp_hub_icon
from .official import _Inputs, _Unsupported, _remote


class GlamaMCPHub(AuthenticatedMCPHub):
    def __init__(self, *, api_token: str, base_url: str = "https://glama.ai/api/mcp", timeout: float = 30.0):
        super().__init__(
            "glama", "Glama", "Glama 远程 MCP 目录，当前提供无需服务端认证的连接器。",
            mcp_hub_icon("glama"), api_token=api_token, base_url=base_url, timeout=timeout,
        )

    def _card(self, item: dict, *, detail: bool = False) -> MCPCard | None:
        connection = item.get("connection") or {}
        # API Key 位置和 OAuth 配置未由此目录提供，不能猜测或混用目录 Key。
        if item.get("deprecatedAt") or item.get("healthy") is False or connection.get("authType") != "none":
            return None
        if connection.get("transport") != "streamable_http":
            return None
        namespace, slug, url = item.get("namespace"), item.get("slug"), item.get("url")
        if not all(isinstance(value, str) and value for value in (namespace, slug, url)):
            raise HubError(self.hub_id, 502, "Glama 条目缺少来源身份或回链。")
        if not url.startswith("https://glama.ai/mcp/connectors/"):
            raise HubError(self.hub_id, 502, "Glama 条目缺少有效的原始页面链接。")
        try:
            config = _remote({"type": "streamable-http", "url": connection.get("url")}, _Inputs())
        except _Unsupported:
            return None
        stamp = item.get("updatedAt")
        updated_at = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else None
        # 推广标记放在标签首位，列表和已安装资源均可见。
        tags = (["广告 / Ad"] if item.get("isBoosted") else []) + (item.get("attributes") or [])
        readme = None
        if detail:
            lines = [item.get("description") or ""]
            if item.get("documentationUrl"):
                lines.append(f"[服务文档]({item['documentationUrl']})")
            for tool in item.get("tools") or []:
                lines.append(f"### {tool['name']}\n\n{tool.get('description') or ''}")
            readme = "\n\n".join(lines)
        return MCPCard(
            hub_id=self.hub_id, id=encode_id(namespace, slug),
            name=re.sub(r"[^a-zA-Z0-9_-]", "-", slug) or "glama-mcp", display_name=item.get("name") or slug,
            description=item.get("description") or "", tags=tags, author=namespace,
            icon_url=item.get("thumbnailUrl"), url=url, readme=readme, updated_at=updated_at,
            is_stateful=False, auth="none", config_template=config,
        )

    async def list_mcps(self, user_id: str, q: str | None = None, cursor: str | None = None, limit: int = 20) -> MCPHubPage:
        params = {"first": max(1, min(limit, 100)), "sort": "recommended:desc", "attributes": "auth:none"}
        if q and q.strip():
            params["query"] = q.strip()
        if cursor:
            params["after"] = cursor
        payload = await self._request("GET", "/v1/connectors", params=params)
        if not isinstance(payload.get("connectors"), list) or not isinstance(payload.get("pageInfo"), dict):
            raise HubError(self.hub_id, 502, "Glama 目录列表或分页格式异常。")
        page = payload["pageInfo"]
        if page.get("hasNextPage") and not page.get("endCursor"):
            raise HubError(self.hub_id, 502, "Glama 声明存在下一页但没有返回游标。")
        return MCPHubPage(
            cards=[card for item in payload["connectors"] if (card := self._card(item)) is not None],
            next_cursor=page.get("endCursor") if page.get("hasNextPage") else None,
        )

    async def get_mcp(self, user_id: str, card_id: str) -> MCPCard:
        namespace, slug = decode_id(card_id, 2)
        payload = await self._request(
            "GET", f"/v1/connectors/{quote(namespace, safe='')}/{quote(slug, safe='')}", missing_key=card_id,
        )
        card = self._card(payload, detail=True)
        if card is None or card.id != card_id:
            raise KeyError(card_id)
        return card
