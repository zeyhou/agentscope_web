import asyncio
import os
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agentscope.rag import QdrantStore
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from auth.accounts import AccountStore
from auth.config import AuthSettings, business_redis_url
from auth.workspaces import UserFileBackend


class StorageTests(unittest.TestCase):
    def test_business_and_auth_redis_configuration(self):
        with patch.dict(os.environ, {"AGENTSCOPE_REDIS_URL": "redis://localhost:6379/3", "AUTH_REDIS_URL": ""}):
            self.assertEqual(AuthSettings().redis_url, business_redis_url())
            with patch.dict(os.environ, {"AUTH_REDIS_URL": "redis://localhost:6379/4"}):
                self.assertEqual(AuthSettings().redis_url, "redis://localhost:6379/4")
                self.assertEqual(business_redis_url(), "redis://localhost:6379/3")

    def test_user_file_backend_reads_inside_workspace(self):
        async def check(path):
            root = path / "user"
            root.mkdir()
            files = UserFileBackend(root)
            await files.write_file("sample.txt", b"workspace")
            self.assertEqual(await files.read_file("sample.txt"), b"workspace")
            with self.assertRaises(HTTPException) as error:
                await files.read_file("../sample.txt")
            self.assertEqual(error.exception.status_code, 403)

        with TemporaryDirectory() as tmp:
            asyncio.run(check(Path(tmp)))

    def test_qdrant_collection_survives_reopen(self):
        async def check(path):
            async with QdrantStore(path=path) as store:
                await store.create_collection("test", dimensions=2)
            async with QdrantStore(path=path) as reopened:
                self.assertTrue(await reopened.has_collection("test"))

        with TemporaryDirectory() as tmp:
            asyncio.run(check(tmp))


@unittest.skipUnless(os.getenv("AGENTSCOPE_TEST_MYSQL_URL"), "requires a dedicated MySQL test database")
class MySQLAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalization_and_legacy_binding_rollback(self):
        store = AccountStore(os.environ["AGENTSCOPE_TEST_MYSQL_URL"])
        self.addAsyncCleanup(store.close)
        await store.init_schema()
        await store.check_ready()
        prefix = token_hex(5)
        first, duplicate = await asyncio.gather(
            store.create(f"{prefix}café", "test-hash"),
            store.create(f"{prefix}ＣＡＦÉ", "test-hash"),
            return_exceptions=True,
        )
        accepted = next(result for result in (first, duplicate) if isinstance(result, str))
        conflict = next(result for result in (first, duplicate) if isinstance(result, HTTPException))
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual((await store.get(username=f"{prefix}café"))["id"], accepted)
        second = await store.create(f"{prefix}cafe", "test-hash")

        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "旧工作区"
            await store.bind_legacy(accepted, f"{prefix}-First", {"agent": folder})
            self.assertEqual(await store.legacy_root(f"{prefix}-First", "agent"), folder)
            self.assertIsNone(await store.legacy_root(f"{prefix}-first", "agent"))
            with self.assertRaises(ValueError):
                await store.bind_legacy(second, f"{prefix}-second", {"agent": folder})
            self.assertEqual((await store.get(second))["storage_user_id"], second)


@unittest.skipUnless(os.getenv("AGENTSCOPE_TEST_REDIS_URL") and os.getenv("AGENTSCOPE_TEST_MYSQL_URL"),
                     "requires dedicated MySQL and Redis test instances")
class ApplicationTests(unittest.TestCase):
    def test_application_login_and_resource_isolation(self):
        from agentscope.app._service import sign_download_token

        origin = "http://localhost:5173"
        auth_headers = {"Origin": origin}
        redis_url = os.environ["AGENTSCOPE_TEST_REDIS_URL"]
        mysql_url = os.environ["AGENTSCOPE_TEST_MYSQL_URL"]

        async def init_schema():
            store = AccountStore(mysql_url)
            try:
                await store.init_schema()
            finally:
                await store.close()

        asyncio.run(init_schema())

        with TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "AUTH_MYSQL_URL": mysql_url,
            "AUTH_REDIS_URL": redis_url,
            "AGENTSCOPE_REDIS_URL": redis_url,
            "AUTH_ALLOWED_ORIGINS": origin,
            "AGENTSCOPE_QDRANT_PATH": str(Path(tmp) / "qdrant"),
            "AGENTSCOPE_QDRANT_URL": "",
            "AGENTSCOPE_BLOB_DIR": str(Path(tmp) / "blobs"),
            "AGENTSCOPE_WORKSPACES_DIR": str(Path(tmp) / "workspaces"),
            "AUTH_COOKIE_SECURE": "false",
            "AUTH_REGISTRATION_OPEN": "true",
        }):
            from main import app

            with TestClient(app) as client:
                self.assertEqual(client.get("/auth/ready").status_code, 200)
                self.assertEqual(client.get("/agent/", headers={"X-User-ID": "spoofed"}).status_code, 401)
                # These handlers belong to the pinned upstream revision.
                paths = app.openapi()["paths"]
                self.assertIn("/chat/submissions", paths)
                self.assertIn("/asr/transcriptions", paths)
                self.assertIn("/background-tasks", paths)

                for index in (1, 2):
                    username = f"test-{token_hex(5)}"
                    body = {"username": username, "password": "test-only-password"}
                    self.assertEqual(client.post("/auth/register", json=body, headers=auth_headers).status_code, 201)
                    login = client.post("/auth/login", json=body, headers=auth_headers)
                    self.assertEqual(login.status_code, 200)
                    self.assertEqual(client.get("/auth/me").json()["user"]["username"], username)
                    headers = {**auth_headers, "X-CSRF-Token": login.json()["csrf_token"]}
                    if index == 1:
                        first_id = login.json()["user"]["id"]
                        created = client.post("/agent/", json={"name": "Test agent"}, headers=headers)
                        self.assertLess(created.status_code, 300, created.text)
                        self.assertEqual(client.get("/agent/").json()["total"], 1)
                    else:
                        self.assertEqual(client.get("/agent/", headers={"X-User-ID": first_id}).json()["total"], 0)
                        second_id = login.json()["user"]["id"]
                        current_token, _ = sign_download_token(app.state.download_secret, second_id, "/asr/realtime/id/model")
                        with client.websocket_connect(f"/asr/realtime?token={current_token}", headers=auth_headers) as socket:
                            socket.send_json({"type": "start"})
                            self.assertEqual(socket.receive_json()["type"], "error")
                        token, _ = sign_download_token(app.state.download_secret, first_id, "/asr/realtime/id/model")
                        with self.assertRaises(WebSocketDisconnect):
                            with client.websocket_connect(f"/asr/realtime?token={token}", headers=auth_headers):
                                self.fail("accepted a token issued to a different account")
                        self.assertEqual(client.post("/auth/logout", headers=auth_headers).status_code, 403)
                        self.assertEqual(client.post("/auth/logout", headers=headers).status_code, 204)
                        self.assertEqual(client.get("/auth/me").status_code, 401)
