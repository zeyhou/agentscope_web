"""项目自定义技能源；仅使用 AgentScope 公开接口，不修改框架。"""

from ._icons import skill_hub_icon
from .github import GitHubSkillHub
from .tencent import TencentSkillHub

__all__ = ["GitHubSkillHub", "TencentSkillHub", "skill_hub_icon"]
