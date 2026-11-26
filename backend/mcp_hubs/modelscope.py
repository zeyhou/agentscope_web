"""魔搭 MCP 广场：读取公共目录，本地配置或用户提供的托管连接地址。"""

import re
from urllib.parse import quote, urlsplit

from agentscope.app.hub import HubError, MCPCard, MCPHubPage

from ._authenticated import AuthenticatedMCPHub, decode_id, encode_id
from ._icons import mcp_hub_icon
from .official import _Inputs, _Unsupported


def _standard_config(raw: dict, env_schema: dict) -> tuple[dict, dict] | None:
    """仅转换明确的标准 MCP 配置，不从 README 猜测启动命令。"""
    if "mcpServers" in raw:
        servers = raw["mcpServers"]
        if not isinstance(servers, dict) or len(servers) != 1:
            return None
        raw = next(iter(servers.values()))
    if not isinstance(raw, dict):
        return None
    inputs = _Inputs()
    properties = env_schema.get("properties") or {}
    if not isinstance(properties, dict) or not all(isinstance(spec, dict) for spec in properties.values()):
        return None
    required = set(env_schema.get("required") or [])
    bindings: dict[str, str] = {}

    def field(name: str, *, force_required: bool = False) -> str:
        spec = properties[name]
        needed = name in required or force_required
        if name not in bindings:
            # 魔搭真实目录未必标记密码格式，常见密钥名称也应使用密码输入。
            secret = spec.get("writeOnly") or spec.get("format") == "password" or bool(
                re.search(r"api.?key|token|secret|password|authorization|(?:^|_)key(?:_|$)", name, re.I)
            )
            bindings[name] = inputs.field({**spec, "isSecret": secret, "choices": spec.get("enum")}, name, required=needed)
        key = bindings[name][2:-1]
        if needed and key not in inputs.required:
            inputs.required.append(key)
        if needed:
            inputs.properties[key]["minLength"] = 1
        return bindings[name]

    def text(value: str, *, force_required: bool = True) -> str:
        # 同一变量在参数、URL、请求头和环境变量中共用一个表单字段。
        value = re.sub(r"\$\{([^{}]+)\}", r"{\1}", value).replace("$", "$$")

        def replace(match):
            name = match[1]
            if name in properties:
                return field(name, force_required=force_required)
            if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*", name):
                raise _Unsupported("配置包含未声明变量")
            return match[0]

        return re.sub(r"\{([^{}]+)\}", replace, value)

    try:
        if raw.get("command") and not raw.get("url"):
            command = raw["command"]
            args = raw.get("args") or []
            env = raw.get("env") or {}
            if not isinstance(command, str) or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                return None
            if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
                return None
            config = {"type": "stdio_mcp", "command": text(command), "args": [text(arg) for arg in args]}
            converted_env = {}
            for key, value in env.items():
                if key in properties:
                    # 空 env 值也是可配置输入，例如真实高德条目的 AMAP_MAPS_API_KEY。
                    converted_env[key] = field(key)
                else:
                    converted_env[key] = text(value, force_required=False)
            for name in properties:
                if name not in converted_env:
                    converted_env[name] = field(name)
            if converted_env:
                config["env"] = converted_env
            if raw.get("cwd"):
                if not isinstance(raw["cwd"], str):
                    return None
                config["cwd"] = raw["cwd"]
            return config, inputs.schema()
        if raw.get("url") and not raw.get("command"):
            url = raw["url"]
            if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
                return None
            kind = raw.get("type")
            if kind not in (None, "http_mcp", "sse", "streamable_http", "streamable-http"):
                return None
            sse = urlsplit(url).path.endswith(("/sse", "/messages/"))
            if kind == "sse" and not sse or kind in ("streamable_http", "streamable-http") and sse:
                return None
            config = {"type": "http_mcp", "url": text(url)}
            if raw.get("headers"):
                if not isinstance(raw["headers"], dict) or not all(isinstance(v, str) for v in raw["headers"].values()):
                    return None
                config["headers"] = {key: text(value) for key, value in raw["headers"].items()}
            return config, inputs.schema()
    except _Unsupported:
        return None
    return None


class ModelScopeMCPHub(AuthenticatedMCPHub):
    def __init__(self, *, api_token: str, base_url: str = "https://modelscope.cn/openapi/v1", timeout: float = 30.0):
        super().__init__(
            "modelscope", "ModelScope 魔搭 MCP 广场", "魔搭公共目录，最多浏览 100 条，可用搜索缩小范围；托管服务需填写自己的连接地址。",
            mcp_hub_icon("modelscope"), api_token=api_token, base_url=base_url, timeout=timeout,
        )

    def _data(self, payload: dict) -> dict:
        if payload.get("success") is not True or not isinstance(payload.get("data"), dict):
            raise HubError(self.hub_id, 502, "魔搭目录响应格式异常。")
        return payload["data"]

    def _card(self, item: dict, *, detail: bool = False) -> MCPCard:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise HubError(self.hub_id, 502, "魔搭条目缺少服务 ID。")
        localized = (item.get("locales") or {}).get("zh") or {}
        # 托管地址属于个人凭据，绝不使用目录 Token 所属账号的 operational_urls。
        config = {"type": "http_mcp", "url": "${MCP_URL}"}
        schema = {
            "type": "object", "properties": {"MCP_URL": {
                "type": "string", "title": "自己的 MCP 连接地址", "format": "password", "writeOnly": True,
                "pattern": r"^https?://\S+$",
                "description": "在魔搭详情页生成并复制自己的完整 /mcp 或 /sse 地址。需要额外认证头的连接请使用手动 MCP 配置。",
            }}, "required": ["MCP_URL"],
        }
        if detail:
            env_schema = item.get("env_schema") or {}
            for raw in item.get("server_config") or []:
                if isinstance(raw, dict) and (converted := _standard_config(raw, env_schema)):
                    config, schema = converted
                    break
        return MCPCard(
            hub_id=self.hub_id, id=encode_id(identifier),
            name=re.sub(r"[^a-zA-Z0-9_-]", "-", identifier.rsplit("/", 1)[-1]) or "modelscope-mcp",
            display_name=localized.get("name") or item.get("chinese_name") or item.get("name") or identifier,
            description=localized.get("description") or item.get("description") or "",
            tags=item.get("tags") or item.get("categories") or [], author=item.get("author") or item.get("publisher"),
            icon_url=item.get("logo_url"), url=f"https://modelscope.cn/mcp/servers/{quote(identifier, safe='/')}",
            readme=(localized.get("readme") or item.get("readme")) if detail else None,
            is_stateful=config["type"] == "stdio_mcp", auth="inputs" if schema else "none",
            inputs_schema=schema, config_template=config,
        )

    async def list_mcps(self, user_id: str, q: str | None = None, cursor: str | None = None, limit: int = 20) -> MCPHubPage:
        # OpenAPI 规定 page_number * page_size <= 100，游标携带页大小防止改变分页边界。
        size = max(1, min(limit, 100))
        page = 1
        if cursor:
            match = re.fullmatch(r"(\d+):(\d+)", cursor)
            if not match or not 1 <= int(match[2]) <= 100 or not 1 <= int(match[1]) * int(match[2]) <= 100:
                raise ValueError("无效的魔搭分页游标。")
            page, size = int(match[1]), int(match[2])
        body = {"page_number": page, "page_size": size}
        if q and q.strip():
            body["search"] = q.strip()
        # PUT 是该平台文档定义的列表查询，不是部署操作。
        data = self._data(await self._request("PUT", "/mcp/servers", json=body))
        if not isinstance(data.get("mcp_server_list"), list) or not isinstance(data.get("total_count"), int):
            raise HubError(self.hub_id, 502, "魔搭目录缺少列表或总数。")
        records = data["mcp_server_list"]
        more = records and page * size < data["total_count"] and (page + 1) * size <= 100
        return MCPHubPage(cards=[self._card(item) for item in records], next_cursor=f"{page + 1}:{size}" if more else None)

    async def get_mcp(self, user_id: str, card_id: str) -> MCPCard:
        identifier, = decode_id(card_id, 1)
        data = self._data(await self._request(
            "GET", f"/mcp/servers/{quote(identifier, safe='')}",
            params={"get_operational_url": "false"}, missing_key=card_id,
        ))
        card = self._card(data, detail=True)
        if card.id != card_id:
            raise KeyError(card_id)
        return card
