# -*- coding: utf-8 -*-
"""项目内的 Z.ai Coding Plan 凭据，通过框架扩展点注册。"""

from typing import Literal, Type

from pydantic import ConfigDict, Field, SecretStr

from agentscope.credential import CredentialBase

from ._model import ZaiCodingChatModel


class ZaiCodingCredential(CredentialBase):
    """仅声明 Coding Plan 对话能力，不继承 OpenAI 的嵌入、语音能力。"""

    model_config = ConfigDict(title="Z.ai 中国站 Coding Plan")

    type: Literal["zai_coding_credential"] = "zai_coding_credential"
    name: str = Field(default="", title="凭据名称", description="便于识别的名称。")
    api_key: SecretStr = Field(
        min_length=1,
        title="Coding Plan API Key",
        description="填写智谱中国站个人编程套餐或团队编程套餐的 API Key。",
    )
    # 中国站 Key 使用智谱 Coding 专用地址，不能使用国际站或普通 API 地址。
    base_url: str = Field(
        default="https://open.bigmodel.cn/api/coding/paas/v4",
        min_length=1,
        title="API 地址",
        description="智谱中国站 Coding Plan 的 OpenAI Chat Completions 基础地址。",
    )

    @classmethod
    def get_chat_model_class(cls) -> Type[ZaiCodingChatModel]:
        """供模型目录和会话运行时使用同一个项目级适配器。"""
        return ZaiCodingChatModel
