"""Redis 登录会话和认证请求限流，不复用业务会话的存储键。"""
import hashlib
import json
import secrets
import time

from fastapi import HTTPException


class LoginSessions:
    def __init__(self, redis, settings):
        self.redis, self.settings = redis, settings

    def key(self, token: str):
        return self.settings.prefix + "session:" + hashlib.sha256(token.encode()).hexdigest()

    async def create(self, account_id: str):
        token = secrets.token_urlsafe(32)
        data = {"account_id": account_id, "csrf_token": secrets.token_urlsafe(32),
                "expires_at": int(time.time()) + self.settings.session_ttl}
        # Redis 中只保存高熵登录 Token 的哈希索引；密码使用独立的 Argon2id。
        await self.redis.set(self.key(token), json.dumps(data), ex=self.settings.session_ttl)
        return token, data

    async def get(self, token: str):
        raw = await self.redis.get(self.key(token)) if token else None
        return json.loads(raw) if raw else None

    async def revoke(self, token: str):
        if token:
            await self.redis.delete(self.key(token))

    async def limit(self, scope: str, value: str, maximum: int, seconds: int):
        key = self.settings.prefix + "limit:" + scope + ":" + hashlib.sha256(value.encode()).hexdigest()
        # Lua 保证首次计数和设置 TTL 原子完成，避免留下不会过期的限流键。
        count = await self.redis.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1, key, seconds,
        )
        if count > maximum:
            raise HTTPException(429, "请求过于频繁，请稍后重试。")
