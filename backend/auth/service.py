"""注册、密码校验及登录会话服务。"""
import asyncio
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException

from .accounts import username_key


class AuthService:
    def __init__(self, accounts, sessions, settings):
        self.accounts, self.sessions, self.settings = accounts, sessions, settings
        self.hasher = PasswordHasher()
        # Argon2 每次校验需要较多内存，限制多用户并发验证，避免挤占业务任务资源。
        self.password_slots = asyncio.Semaphore(4)
        # 未注册账号也执行一次密码校验，避免直接通过响应耗时判断账号是否存在。
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(24))

    async def register(self, username: str, password: str, ip: str):
        if not self.settings.registration_open:
            raise HTTPException(403, "当前未开放注册。")
        await self.sessions.limit("register", ip, 10, 3600)
        key = username_key(username)
        if not 3 <= len(key) <= 64 or not all(c.isalnum() or c in "_.-" for c in key):
            raise HTTPException(422, "用户名需为 3–64 个字母、数字、中文或 _.- 字符。")
        if not 8 <= len(password) <= 128:
            raise HTTPException(422, "密码长度需为 8–128 个字符。")
        async with self.password_slots:
            hashed = await asyncio.to_thread(self.hasher.hash, password)
        identifier = await self.accounts.create(username, hashed)
        return await self.accounts.get(identifier)

    async def login(self, username: str, password: str, ip: str):
        await self.sessions.limit("login-ip", ip, 60, 300)
        await self.sessions.limit("login-account", username_key(username), 10, 300)
        account = await self.accounts.get(username=username)
        try:
            async with self.password_slots:
                await asyncio.to_thread(self.hasher.verify, account["password_hash"] if account else self.dummy_hash, password)
        except (VerificationError, InvalidHashError) as error:
            raise HTTPException(401, "用户名或密码错误。") from error
        if account is None or not account["enabled"]:
            raise HTTPException(401, "用户名或密码错误。")
        token, session = await self.sessions.create(account["id"])
        return account, token, session

    async def authenticate(self, token: str):
        session = await self.sessions.get(token)
        if session is None:
            return None
        account = await self.accounts.get(session["account_id"])
        if account is None or not account["enabled"]:
            await self.sessions.revoke(token)
            return None
        return {"account": account, "session": session, "token": token}
