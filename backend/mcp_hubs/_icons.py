"""将来源官网图标内置返回，避免页面显示依赖外部图床。"""

import base64
from pathlib import Path


def mcp_hub_icon(hub_id: str) -> str:
    """沿用现有 icon_url 字段，保留官网 PNG / ICO 原图格式。"""
    extension, mime = ("ico", "image/x-icon") if hub_id == "modelscope" else ("png", "image/png")
    data = (Path(__file__).parent / "icons" / f"{hub_id}.{extension}").read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
