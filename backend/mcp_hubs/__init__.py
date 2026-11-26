"""项目级 MCPHub 扩展，不修改 AgentScope 框架源码。"""

from ._icons import mcp_hub_icon
from .configuration import configured_mcp_hubs
from .glama import GlamaMCPHub
from .modelscope import ModelScopeMCPHub
from .official import OfficialRegistryMCPHub

__all__ = ["OfficialRegistryMCPHub", "ModelScopeMCPHub", "GlamaMCPHub", "configured_mcp_hubs", "mcp_hub_icon"]
