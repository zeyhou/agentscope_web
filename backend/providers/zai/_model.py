# -*- coding: utf-8 -*-
"""Z.ai Coding Plan 的 OpenAI Chat Completions 协议适配。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from agentscope.message import Msg
from agentscope.model import DeepSeekChatModel
from agentscope.tool import ToolChoice


class ZaiCodingChatModel(DeepSeekChatModel):
    """复用兼容协议的流式解析及 reasoning_content 历史消息格式化。"""

    type: Literal["zai_coding_chat"] = "zai_coding_chat"

    class Parameters(BaseModel):
        """只暴露当前 GLM-5.3 系列支持的参数。"""

        max_tokens: int | None = Field(
            default=None, gt=0, le=131072, title="最大输出 Tokens",
        )
        # 两个模型都不支持关闭推理；模型卡会隐藏这个内部兼容字段。
        thinking_enable: Literal[True] = True
        reasoning_effort: Literal["low", "high", "max"] = Field(
            default="max", title="推理强度",
            description="low 为轻量推理，high 为增强推理，max 为深度推理。",
        )
        temperature: float | None = Field(
            default=None, ge=0, le=1, title="温度",
        )
        top_p: float | None = Field(
            default=None, ge=0.01, le=1, title="Top P",
        )

    def __init__(
        self,
        credential,
        model: str,
        parameters: Parameters | None = None,
        context_size: int = 1000000,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            credential=credential, model=model, parameters=parameters,
            context_size=context_size, **kwargs,
        )
        # 直接构造和通过会话服务构造时都遵循各自模型卡的输入能力。
        for card in self.list_models():
            if card.name == model:
                self.formatter.input_types = card.input_types
                break

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict] | None = None,
        tool_choice: ToolChoice | None = None,
        **generate_kwargs: Any,
    ):
        extra_body = dict(generate_kwargs.get("extra_body") or {})
        # Coding Plan 保留思考上下文；继承的格式化器会回传历史 reasoning_content。
        extra_body["thinking"] = {
            **extra_body.get("thinking", {}),
            "type": "enabled",
            "clear_thinking": False,
        }
        if self.stream and tools:
            extra_body["tool_stream"] = True
        generate_kwargs["extra_body"] = extra_body
        return await super()._call_api(
            model_name, messages, tools=tools, tool_choice=tool_choice,
            **generate_kwargs,
        )

    def _get_disable_thinking_kwargs(self) -> dict:
        # 框架的结构化输出回退不能关闭 GLM-5.3 推理，改为合法的最低推理强度。
        return {"reasoning_effort": "low"}
