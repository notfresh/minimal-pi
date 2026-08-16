"""
messages.py — 消息模型与 LLM 边界转换
======================================

职责：定义循环内统一使用的消息结构（AgentMessage），以及发送给 LLM 前
      的格式转换（convert_to_llm）。循环内部永远操作统一结构，只有到
      LLM 调用边界才转成 provider 格式（对齐 Pi 的设计：
      "Agent loop that works with AgentMessage throughout. Transforms to
      Message[] only at the LLM call boundary."）。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- AgentContext 定义:       packages/agent/src/types.ts:412
- convertToLlm 转换函数:   packages/agent/src/harness/messages.ts:124
- AgentMessage 类型族:     packages/agent/src/types.ts（AssistantMessage/
                           ToolResultMessage 等）

v1 简化说明：
- Pi 有 7 种消息角色（user/assistant/toolResult/bashExecution/custom/
  branchSummary/compactionSummary），其中 bashExecution 等 4 种在
  convertToLlm（messages.ts:124-167）里被转成 user 消息。
  v1 只有 user/assistant/toolResult 三种，转换是直通——
  被砍的 4 种角色是"会话树分叉摘要 / 上下文压缩摘要 / bash 特殊消息"
  的产物，v1 没有这些功能，所以转换表天然缩小。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """模型发起的一次工具调用（对齐 AgentToolCall，types.ts:53）。"""

    id: str
    name: str
    arguments: dict[str, Any]  # 已解析的 JSON 参数


@dataclass
class AssistantMessage:
    """模型的一次完整响应。stop_reason 对齐 Pi 的停止原因枚举。"""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # "end_turn" 正常结束 | "tool_use" 请求工具 | "length" 输出被截断 | "error"
    stop_reason: str = "end_turn"


@dataclass
class ToolResultMessage:
    """一次工具调用的执行结果（对齐 ToolResultMessage）。"""

    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


# 循环内统一消息 = user 文本 | AssistantMessage | ToolResultMessage
AgentMessage = Any


def convert_to_llm(messages: list[AgentMessage]) -> list[dict[str, Any]]:
    """
    统一消息 → LLM provider 消息格式。

    对齐源码: convertToLlm，packages/agent/src/harness/messages.ts:124
    - Pi 对 bashExecution/custom/branchSummary/compactionSummary 四类
      特殊消息做"转 user + 包装文本"（messages.ts:128-158），
      user/assistant/toolResult 三直通（messages.ts:159-162）。
    - v1 只有三类直通消息，这里做等价直通 + tool 消息的角色映射。
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, str):
            out.append({"role": "user", "content": m})
        elif isinstance(m, AssistantMessage):
            msg: dict[str, Any] = {"role": "assistant", "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        # OpenAI 兼容 API 要求 arguments 是 JSON 字符串
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ]
            out.append(msg)
        elif isinstance(m, ToolResultMessage):
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                }
            )
        else:  # 对齐 messages.ts:163-164 的 default: undefined（跳过未知类型）
            continue
    return out
