"""用户目录和文件接口边界；本地 Shell 仍使用宿主机权限，并非执行沙箱。"""
import asyncio
import hashlib
import os
from pathlib import Path
import re
import time

from fastapi import HTTPException

from agentscope.app.workspace_manager import WorkspaceManagerBase
from agentscope.mcp import MCPClient
from agentscope.tool._builtin._backend import LocalBackend
from agentscope.workspace import LocalWorkspace

from .middleware import current_storage_user


class UserFileBackend(LocalBackend):
    def __init__(self, root: Path):
        self.root = root.resolve()
        super().__init__(workdir=str(self.root))

    def checked(self, path: str) -> str:
        target = Path(path)
        # 先做不访问磁盘的词法边界检查，避免对外部盘符或 UNC 路径发起解析。
        target = Path(os.path.abspath(target if target.is_absolute() else self.root / target))
        if not target.is_relative_to(self.root):
            raise HTTPException(403, "路径超出当前用户工作区。")
        target = target.resolve()
        if not target.is_relative_to(self.root):
            raise HTTPException(403, "路径超出当前用户工作区。")
        return str(target)

    def abspath(self, path: str, *, cwd: str) -> str:
        return self.checked(super().abspath(path, cwd=self.checked(cwd)))

    async def getcwd(self):
        return str(self.root)

    async def expanduser(self, path):
        return self.checked(await super().expanduser(path))

    async def exec_shell(self, command, *, cwd=None, **kwargs):
        return await super().exec_shell(command, cwd=self.checked(cwd or str(self.root)), **kwargs)

    async def read_file(self, path):
        return await super().read_file(self.checked(path))

    async def write_file(self, path, data):
        return await super().write_file(self.checked(path), data)

    async def write_stream(self, path, stream):
        return await super().write_stream(self.checked(path), stream)

    async def read_stream(self, path, *args, **kwargs):
        async for chunk in super().read_stream(self.checked(path), *args, **kwargs):
            yield chunk

    async def file_exists(self, path):
        return await super().file_exists(self.checked(path))

    async def is_dir(self, path):
        return await super().is_dir(self.checked(path))

    async def list_dir(self, path, **kwargs):
        return await super().list_dir(self.checked(path), **kwargs)

    async def scandir(self, path):
        return await super().scandir(self.checked(path))

    async def stat(self, path):
        return await super().stat(self.checked(path))

    async def stat_mtime(self, path):
        return await super().stat_mtime(self.checked(path))

    async def delete_path(self, path):
        return await super().delete_path(self.checked(path))


class UserLocalWorkspace(LocalWorkspace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 只替换此工作区实例的文件后端，不修改框架类或全局实现。
        self._backend = UserFileBackend(Path(self.workdir))


class UserWorkspaceManager(WorkspaceManagerBase):
    def __init__(self, basedir: Path, accounts, default_mcps=(), ttl=3600):
        super().__init__()
        self.basedir, self.accounts = basedir.resolve(), accounts
        self.default_mcps, self.ttl = default_mcps, ttl
        self._cache = {}
        self._lock = asyncio.Lock()

    async def get_workspace(self, user_id, agent_id, session_id, workspace_id=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", agent_id):
            raise HTTPException(400, "智能体标识不合法。")
        workspace_id = workspace_id or await self.assign_workspace_id(
            user_id=user_id, agent_id=agent_id, session_id=session_id,
        )
        # 显式 workspace_id 也只能命中当前用户的缓存，不能借用其他用户实例。
        key = (user_id, workspace_id)
        async with self._lock:
            now = time.monotonic()
            for stale, (workspace, seen) in list(self._cache.items()):
                if now - seen > self.ttl:
                    del self._cache[stale]
                    await workspace.close()
            if key not in self._cache:
                root = await self.accounts.legacy_root(user_id, agent_id)
                if root is None:
                    namespace = hashlib.sha256(user_id.encode()).hexdigest()[:32]
                    root = self.basedir / "_users" / namespace / agent_id
                root = root.resolve()
                if not root.is_relative_to(self.basedir):
                    raise HTTPException(403, "工作区目录不合法。")
                # 每个工作区都有独立客户端对象，有状态 MCP 不跨用户共享连接。
                defaults = [MCPClient(name=c.name, is_stateful=c.is_stateful,
                                      mcp_config=c.mcp_config.model_copy(deep=True)) for c in self.default_mcps]
                workspace = UserLocalWorkspace(workdir=str(root), workspace_id=workspace_id, default_mcps=defaults)
                await workspace.initialize()
            else:
                workspace, _ = self._cache[key]
            self._cache[key] = (workspace, now)
            return workspace

    async def close(self, workspace_id):
        # 框架 close 接口没有 user_id；请求上下文限定只关闭当前用户的缓存。
        owner = current_storage_user.get()
        for key, (workspace, _) in list(self._cache.items()):
            if key[1] == workspace_id and (owner is None or key[0] == owner):
                del self._cache[key]
                await workspace.close()

    async def close_all(self):
        workspaces = list(self._cache.values())
        self._cache.clear()
        for workspace, _ in workspaces:
            await workspace.close()
