# -*- coding: utf-8 -*-
"""The example script to start the agent service."""
import os

import uvicorn
from redis.asyncio import ConnectionPool

from agentscope.app import create_app, SubAgentTemplate
from agentscope.app.channel import (
    DingTalkChannel,
    DiscordChannel,
    FeishuChannel,
)
from agentscope.app.hub import ClawSkillHub
from agentscope.app.message_bus import InMemoryMessageBus
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager
from agentscope.app.rag.blob_store import LocalBlobStore
from agentscope.app.storage import RedisStorage
from agentscope.mcp import MCPClient, StdioMCPConfig, HttpMCPConfig
from agentscope.middleware import AgenticMemoryMiddleware, MiddlewareBase
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.rag import ApproxTokenChunker, QdrantStore
from agentscope.workspace import WorkspaceBase

from mcp_hubs import configured_mcp_hubs
from skill_hubs import GitHubSkillHub, TencentSkillHub, skill_hub_icon
from providers import SiliconFlowCredential, ZaiCodingCredential
from auth import AccountStore, AuthSettings, install_auth
from auth.config import backend_path, business_redis_url
from auth.workspaces import UserWorkspaceManager

default_mcps = [
    MCPClient(
        name="playwright",
        mcp_config=StdioMCPConfig(
            command="npx",
            args=["@playwright/mcp@latest"],
        ),
        is_stateful=True,
    ),
]

if os.getenv("AMAP_API_KEY"):
    default_mcps.append(
        MCPClient(
            name="amap",
            mcp_config=HttpMCPConfig(
                url=f"https://mcp.amap.com/mcp?key="
                f"{os.environ['AMAP_API_KEY']}",
            ),
            is_stateful=False,
        ),
    )

auth_settings = AuthSettings()
auth_accounts = AccountStore(auth_settings.mysql_url)
business_pool = ConnectionPool.from_url(business_redis_url(), decode_responses=True)
storage = RedisStorage(connection_pool=business_pool)

qdrant_url = os.getenv("AGENTSCOPE_QDRANT_URL")
vector_store = (
    QdrantStore(url=qdrant_url, api_key=os.getenv("AGENTSCOPE_QDRANT_API_KEY"))
    if qdrant_url
    else QdrantStore(path=str(backend_path("AGENTSCOPE_QDRANT_PATH", "data/qdrant")))
)


async def longterm_memory_factory(
    user_id: str,
    agent_id: str,
    session_id: str,
    workspace: WorkspaceBase,
) -> list[MiddlewareBase]:
    """Attach Markdown-file long-term memory, stored under the session's
    workspace so it is reachable through whichever backend is bound."""
    del user_id, agent_id, session_id
    return [
        AgenticMemoryMiddleware(
            workdir=workspace.workdir,
            backend=workspace.get_backend(),
        ),
    ]


app = create_app(
    storage=storage,
    # 项目级凭据扩展：由框架生成表单 Schema，并用于模型目录和会话调用。
    extra_credentials=[ZaiCodingCredential, SiliconFlowCredential],
    message_bus=InMemoryMessageBus(),
    # -- 若要改用基于 Redis 的消息总线（推荐用于
    # -- 多进程 / 生产环境部署），请取消下面几行的注释，
    # -- 并用其替换上方的 InMemoryMessageBus()：
    #
    # from agentscope.app.message_bus import RedisMessageBus
    # message_bus=RedisMessageBus(
    #     host="localhost",
    #     port=6379,
    # ),
    workspace_manager=UserWorkspaceManager(
        basedir=backend_path("AGENTSCOPE_WORKSPACES_DIR", "workspaces"),
        accounts=auth_accounts,
        default_mcps=default_mcps,
    ),
    blob_store=LocalBlobStore(root_dir=str(backend_path("AGENTSCOPE_BLOB_DIR", "blobs"))),
    # CollectionPerKbManager 会为每个知识库分配一个独立的集合，
    # 因此允许任意维度的向量嵌入。
    knowledge_base_manager=CollectionPerKbManager(
        storage=storage,
        vector_store=vector_store,
    ),
    # 用户在创建知识库时可以选择的分块器（chunker）类；
    # 所选的类型和参数会在知识库创建时被固定下来。
    knowledge_chunkers=[ApproxTokenChunker],
    # GitHub 和官方目录始终保留；魔搭、Glama 在配置后端目录 Token 后启用。
    # 目录 Token 不作为具体 MCP 的连接凭据，安装参数仍由用户在表单中填写。
    mcp_hubs=configured_mcp_hubs(),
    # 每个来源使用稳定且唯一的 hub_id；新增适配器完全放在本项目 backend 中。
    skill_hubs=[
        # 图标随项目内置，侧栏和来源面板均复用框架返回的 icon_url。
        ClawSkillHub(
            api_token=os.getenv("CLAWHUB_API_TOKEN"),
            icon_url=skill_hub_icon("clawhub"),
        ),
        TencentSkillHub(),
        GitHubSkillHub(
            hub_id="anthropic-skills",
            display_name="Anthropic Skills",
            repo="anthropics/skills",
            description="Anthropic 官方技能：文档处理、开发与通用任务。",
            icon_url=skill_hub_icon("anthropic-skills"),
            api_token=os.getenv("GITHUB_SKILLS_TOKEN"),
        ),
        GitHubSkillHub(
            hub_id="vercel-skills",
            display_name="Vercel Agent Skills",
            repo="vercel-labs/agent-skills",
            description="Vercel 官方技能：React、前端性能与网页设计规范。",
            icon_url=skill_hub_icon("vercel-skills"),
            api_token=os.getenv("GITHUB_SKILLS_TOKEN"),
        ),
    ],

    # 自定义你自己的子智能体模板
    custom_subagent_templates=[
        SubAgentTemplate(
            type="explorer",
            description=(
                "Read-only agents specialized in exploration tasks. It can "
                "read files but cannot modify, create, or delete them. Use "
                "this agent type when you need to investigate the codebase, "
                "understand its structure, or gather information from files "
                "to support planning—without making any changes."
            ),
            system_prompt_template="""You are {member_name}, an explorer \
agent in team '{team_name}' led by {leader_name}.

Team purpose: {team_description}

Your role: {member_description}

## Responsibilities
- Complete the exploration tasks assigned by the team leader.
- You are read-only: you may inspect files and the codebase, but you must \
never modify, create, or delete anything.

## Reporting
- Always report the task result back to {leader_name} using the TeamSay \
tool, whether the task succeeds or fails.
- Keep your private reasoning private; only share conclusions and findings \
that the leader needs.

Note: `TeamSay` is your ONLY channel to communicate with {leader_name} and \
the other team members. Any other output you produce is invisible to them, \
so anything you want them to see MUST be sent through `TeamSay`.""",
            permission_context=PermissionContext(
                # Read-only
                mode=PermissionMode.EXPLORE,
            ),
        ),
    ],
    # 长期记忆。默认的 PER_AGENT 工作区隔离方式使得记忆能够
    # 在同一个智能体的多个会话之间保留。
    extra_agent_middlewares=longterm_memory_factory,
    channels=[
        DingTalkChannel,
        DiscordChannel,
        FeishuChannel,
    ],
)

# 在框架 app 外层统一建立登录身份，保留框架现有的用户资源授权逻辑。
install_auth(app, auth_accounts, auth_settings, business_pool=business_pool)

if __name__ == "__main__":
    # 启动服务
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8088,
    )
