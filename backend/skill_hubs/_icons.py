"""读取随项目内置的来源图标，前端显示时不需要请求外部图床。"""

import base64
from pathlib import Path


def skill_hub_icon(hub_id: str) -> str:
    """通过现有 icon_url 字段返回 PNG，兼容前后端分离部署。"""
    data = (Path(__file__).parent / "icons" / f"{hub_id}.png").read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"
