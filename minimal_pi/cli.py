"""
cli.py — minimal-pi 入口（print 模式 + 简易交互模式）
=====================================================

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- 模式路由（interactive / print / JSON / RPC）: packages/coding-agent/README.md
  （Modes 表：print 模式 -p 跑完退出；默认交互）
- v1 只实现 print 模式 + 简易 input() 交互（Pi 的交互是差分渲染 TUI，
  packages/tui；v1 砍 TUI）。

用法：
    python -m minimal_pi -p "列出当前目录的文件"          # print 模式
    python -m minimal_pi "写一个 hello.py"                 # 简易交互
    DEEPSEEK_API_KEY=... python -m minimal_pi -p "..."     # 显式 key
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from minimal_pi.llm import LLMClient
from minimal_pi.loop import ConversationLoop
from minimal_pi.messages import AssistantMessage
from minimal_pi.prompt import build_system_prompt
from minimal_pi.skills import discover_skills
from minimal_pi.tools import create_coding_tools


def _agent_dir() -> str:
    """~/.pi/agent/（对齐 config.ts getAgentDir，packages/coding-agent/src/config.ts:515）。"""
    return os.path.join(os.path.expanduser("~"), ".pi", "agent")


def run_once(args: argparse.Namespace) -> list:
    cwd = str(Path(args.cwd).resolve())
    tools = create_coding_tools(cwd)
    skills = discover_skills(cwd, agent_dir=_agent_dir()) if not args.no_skills else []
    system_prompt = build_system_prompt(
        cwd=cwd,
        tools=tools,
        skills=skills,
        agent_dir=_agent_dir(),
    )

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    llm = LLMClient(base_url=args.base_url, api_key=api_key, model=args.model)
    loop = ConversationLoop(llm=llm, tools=tools, system_prompt=system_prompt, max_turns=args.max_turns)
    return loop.run(args.prompt)


def _print_run(messages: list) -> None:
    """print 模式：只输出模型最终文本（工具过程静默）。"""
    for m in messages:
        if isinstance(m, AssistantMessage) and m.content:
            print(m.content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minimal-pi", description="Pi agent harness 的最小蒸馏版")
    parser.add_argument("prompt", nargs="?", help="prompt（print 模式）")
    parser.add_argument("-p", "--prompt", dest="prompt_flag", help="prompt（-p 等价位置参数）")
    parser.add_argument("--model", default="deepseek-chat", help="模型名（默认 deepseek-chat）")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1", help="OpenAI 兼容 base_url")
    parser.add_argument("--api-key", default="", help="API key（默认读 DEEPSEEK_API_KEY / OPENAI_API_KEY）")
    parser.add_argument("--cwd", default=".", help="工作目录（默认当前目录）")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--no-skills", action="store_true", help="不加载技能")
    parser.add_argument("--verbose", action="store_true", help="打印每轮工具调用与结果")
    args = parser.parse_args(argv)

    prompt = args.prompt_flag or args.prompt
    if not prompt:
        # 简易交互模式（Pi 交互模式的贫民版：无 TUI，无 steering）
        print("minimal-pi interactive (Ctrl-D 退出)", file=sys.stderr)
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line.strip():
                continue
            args.prompt = line
            messages = run_once(args)
            _print_run(messages)
        return 0

    messages = run_once(args)
    if args.verbose:
        for m in messages:
            print(f"[{type(m).__name__}] {str(m)[:200]}")
    else:
        _print_run(messages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
