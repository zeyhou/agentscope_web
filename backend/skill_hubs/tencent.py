"""腾讯 SkillHub：将页码接口、发布者命名空间转换成框架的技能接口。"""

from datetime import datetime
from urllib.parse import quote

import frontmatter
import yaml

from agentscope.app.hub import HubError, SkillArchive, SkillCard, SkillHubPage

from ._http import HttpSkillHub
from ._icons import skill_hub_icon


class TencentSkillHub(HttpSkillHub):
    """使用腾讯公开读取接口，无须安装 SkillHub CLI 或配置登录凭据。"""

    def __init__(
        self,
        hub_id: str = "tencent-skillhub",
        display_name: str = "腾讯 SkillHub",
        *,
        base_url: str = "https://api.skillhub.cn",
        icon_url: str | None = None,
        timeout: float = 60.0,
    ):
        super().__init__(
            hub_id, display_name, "腾讯技能市场，提供中文技能发现和下载。",
            icon_url or skill_hub_icon("tencent-skillhub"), timeout=timeout,
        )
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _identity(card_id: str) -> tuple[str, dict[str, str]]:
        namespace, separator, slug = card_id.rpartition("/")
        if not separator or not namespace or not slug or "/" in namespace:
            raise KeyError(card_id)
        return slug, {"namespace": namespace}

    def _card(self, item: dict) -> SkillCard:
        namespace = item.get("namespace") or {}
        handle = namespace.get("handle")
        slug = namespace.get("publicSlug") or item.get("slug")
        if not handle or not slug:
            raise HubError(self.hub_id, 502, "腾讯技能缺少 slug 或发布者 namespace。")
        stats = item.get("stats") or item
        latest = item.get("latestVersion") or {}
        version = latest.get("version") or item.get("version")
        stamp = item.get("updatedAt") or item.get("updated_at")
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        elif stamp is not None:
            stamp = float(stamp)
            if stamp > 100_000_000_000:
                stamp /= 1000  # 腾讯使用毫秒，前端和框架约定为秒。
        tags = item.get("tags") or []
        if isinstance(tags, dict):
            tags = list(tags)
        return SkillCard(
            hub_id=self.hub_id,
            id=f"{handle}/{slug}",
            name=slug,
            display_name=item.get("displayName") or item.get("name") or slug,
            description=item.get("summary_zh") or item.get("description_zh")
            or item.get("summary") or item.get("description") or "",
            author=handle,
            version=str(version) if version is not None else None,
            updated_at=stamp,
            icon_url=item.get("iconUrl"),
            installs=stats.get("installs"),
            downloads=stats.get("downloads"),
            tags=tags,
            url=f"https://skillhub.cn/{quote(handle, safe='')}/{quote(slug, safe='')}",
            metadata={"namespace": handle, "source": item.get("source")},
        )

    async def list_skills(
        self, user_id: str, q: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> SkillHubPage:
        # 将外部页码封装成框架的游标；搜索也使用同一套分页。
        if cursor is not None and (not cursor.isdecimal() or int(cursor) < 1):
            raise ValueError("无效的腾讯 SkillHub 分页游标。")
        page = int(cursor) if cursor else 1
        limit = max(1, min(limit, 100))
        params = {"page": page, "pageSize": limit}
        if q and q.strip():
            params["keyword"] = q.strip()
        payload = self._json(await self._get(f"{self.base_url}/api/skills", params=params))
        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            raise HubError(self.hub_id, 502, payload.get("message") or "腾讯技能列表格式异常。")
        data = payload["data"]
        records = data.get("skills")
        if not isinstance(records, list) or not isinstance(data.get("total"), int):
            raise HubError(self.hub_id, 502, "腾讯技能列表缺少 skills 或 total。")
        return SkillHubPage(
            cards=[self._card(item) for item in records],
            next_cursor=str(page + 1) if records and page * limit < data["total"] else None,
        )

    async def get_skill(self, user_id: str, card_id: str) -> SkillCard:
        slug, params = self._identity(card_id)
        path = f"{self.base_url}/api/v1/skills/{quote(slug, safe='')}"
        payload = self._json(await self._get(path, params=params, missing_key=card_id))
        item = dict(payload.get("skill") or {})
        item["namespace"] = payload.get("namespace")
        item["latestVersion"] = payload.get("latestVersion")
        card = self._card(item)
        file_params = {**params, "path": "SKILL.md"}
        if card.version:
            file_params["version"] = card.version
        response = await self._get(f"{path}/file", params=file_params, missing_key=card_id)
        try:
            parsed = frontmatter.loads(response.text.removeprefix("\ufeff"))
        except (ValueError, yaml.YAMLError) as exc:
            raise HubError(self.hub_id, 502, "腾讯技能的 SKILL.md 格式无效。") from exc
        # 详情按实际技能声明取名，确保技能库与工作区中的名称一致。
        if not parsed.get("name") or not parsed.get("description"):
            raise HubError(self.hub_id, 502, "该技能缺少 name 或 description，无法加入工作区。")
        card.name = str(parsed["name"])
        card.markdown = parsed.content
        return card

    async def download(
        self, user_id: str, card_id: str, version: str | None = None,
    ) -> SkillArchive:
        slug, params = self._identity(card_id)
        params["slug"] = slug
        if version is not None:
            params["version"] = version  # 使用技能库记录的版本，不重新解析 latest。
        stream = await self._archive_stream(
            f"{self.base_url}/api/v1/download", params=params, missing_key=card_id,
        )
        return SkillArchive("zip", stream)
