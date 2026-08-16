"""
llm.py — LLM 客户端（OpenAI 兼容，非流式）
===========================================

职责：循环的唯一"发请求"出口。接收系统提示词 + 消息 + 工具定义，
      返回 (文本, 工具调用列表, 停止原因)。v1 不区分 provider——
      base_url 可指向 DeepSeek / OpenAI / 任何 OpenAI 兼容端点。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- streamFunction 签名边界: packages/agent/src/agent-loop.ts:281
                           (streamAssistantResponse——循环在此处把
                           AgentMessage[] 转 Message[] 后调用 streamFn)
- 默认实现入口:            packages/agent/src/stream-fn.ts:15
                           (getDefaultStreamFn)
- 工具调用校验:            validateToolArguments（pi-ai，v1 由工具自身兜底）

v1 简化说明：
- 砍流式事件（agent-loop.ts:317-361 的 text_delta/toolcall_delta 增量
  事件流，TUI 用它做打字机渲染）；砍重试/退避/凭证轮换（pi-ai
  RetryPolicy）；砍多 provider 模型目录（models.generated.ts）。
- stop_reason 对齐 Pi 的停止原因：end_turn / tool_use / length / error
  （length 由 finish_reason="length" 映射——这是主循环截断保护的输入）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from openai import OpenAI

from minimal_pi.messages import AssistantMessage, ToolCall
from minimal_pi.tools import Tool


class LLMClient:
    """OpenAI 兼容客户端。对齐 streamFunction 边界（agent-loop.ts:281-312）。"""

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com/v1",
        api_key: str = "",
        model: str = "deepseek-chat",
    ):
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def _to_openai_tools(self, tools: list[Tool]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.snippet,  # 一行 snippet 同时充当工具描述
                    "parameters": t.schema,
                },
            }
            for t in tools
        ]

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Tool],
    ) -> AssistantMessage:
        """对齐 streamAssistantResponse 的调用体（agent-loop.ts:281-312）。

        v1 简化：同步单次请求（Pi 是事件流 + partial 消息累积）。
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            return AssistantMessage(content=f"LLM error: {e}", stop_reason="error")

        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        stop_reason = "end_turn"
        if choice.finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif choice.finish_reason == "length":
            stop_reason = "length"  # 对齐 failToolCallsFromTruncatedMessage 的输入

        return AssistantMessage(
            content=message.content or "",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )
