"""
loop.py — Agent 主循环（Pi 双循环结构 + 截断保护）
===================================================

职责：把系统提示词 + 消息 + 工具喂给 LLM，执行模型请求的工具调用，
      结果回注后继续，直到模型不再请求工具。这是整个 harness 的心脏。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- runLoop 主循环:       packages/agent/src/agent-loop.ts:155
- streamAssistantResponse: agent-loop.ts:281
  （一轮 = 一次 LLM 调用 + 消息累积，agent-loop.ts:193-194）
- 工具调用判定:         agent-loop.ts:202-207
  （content 里的 toolCall 过滤；无工具调用 → 本回合结束）
- 截断保护 failToolCallsFromTruncatedMessage:
                        agent-loop.ts:381-406
  （stopReason=length 时：输出被 token 上限截断，工具参数可能不完整，
   全部不执行、标记错误、让模型重新发起——agent-loop.ts:208-214）
- 批量执行 executeToolCalls: agent-loop.ts:411-426
  （Pi 默认并行 agent-loop.ts:489；v1 简化为顺序）
- 停止判定 hasMoreToolCalls: agent-loop.ts:171-174, 216, 260

v1 简化说明：
- 砍 steering/follow-up 队列（agent-loop.ts:167,259,263——用户运行中
  Enter 中途插话 / Alt+Enter 排队，靠 TUI 输入线程；v1 无 TUI）；
  砍 prepareNextTurn 回合间钩子（agent-loop.ts:226-245，用于换模型/
  调思考级别/上下文替换）；砍 beforeToolCall/afterToolCall 钩子
  （agent-loop.ts:619-634）；砍事件流 emit（agent-loop.ts:109-114）；
  砍并行执行（executeToolCallsParallel agent-loop.ts:489）。
"""

from __future__ import annotations

from minimal_pi.llm import LLMClient
from minimal_pi.messages import AssistantMessage, ToolResultMessage, ToolCall
from minimal_pi.tools import Tool, ToolError


class ConversationLoop:
    """Pi 的 agent loop 蒸馏（对齐 runLoop，agent-loop.ts:155）。"""

    def __init__(self, llm: LLMClient, tools: list[Tool], system_prompt: str, max_turns: int = 40):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.max_turns = max_turns

    def run(self, prompt: str) -> list:
        """跑一轮完整对话，返回最终消息列表（含工具执行记录）。"""
        messages: list = [prompt]  # 对齐 runAgentLoop 的 prompts 入队（agent-loop.ts:103-107）
        turns = 0

        while True:
            turns += 1
            if turns > self.max_turns:
                messages.append("(stopped: max_turns reached)")
                break

            # ── 一次 LLM 调用（对齐 streamAssistantResponse，agent-loop.ts:281）──
            assistant = self.llm.complete(self.system_prompt, convert(messages), list(self.tools.values()))
            messages.append(assistant)

            # ── 截断保护（对齐 failToolCallsFromTruncatedMessage，agent-loop.ts:381）──
            # 输出被 token 上限截断时，流式 tool-call 参数可能残缺，
            # 一个都不能执行：全部标记错误，让模型重新发起（agent-loop.ts:208-214）。
            if assistant.stop_reason == "length":
                for tc in assistant.tool_calls:
                    messages.append(
                        ToolResultMessage(
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                            content=(
                                f'Tool call "{tc.name}" was not executed: the response hit the output '
                                "token limit, so its arguments may be truncated. Re-issue the tool "
                                "call with complete arguments."
                            ),
                            is_error=True,
                        )
                    )
                continue

            # ── 无工具调用 → 回合结束（对齐 agent-loop.ts:203-206）──
            if not assistant.tool_calls:
                break

            # ── 批量执行工具（对齐 executeToolCalls，agent-loop.ts:411）──
            # Pi 默认并行（agent-loop.ts:489-554），v1 顺序执行；
            # 工具不存在 → 错误结果回注（对齐 agent-loop.ts:607-614）。
            for tc in assistant.tool_calls:
                messages.append(self._execute_tool(tc))

            # 内层循环继续（hasMoreToolCalls，agent-loop.ts:216）
            # 外层 follow-up 检查（agent-loop.ts:263-268）v1 砍掉：无排队消息。

        self.messages = messages  # 供 last_text / 调试查看
        return messages

    def _execute_tool(self, tool_call: ToolCall) -> ToolResultMessage:
        tool = self.tools.get(tool_call.name)
        if tool is None:
            return ToolResultMessage(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=f"Tool {tool_call.name} not found",
                is_error=True,
            )
        try:
            result = tool.execute(tool_call.arguments)
            return ToolResultMessage(
                tool_call_id=tool_call.id, tool_name=tool_call.name, content=result, is_error=False
            )
        except ToolError as e:
            return ToolResultMessage(
                tool_call_id=tool_call.id, tool_name=tool_call.name, content=str(e), is_error=True
            )

    @property
    def last_text(self) -> str:
        """最后一条 assistant 文本（供 print 模式输出）。"""
        for m in reversed(self.messages):
            if isinstance(m, AssistantMessage) and m.content:
                return m.content
        return ""


def convert(messages: list) -> list[dict]:
    """延迟导入避免循环依赖；见 messages.convert_to_llm。"""
    from minimal_pi.messages import convert_to_llm

    return convert_to_llm(messages)
