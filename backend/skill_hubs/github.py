"""将 GitHub 技能仓库适配为可浏览、可固定版本下载的 SkillHub。"""

import asyncio
import io
import re
import stat
import time
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

import frontmatter
import yaml

from agentscope.app.hub import HubError, SkillArchive, SkillCard, SkillHubPage

from ._http import HttpSkillHub


@dataclass
class _Snapshot:
    """归档和卡片索引必须来自同一个 commit，防止预览与下载内容漂移。"""

    archive: bytes
    cards: dict[str, SkillCard]
    files: dict[str, str]


class GitHubSkillHub(HttpSkillHub):
    """一个仓库对应一个来源；多个来源复用此实现。"""

    def __init__(
        self, hub_id: str, display_name: str, *, repo: str,
        skill_roots: tuple[str, ...] = ("skills",), ref: str = "main",
        description: str = "", icon_url: str | None = None,
        api_token: str | None = None, timeout: float = 60.0,
    ):
        super().__init__(hub_id, display_name, description, icon_url, timeout=timeout)
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError("GitHub repo 应使用 owner/repository 格式。")
        self.repo = repo
        self.skill_roots = tuple(root.strip("/") for root in skill_roots)
        self.ref = ref
        self.api_token = api_token
        self._snapshots: OrderedDict[str, _Snapshot] = OrderedDict()
        self._latest_sha: str | None = None
        self._checked_at = 0.0
        # 列表和详情可能同时到达；同一仓库只建立一次索引。
        self._lock = asyncio.Lock()

    async def _snapshot(self, version: str | None = None) -> tuple[str, _Snapshot]:
        if version is not None and not re.fullmatch(r"[0-9a-f]{40}", version):
            raise ValueError("GitHub 技能版本必须为完整 commit SHA。")
        async with self._lock:
            sha = version
            checked_at = None
            if sha is None:
                # 浏览缓存十分钟；旧版本下载始终按 SHA 定位，不受此缓存影响。
                if self._latest_sha is None or time.monotonic() - self._checked_at >= 600:
                    headers = {"Accept": "application/vnd.github+json"}
                    if self.api_token:
                        headers["Authorization"] = f"Bearer {self.api_token}"
                    response = await self._get(
                        f"https://api.github.com/repos/{self.repo}/commits/{quote(self.ref, safe='')}",
                        headers=headers,
                    )
                    sha = self._json(response).get("sha")
                    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                        raise HubError(self.hub_id, 502, "GitHub 未返回有效的 commit SHA。")
                    checked_at = time.monotonic()
                else:
                    sha = self._latest_sha
            if sha not in self._snapshots:
                # 下载公开仓库归档时不携带 GitHub Token。
                stream = await self._archive_stream(
                    f"https://codeload.github.com/{self.repo}/zip/{sha}",
                )
                data = b"".join([chunk async for chunk in stream])
                snapshot = await asyncio.to_thread(self._index, sha, data)
                self._snapshots[sha] = snapshot
                # 只缓存两个版本，避免连续更新仓库使服务内存持续增长。
                if len(self._snapshots) > 2:
                    self._snapshots.popitem(last=False)
            self._snapshots.move_to_end(sha)
            if version is None:
                self._latest_sha = sha
                if checked_at is not None:
                    self._checked_at = checked_at
            return sha, self._snapshots[sha]

    def _index(self, sha: str, data: bytes) -> _Snapshot:
        cards: dict[str, SkillCard] = {}
        files: dict[str, str] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 128 * 1024 * 1024:
                    raise HubError(self.hub_id, 502, "仓库解压后超过 128 MiB 上限。")
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    path = PurePosixPath(info.filename)
                    # 网络归档仅在内存中读取；重打包之前仍要拒绝路径穿越和符号链接。
                    if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                        raise HubError(self.hub_id, 502, "仓库归档包含不安全的路径。")
                    relative = PurePosixPath(*path.parts[1:])
                    files[str(relative)] = info.filename
                    if relative.name != "SKILL.md" or not any(
                        relative.parent.parent == PurePosixPath(root) for root in self.skill_roots
                    ):
                        continue
                    raw = archive.read(info).decode("utf-8-sig")
                    parsed = frontmatter.loads(raw)
                    name, description = parsed.get("name"), parsed.get("description")
                    if not isinstance(name, str) or not name or not isinstance(description, str) or not description:
                        raise HubError(self.hub_id, 502, f"{relative} 缺少有效 name 或 description。")
                    card_id = str(relative.parent)
                    metadata = parsed.get("metadata") or {}
                    cards[card_id] = SkillCard(
                        hub_id=self.hub_id, id=card_id, name=name, description=description,
                        version=sha, author=metadata.get("author") or self.repo.split("/")[0],
                        url=f"https://github.com/{self.repo}/tree/{sha}/{quote(card_id, safe='/')}",
                        markdown=parsed.content,
                        metadata={"repo": self.repo, "path": card_id, "license": parsed.get("license")},
                    )
        except (zipfile.BadZipFile, UnicodeError, ValueError, yaml.YAMLError) as exc:
            raise HubError(self.hub_id, 502, f"仓库技能归档或 SKILL.md 格式无效：{exc}") from exc
        if not cards:
            raise HubError(self.hub_id, 502, "配置的技能目录中没有找到有效 SKILL.md。")
        return _Snapshot(data, dict(sorted(cards.items())), files)

    async def list_skills(
        self, user_id: str, q: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> SkillHubPage:
        version, offset = None, 0
        if cursor is not None:
            match = re.fullmatch(r"([0-9a-f]{40}):(\d+)", cursor)
            if match is None:
                raise ValueError("无效的 GitHub 技能源分页游标。")
            version, offset = match[1], int(match[2])
        sha, snapshot = await self._snapshot(version)
        needle = (q or "").strip().casefold()
        cards = [card for card in snapshot.cards.values() if not needle or needle in
                 f"{card.name} {card.description} {card.id}".casefold()]
        end = offset + max(1, min(limit, 100))
        return SkillHubPage(
            # 浏览结果省略正文；不逐卡访问 GitHub 文件接口。
            cards=[card.model_copy(update={"markdown": None}) for card in cards[offset:end]],
            next_cursor=f"{sha}:{end}" if end < len(cards) else None,
        )

    async def get_skill(self, user_id: str, card_id: str) -> SkillCard:
        _, snapshot = await self._snapshot()
        if card_id not in snapshot.cards:
            raise KeyError(card_id)
        return snapshot.cards[card_id].model_copy(deep=True)

    def _pack(self, snapshot: _Snapshot, card_id: str) -> bytes:
        """只打包选中的技能，保留脚本、参考资料和资源，不执行其中的代码。"""
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(snapshot.archive)) as source, zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED,
        ) as target:
            for path, original in snapshot.files.items():
                if not path.startswith(f"{card_id}/"):
                    continue
                info = source.getinfo(original)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise HubError(self.hub_id, 502, f"技能包含无法直接安装的符号链接：{path}")
                # SKILL.md 放在压缩包根部，供框架直接识别。
                relative = path[len(card_id) + 1:]
                entry = zipfile.ZipInfo(relative)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = info.external_attr
                target.writestr(entry, source.read(original))
        return output.getvalue()

    async def download(
        self, user_id: str, card_id: str, version: str | None = None,
    ) -> SkillArchive:
        _, snapshot = await self._snapshot(version)
        if card_id not in snapshot.cards:
            raise KeyError(card_id)
        data = await asyncio.to_thread(self._pack, snapshot, card_id)

        async def chunks():
            for offset in range(0, len(data), 64 * 1024):
                yield data[offset:offset + 64 * 1024]

        return SkillArchive("zip", chunks())
