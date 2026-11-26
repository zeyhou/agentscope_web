"""按后端进程环境启用需要凭据的目录，未配置时不暴露不可用入口。"""

import os

from agentscope.app.hub import GitHubMCPHub, MCPHubBase

from ._icons import mcp_hub_icon
from .glama import GlamaMCPHub
from .modelscope import ModelScopeMCPHub
from .official import OfficialRegistryMCPHub


def configured_mcp_hubs() -> list[MCPHubBase]:
    hubs = [GitHubMCPHub(icon_url=mcp_hub_icon("github")), OfficialRegistryMCPHub()]
    modelscope_token = os.getenv("MODELSCOPE_API_TOKEN", "").strip()
    glama_key = os.getenv("GLAMA_API_KEY", "").strip()
    if modelscope_token:
        hubs.append(ModelScopeMCPHub(api_token=modelscope_token))
    if glama_key:
        hubs.append(GlamaMCPHub(api_token=glama_key))
    return hubs
