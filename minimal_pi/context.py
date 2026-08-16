"""
context.py — AGENTS.md / CLAUDE.md 项目上下文加载
==================================================

职责：收集要注入系统提示词 <project_context> 的上下文文件——
      全局一份（~/.pi/agent/）+ cwd 逐级向上，祖先在前。
      这就是 Pi 读取 AGENTS.md / CLAUDE.md 的机制。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- loadProjectContextFiles: packages/coding-agent/src/core/resource-loader.ts:118
- 候选文件名（按优先级）: resource-loader.ts:71
  （AGENTS.override.md / AGENTS.md / AGENTS.MD / CLAUDE.md / CLAUDE.MD）
- 全局一份 + 逐级向上 + 祖先在前（unshift）: resource-loader.ts:128-153
- 去重 seenPaths:         resource-loader.ts:126,143-146

v1 简化说明：
- 砍 worktree shadow 判定（resource-loader.ts:100-116 findShadowedContextFile，
  处理 git worktree 子工作树与主仓库的上下文文件遮蔽）；
  砍 git 根判定（Pi 走完整个目录树直到文件系统根，v1 同样走到底，
  但不停在 git 根）。
"""

from __future__ import annotations

from pathlib import Path

# 对齐 resource-loader.ts:71 的候选文件名与优先级
CONTEXT_FILE_CANDIDATES = ["AGENTS.override.md", "AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD"]


def load_context_file_from_dir(dir_path: str | Path) -> tuple[str, str] | None:
    """目录里按优先级取第一个存在的上下文文件，返回 (路径, 内容)。"""
    d = Path(dir_path)
    for name in CONTEXT_FILE_CANDIDATES:
        candidate = d / name
        if candidate.is_file():
            try:
                return str(candidate), candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def load_project_context_files(cwd: str, agent_dir: str | None = None) -> list[tuple[str, str]]:
    """收集上下文文件，顺序 = [全局] + [最外层祖先 → cwd]。

    对齐源码: loadProjectContextFiles，resource-loader.ts:118-156
    - 全局上下文（~/.pi/agent/AGENTS.md 等）最先（resource-loader.ts:128-132）
    - cwd 逐级向上收集，unshift 使祖先在前（resource-loader.ts:134-153）
    - seenPaths 去重（resource-loader.ts:143-146）
    """
    files: list[tuple[str, str]] = []
    seen: set[str] = set()

    if agent_dir:
        global_ctx = load_context_file_from_dir(agent_dir)
        if global_ctx:
            files.append(global_ctx)
            seen.add(global_ctx[0])

    ancestors: list[tuple[str, str]] = []
    current = Path(cwd).resolve()
    while True:
        ctx = load_context_file_from_dir(current)
        if ctx and ctx[0] not in seen:
            ancestors.insert(0, ctx)  # 对齐 resource-loader.ts:144 的 unshift
            seen.add(ctx[0])
        if current.parent == current:
            break
        current = current.parent

    files.extend(ancestors)
    return files
