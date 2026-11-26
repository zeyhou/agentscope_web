"""官方 MCP Registry v0.1 适配器，仅使用 AgentScope 公开接口。"""

import base64
import json
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from agentscope.app.hub import HubError, MCPCard, MCPHubBase, MCPHubPage

from ._icons import mcp_hub_icon


_VARIABLE = re.compile(r"\{([^{}]+)\}")
_OFFICIAL_META = "io.modelcontextprotocol.registry/official"
_LOGGER = logging.getLogger(__name__)


def _card_id(name: str, version: str) -> str:
    """框架 MCP 路由只接收单段 ID，使用无斜杠的编码保存服务名和版本。"""
    data = json.dumps([name, version], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class _Unsupported(ValueError):
    """某个连接方式无法转换时，尝试同一服务的其他连接方式。"""


class _Inputs:
    """将目录的输入定义转换成现有安装表单和 ${...} 模板。"""

    def __init__(self):
        self.properties: dict[str, dict] = {}
        self.required: list[str] = []

    def field(self, spec: dict, key: str, *, required: bool) -> str:
        # 原变量名可能包含连字符，统一生成 string.Template 可识别的字段名。
        name = re.sub(r"[^a-zA-Z0-9_]", "_", f"input_{key}")
        # 不同位置的同名参数不能意外共享值，尤其不能混用凭据。
        unique = name
        while unique in self.properties:
            unique += "_"
        prop = {"type": "string", "title": key, "description": spec.get("description") or ""}
        if spec.get("isSecret"):
            prop.update(writeOnly=True, format="password")
        if "default" in spec:
            prop["default"] = str(spec["default"])
        if spec.get("choices"):
            prop["enum"] = [str(choice) for choice in spec["choices"]]
        self.properties[unique] = prop
        if required:
            self.required.append(unique)
        return f"${{{unique}}}"

    def text(self, value: str, variables: dict, key: str) -> str:
        # 转义文字中的美元符号，只替换上游明确声明的 {变量}。
        literal = value.replace("$", "$$")
        replacements = {}
        for name, spec in variables.items():
            if f"{{{name}}}" not in value:
                continue
            replacements[name] = (
                str(spec["value"]).replace("$", "$$") if "value" in spec
                else self.field(spec, f"{key}_{name}", required=True)
            )
        def replace(match):
            if match[1] in replacements:
                return replacements[match[1]]
            if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*", match[1]):
                raise _Unsupported(f"占位符 {match[0]} 未声明输入定义")
            return match[0]

        return _VARIABLE.sub(replace, literal)

    def value(self, spec: dict, key: str, *, optional_env: bool = False) -> str | None:
        if "value" in spec:
            return self.text(str(spec["value"]), spec.get("variables") or {}, key)
        required = bool(spec.get("isRequired"))
        # 框架仅能动态省略未填的可选环境变量；其他可选参数无默认值时不写入模板。
        if not optional_env and not required and "default" not in spec:
            return None
        if spec.get("isRepeated"):
            raise _Unsupported("可重复输入暂不支持转换为单值安装表单")
        return self.field(spec, key, required=required)

    def schema(self) -> dict:
        if not self.properties:
            return {}
        result = {"type": "object", "properties": self.properties}
        if self.required:
            result["required"] = self.required
        return result


def _remote(remote: dict, inputs: _Inputs) -> dict:
    kind, url = remote.get("type"), remote.get("url")
    if kind not in ("streamable-http", "sse") or not isinstance(url, str):
        raise _Unsupported("不支持的远程传输方式")
    path = urlsplit(url).path
    is_sse_path = path.endswith("/sse") or path.endswith("/messages/")
    if urlsplit(url).scheme not in ("https", "http") or (kind == "sse") != is_sse_path:
        # 框架按路径选择 SSE；不能擅自改写服务端地址来伪装兼容。
        raise _Unsupported("URL 与框架的传输识别规则不兼容")
    config = {
        "type": "http_mcp",
        "url": inputs.text(url, remote.get("variables") or {}, "url"),
    }
    headers = {}
    for index, header in enumerate(remote.get("headers") or []):
        value = inputs.value(header, f"header_{index}_{header['name']}")
        if value is not None:
            headers[header["name"]] = value
    if headers:
        config["headers"] = headers
    return config


def _arguments(arguments: list[dict], inputs: _Inputs, prefix: str) -> list[str]:
    result = []
    for index, argument in enumerate(arguments):
        if argument.get("type") not in ("named", "positional"):
            raise _Unsupported("不支持的启动参数类型")
        label = argument.get("valueHint") or argument.get("name") or str(index)
        value = inputs.value(argument, f"{prefix}_{index}_{label}")
        if value is None:
            continue
        result.append(f"{argument['name']}={value}" if argument["type"] == "named" else value)
    return result


def _package(package: dict, inputs: _Inputs) -> dict:
    kind = package.get("registryType")
    runtime = {"npm": "npx", "pypi": "uvx"}.get(kind)
    if runtime is None or package.get("runtimeHint", runtime) != runtime:
        raise _Unsupported("第一批仅支持 npx/npm 和 uvx/PyPI")
    if (package.get("transport") or {}).get("type") != "stdio" or package.get("fileSha256"):
        raise _Unsupported("暂不支持本地 HTTP 服务或需要额外文件校验的安装包")
    registry = package.get("registryBaseUrl", "").rstrip("/")
    if registry and registry != {"npm": "https://registry.npmjs.org", "pypi": "https://pypi.org"}[kind]:
        raise _Unsupported("第一批仅支持标准 npm/PyPI 源")
    identifier, version = package.get("identifier"), package.get("version")
    if not isinstance(identifier, str) or not identifier or not isinstance(version, str) or not version:
        raise _Unsupported("缺少可固定的软件包名称或版本")
    # 用软件包自己的版本，而不是 Registry 条目的版本固定执行内容。
    spec = f"{identifier}@{version}"
    args = ["-y"] if runtime == "npx" else []
    args += _arguments(package.get("runtimeArguments") or [], inputs, "runtime")
    args += [spec]
    args += _arguments(package.get("packageArguments") or [], inputs, "package")
    env = {}
    for index, variable in enumerate(package.get("environmentVariables") or []):
        env[variable["name"]] = inputs.value(variable, f"env_{index}_{variable['name']}", optional_env=True)
    config = {"type": "stdio_mcp", "command": runtime, "args": args}
    if env:
        config["env"] = env
    return config


class OfficialRegistryMCPHub(MCPHubBase):
    """公开读取官方目录；浏览、详情和安装元数据均不会启动 MCP 进程。"""

    def __init__(
        self, hub_id: str = "official", display_name: str = "官方 MCP Registry", *,
        base_url: str = "https://registry.modelcontextprotocol.io", timeout: float = 30.0,
    ):
        super().__init__(
            hub_id, display_name, "MCP 官方服务目录，搜索词至少需要 3 个字符。",
            mcp_hub_icon("official"),
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._http()
        return self

    async def __aexit__(self, *exc: Any):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True,
                headers={"Accept": "application/json", "User-Agent": "AgentScope-Web-MCPHubs"},
            )
        return self._client

    async def _get(self, path: str, *, missing_key: str | None = None, **kwargs: Any) -> dict:
        try:
            response = await self._http().get(f"{self.base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise HubError(self.hub_id, 502, f"访问官方 MCP Registry 失败：{exc}") from exc
        if response.status_code == 404 and missing_key is not None:
            raise KeyError(missing_key)
        if response.is_error:
            raise HubError(self.hub_id, response.status_code, response.text[:1000])
        try:
            payload = response.json()
        except ValueError as exc:
            raise HubError(self.hub_id, 502, "官方目录返回了无效 JSON。") from exc
        if not isinstance(payload, dict):
            raise HubError(self.hub_id, 502, "官方目录响应必须为 JSON 对象。")
        return payload

    def _card(self, entry: dict) -> MCPCard | None:
        meta = (entry.get("_meta") or {}).get(_OFFICIAL_META) or {}
        # latest 仍可能已弃用，只有 active 状态的条目才提供安装。
        if meta.get("status") != "active":
            return None
        server = entry.get("server") or {}
        name, version = server.get("name"), server.get("version")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", name):
            raise HubError(self.hub_id, 502, "官方目录缺少有效服务名称。")
        if not isinstance(version, str) or not version or version == "latest":
            raise HubError(self.hub_id, 502, "官方目录缺少可固定的服务版本。")
        # 优先标准远程 HTTP，其次 SSE，再尝试本地软件包。
        remotes = sorted(server.get("remotes") or [], key=lambda item: item.get("type") != "streamable-http")
        candidates = [(_remote, remote) for remote in remotes]
        candidates += [(_package, package) for package in server.get("packages") or []]
        config, inputs = None, None
        for build, candidate in candidates:
            candidate_inputs = _Inputs()
            try:
                config = build(candidate, candidate_inputs)
                inputs = candidate_inputs
                break
            except _Unsupported as exc:
                _LOGGER.debug("跳过 %s 的一种 MCP 连接方式：%s", name, exc)
        if config is None or inputs is None:
            return None
        stamp = meta.get("updatedAt")
        try:
            updated_at = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else None
        except (ValueError, AttributeError):
            updated_at = None
        icons = server.get("icons") or []
        schema = inputs.schema()
        return MCPCard(
            hub_id=self.hub_id,
            id=_card_id(name, version),
            name=re.sub(r"[^a-zA-Z0-9_-]", "-", name.split("/")[-1]),
            display_name=server.get("title") or name,
            description=server.get("description") or "", version=version, updated_at=updated_at,
            author=name.split("/")[0], icon_url=icons[0].get("src") if icons else None,
            url=server.get("websiteUrl") or (server.get("repository") or {}).get("url")
            or f"{self.base_url}/?search={quote(name, safe='')}",
            is_stateful=config["type"] == "stdio_mcp", auth="inputs" if schema else "none",
            inputs_schema=schema, config_template=config,
        )

    async def list_mcps(
        self, user_id: str, q: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> MCPHubPage:
        query = (q or "").strip()
        # 官方 API 拒绝不足三个字符的搜索；等待输入完成，不发出无效请求。
        if query and len(query) < 3:
            return MCPHubPage(cards=[])
        params = {"version": "latest", "limit": max(1, min(limit, 100))}
        if query:
            params["search"] = query
        if cursor:
            params["cursor"] = cursor
        payload = await self._get("/v0.1/servers", params=params)
        if not isinstance(payload.get("servers"), list):
            raise HubError(self.hub_id, 502, "官方目录响应缺少 servers 列表。")
        cards = [card for entry in payload["servers"] if (card := self._card(entry)) is not None]
        return MCPHubPage(
            cards=cards, next_cursor=(payload.get("metadata") or {}).get("nextCursor"),
        )

    async def get_mcp(self, user_id: str, card_id: str) -> MCPCard:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", card_id):
            raise KeyError(card_id)
        try:
            data = base64.b64decode(card_id + "=" * (-len(card_id) % 4), altchars=b"-_", validate=True)
            identity = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise KeyError(card_id) from exc
        if not isinstance(identity, list) or len(identity) != 2 or not all(isinstance(item, str) and item for item in identity):
            raise KeyError(card_id)
        name, version = identity
        path = f"/v0.1/servers/{quote(name, safe='')}/versions/{quote(version, safe='')}"
        card = self._card(await self._get(path, missing_key=card_id))
        if card is None or card.id != card_id:
            raise KeyError(card_id)
        return card
