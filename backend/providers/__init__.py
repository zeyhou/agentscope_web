"""统一导出项目级模型厂商凭据，类型标识保持不变以兼容已有数据。"""
from .siliconflow import SiliconFlowCredential
from .zai import ZaiCodingCredential

__all__ = ["SiliconFlowCredential", "ZaiCodingCredential"]
