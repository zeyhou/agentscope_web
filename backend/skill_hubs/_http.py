"""两个外部技能源共用的 HTTP 生命周期和错误转换。"""

from typing import Any, AsyncIterator

import httpx

from agentscope.app.hub import HubError, SkillHubBase


class HttpSkillHub(SkillHubBase):
    """沿用框架的 Hub 生命周期，共享连接池，不在启动时访问外网。"""

    def __init__(self, *args: Any, timeout: float = 60.0, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "AgentScope-Web-SkillHubs"},
            )
        return self._client

    async def __aenter__(self):
        self._http()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _check(self, response: httpx.Response, missing_key: str | None) -> None:
        if response.status_code == 404 and missing_key is not None:
            raise KeyError(missing_key)
        if response.is_error:
            # 保留上游状态码（包括限流），交给框架统一转换，不能伪装成空列表。
            raise HubError(self.hub_id, response.status_code, response.text[:1000])

    async def _get(
        self, url: str, *, missing_key: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        try:
            response = await self._http().get(url, **kwargs)
        except httpx.HTTPError as exc:
            raise HubError(self.hub_id, 502, f"访问技能源失败：{exc}") from exc
        self._check(response, missing_key)
        return response

    def _json(self, response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise HubError(self.hub_id, 502, "技能源返回了无效 JSON。") from exc
        if not isinstance(payload, dict):
            raise HubError(self.hub_id, 502, "技能源返回的 JSON 应为对象。")
        return payload

    async def _archive_stream(
        self, url: str, *, missing_key: str | None = None, **kwargs: Any
    ) -> AsyncIterator[bytes]:
        """先校验响应状态，再返回有大小限制、会自动关闭连接的下载流。"""
        response = None
        try:
            request = self._http().build_request("GET", url, **kwargs)
            response = await self._http().send(request, stream=True)
            if response.is_error:
                await response.aread()
            self._check(response, missing_key)
        except httpx.HTTPError as exc:
            if response is not None:
                await response.aclose()
            raise HubError(self.hub_id, 502, f"打开技能下载失败：{exc}") from exc
        except BaseException:
            if response is not None:
                await response.aclose()
            raise
        return self._drain(response)

    async def _drain(self, response: httpx.Response) -> AsyncIterator[bytes]:
        total = 0
        try:
            async for chunk in response.aiter_bytes(64 * 1024):
                total += len(chunk)
                if total > 64 * 1024 * 1024:
                    raise HubError(self.hub_id, 502, "技能归档超过 64 MiB 下载上限。")
                yield chunk
        except httpx.HTTPError as exc:
            raise HubError(self.hub_id, 502, f"下载技能失败：{exc}") from exc
        finally:
            await response.aclose()
