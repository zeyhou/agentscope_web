"""复用框架的推理、流式响应和工具解析，仅适配硅基流动请求参数。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from agentscope.model import DeepSeekChatModel


class SiliconFlowChatModel(DeepSeekChatModel):
    type: Literal["siliconflow_chat"] = "siliconflow_chat"

    class Parameters(BaseModel):
        max_tokens: int | None = Field(default=None, gt=0, title="最大输出 Tokens")
        # 不指定时使用厂商默认值，避免替用户强制关闭模型的推理模式。
        thinking_enable: bool | None = Field(default=None, title="启用思考")
        thinking_budget: int | None = Field(default=None, ge=128, le=32768, title="思考预算")
        reasoning_effort: Literal["high", "max"] | None = Field(default=None, title="推理强度")
        temperature: float | None = Field(default=None, ge=0, le=2, title="温度")
        top_p: float | None = Field(default=None, gt=0, le=1, title="Top P")

    async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **generate_kwargs):
        parameters = self.parameters.model_dump(exclude_none=True)
        enabled = parameters.pop("thinking_enable", None)
        budget = parameters.pop("thinking_budget", None)
        extra_body = {}
        if enabled is not None:
            extra_body["enable_thinking"] = enabled
        if budget is not None:
            extra_body["thinking_budget"] = budget
        extra_body.update(generate_kwargs.pop("extra_body", {}) or {})
        # 硅基流动使用 enable_thinking，不能发送 DeepSeek 原生的 thinking 对象。
        kwargs = {"model": model_name, "messages": await self.formatter.format(messages),
                  "stream": self.stream, **parameters, **generate_kwargs}
        if extra_body:
            kwargs["extra_body"] = extra_body
        formatted_tools, formatted_choice = self._format_tools(tools, tool_choice)
        if formatted_tools:
            kwargs["tools"] = formatted_tools
        if formatted_choice is not None:
            kwargs["tool_choice"] = formatted_choice
        if self.stream:
            kwargs["stream_options"] = {"include_usage": True}
        started = datetime.now()
        response = await self.client.chat.completions.create(**kwargs)
        if self.stream:
            return self._parse_stream_response(started, response)
        return self._parse_completion_response(started, response)

    def _get_disable_thinking_kwargs(self):
        # 结构化输出回退同样采用厂商的参数名称。
        return {"extra_body": {"enable_thinking": False}}
