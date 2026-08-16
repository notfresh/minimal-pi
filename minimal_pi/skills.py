"""
skills.py — 技能发现（SKILL.md）+ 系统提示词索引
=================================================

职责：扫描技能目录（项目 .agents/skills/ 向上到 git 根 + 用户级目录），
      解析 SKILL.md frontmatter，生成注入系统提示词的索引块。
      模型看到的是"索引"（name + description + location），需要时用
      read 工具读全文——渐进式披露，这是 Pi 极简提示词的一部分。

对齐源码（earendil-works/pi @ v0.84.2, commit 086c32e, 2026-08-16）:
- loadSkillsFromDir:      packages/coding-agent/src/core/skills.ts:165
  （发现规则注释 skills.ts:163-168：含 SKILL.md 的目录是技能根不再递归；
   否则递归子目录找 SKILL.md）
- Skill 接口:             packages/coding-agent/src/core/skills.ts:74-81
- frontmatter 校验:       skills.ts:11-14（name≤64 / description≤1024）
- disable-model-invocation: skills.ts:70（SkillFrontmatter）
- 索引注入 formatSkillsForSystemPrompt:
                          packages/agent/src/harness/system-prompt.ts:3-25
- 技能目录位置:           packages/coding-agent/docs/skills.md:27-31
  （全局 ~/.pi/agent/skills/、~/.agents/skills/、
   项目 .agents/skills/ 在 cwd 与祖先目录，到 git 根为止）

v1 简化说明：
- 砍 .gitignore/.ignore/.fdignore 忽略规则（skills.ts:16-65）；
  砍根目录直接 .md 文件当技能（skills.ts:163 注释的第二种形态，
  docs/skills.md:37-39）；砍逐目录诊断（ResourceDiagnostic）。
- frontmatter 用极简解析器（--- 分隔 + key: value），Pi 用完整
  frontmatter 库（utils/frontmatter.ts）。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MAX_NAME_LENGTH = 64  # 对齐 skills.ts:11
MAX_DESCRIPTION_LENGTH = 1024  # 对齐 skills.ts:14


@dataclass
class Skill:
    """对齐 Skill 接口，skills.ts:74-81。"""

    name: str
    description: str
    file_path: str
    base_dir: str
    disable_model_invocation: bool = False


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 SKILL.md 的 --- 包裹的 frontmatter，返回 (元数据, 正文)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in fm.split("\n"):
        m = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return meta, body


def _read_skill(skill_file: Path) -> Skill | None:
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, _body = parse_frontmatter(text)
    name = meta.get("name") or skill_file.parent.name
    if not re.match(r"^[a-z0-9-]+$", name):  # 对齐 skills.ts:99 校验
        return None
    if len(name) > MAX_NAME_LENGTH or len(meta.get("description", "")) > MAX_DESCRIPTION_LENGTH:
        return None
    return Skill(
        name=name,
        description=meta.get("description", ""),
        file_path=str(skill_file),
        base_dir=str(skill_file.parent),
        disable_model_invocation=meta.get("disable-model-invocation", "").lower() == "true",
    )


def load_skills_from_dir(skill_dir: str | Path) -> list[Skill]:
    """对齐 loadSkillsFromDir，skills.ts:165。

    发现规则（skills.ts:163-168）：
    - 目录含 SKILL.md → 该目录是一个技能根，不递归
    - 否则递归子目录找 SKILL.md
    """
    root = Path(skill_dir)
    if not root.is_dir():
        return []
    skills: list[Skill] = []
    for dirpath, dirnames, _filenames in __import__("os").walk(root):
        skill_file = Path(dirpath) / "SKILL.md"
        if skill_file.is_file():
            skill = _read_skill(skill_file)
            if skill:
                skills.append(skill)
            dirnames.clear()  # 技能根不再递归（对齐 skills.ts:163-166）
    return skills


def _git_root(cwd: str) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def discover_skills(cwd: str, agent_dir: str | None = None) -> list[Skill]:
    """按 Pi 的目录约定收集技能（docs/skills.md:27-31）。

    顺序：项目 .agents/skills/（cwd 向上到 git 根）→ 用户 ~/.agents/skills/
          → 全局 ~/.pi/agent/skills/。
    v1 简化：git 根由 git rev-parse 探测；非 git 目录退化为只扫 cwd 本身。
    """
    roots: list[Path] = []

    # 项目级：cwd 与祖先目录，到 git 根为止（docs/skills.md:31）
    git_root = _git_root(cwd)
    d = Path(cwd).resolve()
    project_roots: list[Path] = []
    while True:
        project_roots.append(d / ".agents" / "skills")
        if git_root and d == git_root:
            break
        if d.parent == d:
            break
        d = d.parent
    roots.extend(reversed(project_roots))  # 最外层祖先在前，cwd 在后

    # 用户级（docs/skills.md:27-28）
    home = Path.home()
    roots.append(home / ".agents" / "skills")
    if agent_dir:
        roots.append(Path(agent_dir) / "skills")  # ~/.pi/agent/skills/

    skills: list[Skill] = []
    seen: set[str] = set()
    for root in roots:
        for skill in load_skills_from_dir(root):
            if skill.name not in seen:
                seen.add(skill.name)
                skills.append(skill)
    return skills


def format_skills_for_system_prompt(skills: list[Skill]) -> str:
    """生成 <available_skills> 索引块。

    对齐源码: formatSkillsForSystemPrompt，
    packages/agent/src/harness/system-prompt.ts:3-25
    - 过滤 disableModelInvocation（system-prompt.ts:4）
    - 输出 name/description/location 三字段 XML（system-prompt.ts:15-23）
    - 附相对路径解析指引（system-prompt.ts:9-10）
    """
    visible = [s for s in skills if not s.disable_model_invocation]
    if not visible:
        return ""
    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "Read the full skill file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.",
        "",
        "<available_skills>",
    ]
    for skill in visible:
        lines.append("  <skill>")
        lines.append(f"    <name>{skill.name}</name>")
        lines.append(f"    <description>{skill.description}</description>")
        lines.append(f"    <location>{skill.file_path}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)
