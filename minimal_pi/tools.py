"""
tools.py — 工具系统：Tool 接口 + 4 个默认工具（read/bash/edit/write）
======================================================================

职责：定义 AgentTool 的 v1 形态（name + snippet + schema + 执行函数），
      以及 Pi 的默认四件套 read/bash/edit/write。工具实现走
      "Pluggable operations" 思路的简化版——执行函数接收 cwd 与参数，
      返回文本结果或抛 ToolError（对齐 Pi 的
      "Throw on failure instead of encoding errors in content"）。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- AgentTool 接口:       packages/agent/src/types.ts:386
- 四件套注册:           packages/coding-agent/src/core/tools/index.ts:168
                        (createCodingTools)
- read 工具:            packages/coding-agent/src/core/tools/read.ts:356
                        (createReadTool)；snippet read.ts:28；
                        schema read.ts:24-32
- bash 工具:            packages/coding-agent/src/core/tools/bash.ts:502
                        (createBashTool)；snippet bash.ts:47；
                        schema bash.ts:41-44
- edit 工具:            packages/coding-agent/src/core/tools/edit.ts:441
                        (createEditTool)；snippet edit.ts:57；
                        schema edit.ts:45-54（多段精确替换）
- write 工具:           packages/coding-agent/src/core/tools/write.ts:272
                        (createWriteTool)；snippet write.ts:21；
                        schema write.ts:15-18
- read 截断:            packages/coding-agent/src/core/tools/truncate.ts:78
                        (truncateHead)；常量 DEFAULT_MAX_LINES=2000 /10
                        DEFAULT_MAX_BYTES=50KB truncate.ts:11-12
- bash 尾部截断:        packages/coding-agent/src/core/tools/truncate.ts:168
                        (truncateTail——bash 输出保留末尾，错误通常在尾部)

v1 简化说明：
- 砍 TypeBox schema 校验（validateToolArguments），由执行函数自行兜底；
  砍 beforeToolCall/afterToolCall 钩子（types.ts:277-292）；
  砍 prepareArguments 兼容层（types.ts:393）；
  砍 executionMode 顺序/并行标记（types.ts:408）；
  砍工具采样（getExperimentalToolSampling）与 TUI 渲染。
- edit 保留"多段替换 + 非增量 + 不重叠"语义（editSchema edit.ts:45-54），
  砍 diff 渲染 / unified patch 生成 / 行号标注（edit-diff.ts 全砍）。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class ToolError(Exception):
    """工具执行失败。对齐 Pi 的 execute 抛错约定（types.ts:394 注释）。"""


@dataclass
class Tool:
    """v1 工具形态（对齐 AgentTool types.ts:386 的简化子集）。

    snippet: 出现在系统提示词里的一行描述——这是 Pi 极简提示词的
             关键机制（system-prompt.ts:80-84：工具只有提供 one-line
             snippet 才会出现在 "Available tools" 里）。
    """

    name: str
    snippet: str
    schema: dict[str, Any]  # OpenAI 兼容 JSON Schema（对齐 TypeBox schema）
    execute: Callable[[dict[str, Any]], str]
    guidelines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# read —— 读文件，带行号参数与截断保护
# ---------------------------------------------------------------------------

DEFAULT_MAX_LINES = 2000  # 对齐 truncate.ts:11
DEFAULT_MAX_BYTES = 50 * 1024  # 对齐 truncate.ts:12


def truncate_head(content: str, max_lines: int = DEFAULT_MAX_LINES, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """从头保留，超出 2000 行 / 50KB 截断。

    对齐源码: truncateHead，packages/coding-agent/src/core/tools/truncate.ts:78
    忠实复刻其语义：行数优先，字节上限在累加时逐行检查
    （truncate.ts:126-137）；截断时标注被截信息。
    v1 简化：返回纯文本而非 TruncationResult 结构（丢弃截断统计）。
    """
    total_lines = content.count("\n") + (0 if content.endswith("\n") else 1)
    total_bytes = len(content.encode("utf-8"))
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return content

    out_lines: list[str] = []
    byte_count = 0
    truncated = False
    for line in content.split("\n"):
        line_bytes = len((line + "\n").encode("utf-8"))
        if len(out_lines) >= max_lines or byte_count + line_bytes > max_bytes:
            truncated = True
            break
        out_lines.append(line)
        byte_count += line_bytes

    result = "\n".join(out_lines)
    if truncated:
        result += (
            f"\n... [truncated: {total_lines} lines / {total_bytes} bytes total, "
            f"showing first {len(out_lines)} lines]"
        )
    return result


def truncate_tail(content: str, max_lines: int = DEFAULT_MAX_LINES, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """从尾保留（bash 输出：错误和最终结果通常在末尾）。

    对齐源码: truncateTail，packages/coding-agent/src/core/tools/truncate.ts:168
    """
    total_lines = content.count("\n") + (0 if content.endswith("\n") else 1)
    total_bytes = len(content.encode("utf-8"))
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return content

    lines = content.split("\n")
    out_lines: list[str] = []
    byte_count = 0
    for line in reversed(lines):
        line_bytes = len((line + "\n").encode("utf-8"))
        if len(out_lines) >= max_lines or byte_count + line_bytes > max_bytes:
            break
        out_lines.append(line)
        byte_count += line_bytes
    out_lines.reverse()

    result = "\n".join(out_lines)
    if len(result) < len(content):
        result = (
            f"... [truncated: {total_lines} lines / {total_bytes} bytes total, "
            f"showing last {len(out_lines)} lines]\n{result}"
        )
    return result


def make_read_tool(cwd: str) -> Tool:
    def execute(args: dict[str, Any]) -> str:
        raw_path = args.get("path", "")
        if not isinstance(raw_path, str) or not raw_path:
            raise ToolError("path is required")
        p = Path(raw_path)
        if not p.is_absolute():
            p = Path(cwd) / p
        if not p.exists():
            raise ToolError(f"File not found: {p}")
        if p.is_dir():
            raise ToolError(f"Is a directory: {p}")

        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        offset = args.get("offset")
        limit = args.get("limit")
        if offset is not None:
            lines = lines[offset - 1 :]  # 对齐 readSchema：1-indexed（read.ts:26）
        if limit is not None:
            lines = lines[:limit]

        # 带行号输出（Pi 的 read 渲染带行号，read.ts formatReadResult:170）
        numbered = "\n".join(f"{i:6d}\t{line}" for i, line in enumerate(lines, start=offset or 1))
        return truncate_head(numbered)

    return Tool(
        name="read",
        snippet="Read file contents",  # 对齐 read.ts:28
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read (relative or absolute)"},
                "offset": {"type": "number", "description": "Line number to start reading from (1-indexed)"},
                "limit": {"type": "number", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        },
        guidelines=["Use read to examine files instead of cat or sed."],  # 对齐 read.ts:29
        execute=execute,
    )


# ---------------------------------------------------------------------------
# bash —— 执行 shell 命令
# ---------------------------------------------------------------------------

def make_bash_tool(cwd: str) -> Tool:
    def execute(args: dict[str, Any]) -> str:
        command = args.get("command", "")
        if not isinstance(command, str) or not command:
            raise ToolError("command is required")
        timeout = args.get("timeout")
        try:
            proc = subprocess.run(
                command,
                shell=True,  # 对齐 Pi 的 shell 执行（bash.ts:5 spawn + shell）
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout if isinstance(timeout, (int, float)) and timeout > 0 else None,
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s"
        except OSError as e:
            raise ToolError(f"Failed to run command: {e}") from e

        output = proc.stdout
        if proc.stderr:
            output += ("\n" if output else "") + proc.stderr
        if proc.returncode != 0:
            output += ("\n" if output else "") + f"[exit code: {proc.returncode}]"
        return truncate_tail(output) if output else f"(no output, exit code {proc.returncode})"

    return Tool(
        name="bash",
        snippet="Execute bash commands (ls, grep, find, etc.)",  # 对齐 bash.ts:47
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {"type": "number", "description": "Timeout in seconds (optional, no default timeout)"},
            },
            "required": ["command"],
        },
        execute=execute,
    )


# ---------------------------------------------------------------------------
# edit —— 多段精确文本替换（非增量、不重叠）
# ---------------------------------------------------------------------------

def make_edit_tool(cwd: str) -> Tool:
    def execute(args: dict[str, Any]) -> str:
        raw_path = args.get("path", "")
        edits = args.get("edits")
        if not isinstance(raw_path, str) or not raw_path:
            raise ToolError("path is required")
        if not isinstance(edits, list) or not edits:
            raise ToolError("edits must be a non-empty array")
        for e in edits:
            if not isinstance(e, dict) or not isinstance(e.get("oldText"), str) or not isinstance(e.get("newText"), str):
                raise ToolError("each edit must have string oldText and newText")

        p = Path(raw_path)
        if not p.is_absolute():
            p = Path(cwd) / p
        if not p.exists():
            raise ToolError(f"File not found: {p}")
        original = p.read_text(encoding="utf-8")

        # 对齐 editSchema 语义（edit.ts:45-54）：
        # 1) 每条 oldText 必须唯一（edit.ts:36-39 "must be unique in the original file"）
        # 2) 每条 edit 对"原文件"匹配，非增量（edit.ts:49 "matched against the
        #    original file, not incrementally"）
        # 3) 不允许重叠（edit.ts:50 "Do not include overlapping or nested edits"）
        spans: list[tuple[int, int, str]] = []
        for e in edits:
            old, new = e["oldText"], e["newText"]
            start = original.find(old)
            if start == -1:
                raise ToolError(f"oldText not found in {p}: {old[:60]!r}")
            if original.find(old, start + 1) != -1:
                raise ToolError(f"oldText is not unique in {p}: {old[:60]!r}")
            spans.append((start, start + len(old), new))

        spans.sort()
        for (a_end, b_start) in zip((s[1] for s in spans), (s[0] for s in spans[1:])):
            if a_end > b_start:
                raise ToolError("edits overlap; merge adjacent changes into one edit")

        # 按位置从后往前应用，避免位移（等价于"对原文件匹配后一次性落盘"）
        result = original
        for start, end, new in reversed(spans):
            result = result[:start] + new + result[end:]

        p.write_text(result, encoding="utf-8")
        return f"Applied {len(edits)} edit(s) to {p}"

    return Tool(
        name="edit",
        snippet="Make precise file edits with exact text replacement, including multiple disjoint edits in one call",  # 对齐 edit.ts:57
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to edit (relative or absolute)"},
                "edits": {
                    "type": "array",
                    "description": (
                        "One or more targeted replacements. Each edit is matched against the original file, "
                        "not incrementally. Do not include overlapping or nested edits. If two changes touch "
                        "the same block or nearby lines, merge them into one edit instead."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {"type": "string", "description": "Exact text to replace; must be unique in the original file"},
                            "newText": {"type": "string", "description": "Replacement text"},
                        },
                        "required": ["oldText", "newText"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
        execute=execute,
    )


# ---------------------------------------------------------------------------
# write —— 创建或覆盖文件
# ---------------------------------------------------------------------------

def make_write_tool(cwd: str) -> Tool:
    def execute(args: dict[str, Any]) -> str:
        raw_path = args.get("path", "")
        content = args.get("content", "")
        if not isinstance(raw_path, str) or not raw_path:
            raise ToolError("path is required")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        p = Path(raw_path)
        if not p.is_absolute():
            p = Path(cwd) / p
        p.parent.mkdir(parents=True, exist_ok=True)  # 对齐 write.ts:3 mkdir
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {p}"

    return Tool(
        name="write",
        snippet="Create or overwrite files",  # 对齐 write.ts:21
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write (relative or absolute)"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
        guidelines=["Use write only for new files or complete rewrites."],  # 对齐 write.ts:22
        execute=execute,
    )


def create_coding_tools(cwd: str) -> list[Tool]:
    """默认四件套（对齐 createCodingTools，tools/index.ts:168-175）。"""
    return [make_read_tool(cwd), make_bash_tool(cwd), make_edit_tool(cwd), make_write_tool(cwd)]
