"""
prompt.py — 系统提示词构造（Pi 极简提示词的核心）
=================================================

职责：拼出 Pi 风格的极简系统提示词——
      工具只列一行 snippet、两条硬 guideline、文档不内联、
      上下文文件与技能索引按需注入。这是 Pi "token 效率"卖点的源头。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- buildSystemPrompt: packages/coding-agent/src/core/system-prompt.ts:28
- 工具一行 snippet 机制: system-prompt.ts:80-84
  （"A tool appears in Available tools only when the caller provides a
    one-line snippet"——只有提供 snippet 的工具才出现在提示词里）
- guidelines 推导:     system-prompt.ts:86-119
  （按可用工具推导 + 恒有的两条：Be concise / Show file paths）
- 上下文文件注入:     system-prompt.ts:144-152（<project_context>）
- 技能索引注入:       system-prompt.ts:154-157
                       + packages/agent/src/harness/system-prompt.ts:3
- 开头角色设定:       system-prompt.ts:121

v1 简化说明：
- 砍 pi 自身文档路径段（system-prompt.ts:131-138，让模型按需 read
  pi 文档的指引——minimal-pi 没有自己的文档体系）；
  砍自定义提示词分支（system-prompt.ts:46-72 customPrompt）；
  砍 APPEND_SYSTEM.md 追加段（system-prompt.ts:140-142）。
"""

from __future__ import annotations

from minimal_pi.context import load_project_context_files
from minimal_pi.skills import Skill, format_skills_for_system_prompt
from minimal_pi.tools import Tool


def build_system_prompt(
    cwd: str,
    tools: list[Tool],
    skills: list[Skill] | None = None,
    agent_dir: str | None = None,
    prompt_guidelines: list[str] | None = None,
) -> str:
    """对齐源码: buildSystemPrompt，system-prompt.ts:28。

    参数对应（v1 子集）：
    - tools            ← selectedTools + toolSnippets（system-prompt.ts:80-84）
    - prompt_guidelines ← 外部追加 guideline（system-prompt.ts:108-113）
    - 上下文文件       ← contextFiles（system-prompt.ts:144-152）
    - skills           ← skills（system-prompt.ts:154-157）
    """
    # 工具列表：只有提供 snippet 的工具才会列出（对齐 system-prompt.ts:82-84）
    tools_list = "\n".join(f"- {t.name}: {t.snippet}" for t in tools)

    # guidelines：工具自带 + 外部传入 + 恒有两条（对齐 system-prompt.ts:86-119）
    guidelines: list[str] = []
    seen: set[str] = set()
    for tool in tools:
        for g in tool.guidelines:
            if g not in seen:
                seen.add(g)
                guidelines.append(g)
    for g in prompt_guidelines or []:
        g = g.strip()
        if g and g not in seen:
            seen.add(g)
            guidelines.append(g)
    for g in ("Be concise in your responses", "Show file paths clearly when working with files"):
        if g not in seen:  # 对齐 system-prompt.ts:116-117 "Always include these"
            seen.add(g)
            guidelines.append(g)
    guidelines_text = "\n".join(f"- {g}" for g in guidelines)

    prompt = (
        "You are an expert coding assistant operating inside pi, a coding agent harness. "
        "You help users by reading files, executing commands, editing code, and writing new files.\n\n"
        "Available tools:\n"
        f"{tools_list}\n\n"
        "In addition to the tools above, you may have access to other custom tools depending on the project.\n\n"
        "Guidelines:\n"
        f"{guidelines_text}"
    )

    # 上下文文件（<project_context>，对齐 system-prompt.ts:144-152）
    context_files = load_project_context_files(cwd, agent_dir)
    if context_files:
        prompt += "\n\n<project_context>\n\nProject-specific instructions and guidelines:\n\n"
        for file_path, content in context_files:
            prompt += f'<project_instructions path="{file_path}">\n{content}\n</project_instructions>\n\n'
        prompt += "</project_context>"

    # 技能索引（<available_skills>，对齐 system-prompt.ts:154-157）
    if skills:
        skills_section = format_skills_for_system_prompt(skills)
        if skills_section:
            prompt += "\n\n" + skills_section

    prompt += f"\n\nCurrent working directory: {cwd.replace(chr(92), '/')}"  # 对齐 system-prompt.ts:159
    return prompt
