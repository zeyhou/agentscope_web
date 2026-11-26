"""硅基流动中国站凭据，通过项目扩展点注册，不修改框架源码。"""
from typing import Literal

from pydantic import ConfigDict, Field, SecretStr
from agentscope.credential import CredentialBase

from .chat._model import SiliconFlowChatModel
from .embedding._model import SiliconFlowEmbeddingModel


class SiliconFlowCredential(CredentialBase):
    model_config = ConfigDict(title="硅基流动 SiliconFlow API")

    type: Literal["siliconflow_credential"] = "siliconflow_credential"
    name: str = Field(default="", title="凭据名称", description="便于识别的名称。")
    api_key: SecretStr = Field(min_length=1, title="API Key", description="填写硅基流动中国站控制台创建的 API Key，不加 Bearer 前缀。")
    base_url: str = Field(default="https://api.siliconflow.cn/v1", min_length=1,
                          title="API 地址", description="中国站 OpenAI 兼容基础地址，可用于对话和文本嵌入。")

    @classmethod
    def get_chat_model_class(cls):
        return SiliconFlowChatModel

    @classmethod
    def get_embedding_model_class(cls):
        # 同一用户的知识库通过凭据 ID 解析，继续沿用框架的用户隔离。
        return SiliconFlowEmbeddingModel
