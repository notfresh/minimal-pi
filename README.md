# minimal-pi — Pi agent harness 的最小蒸馏版（v1）

> 从 [earendil-works/pi](https://github.com/earendil-works/pi)（作者 Mario Zechner，
> libGDX 创始人）蒸馏的可运行最小实现。保留"让 agent 工作"的代码，
> 砍掉"让 agent 在真实世界不崩"的代码。详见 `v1-what-is-discard.md`。

**版本基线**：earendil-works/pi @ `086c32e`（v0.84.2，2026-08-16 浅克隆）。
所有 `文件:行号` 均基于该 checkout 实测，源码漂移后以仓库为准。

## 一句话

Pi 的核心 = **极简系统提示词（工具只列一行 snippet）+ 双循环 agent loop
（内层跑工具，外层等 follow-up）+ 截断保护（输出被 token 上限截断时
拒绝执行任何工具调用）**。minimal-pi 把这三件事用 ~1150 行 Python 复刻出来，
接 OpenAI 兼容 API（默认 DeepSeek）真实可跑。

## 快速开始

```bash
cd /root/projects/minimal-pi

# 1) 准备环境（首次 / 依赖更新时跑一次；用 uv 隔离到 .venv）
uv sync

# 2) 配 key
export DEEPSEEK_API_KEY=sk-...

# 3) 跑（必须走 venv 里的 python，不然找不到 openai）
.venv/bin/python -m minimal_pi -p "看看当前目录有什么文件，读一下 README 开头" --cwd /path/to/dir

# 或激活 venv 后用普通 python
# source .venv/bin/activate
# python -m minimal_pi
```

常用模式：

```bash
# print 模式：跑完输出最终回答
.venv/bin/python -m minimal_pi -p "看看当前目录有什么文件，读一下 README 开头" --cwd /path/to/dir

# 简易交互模式
.venv/bin/python -m minimal_pi

# 换模型 / 换端点（任何 OpenAI 兼容）
.venv/bin/python -m minimal_pi -p "hi" --model gpt-4o-mini --base-url https://api.openai.com/v1

# 看每轮工具调用（调试）
.venv/bin/python -m minimal_pi -p "..." --verbose
```



依赖：`pyproject.toml` 声明，仅 `openai`（Python 3.10+）。默认模型 `deepseek-chat`。

## 行为示例（真实 API，2026-08-16）

用户：*"当前目录有什么文件？用工具查一下，然后读 hello.txt 的内容并告诉我里面有几行。"*

```
[user]      当前目录有什么文件？...
[assistant] stop=tool_use   tools=['bash']      ← 模型决定用 bash
[tool bash] total 196 drwxr-xr-x ...            ← 执行结果回注
[assistant] stop=tool_use   tools=['read']      ← 模型决定用 read
[tool read] 1	LINE ONE
            2	X two
            3	LINE THREE
[assistant] stop=end_turn   输出最终回答          ← 无工具调用，回合结束
```

循环结构与 Pi 完全同构：**LLM → 工具调用 → 结果回注 → 再 LLM → …→ 无工具调用结束**。

## 源码映射总表（模块 ↔ 原版 文件:行号 ↔ 蒸馏函数）

### 主循环（心脏）

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `loop.py` | `packages/agent/src/agent-loop.ts:155` | `runLoop` | `ConversationLoop.run` |
| `loop.py` | `packages/agent/src/agent-loop.ts:281` | `streamAssistantResponse` | `llm.complete` 调用体 |
| `loop.py` | `packages/agent/src/agent-loop.ts:381` | `failToolCallsFromTruncatedMessage` | `stop_reason=="length"` 分支 |
| `loop.py` | `packages/agent/src/agent-loop.ts:411` | `executeToolCalls` | 批量 `_execute_tool` |
| `loop.py` | `packages/agent/src/agent-loop.ts:607` | 工具未找到分支 | `Tool ... not found` |
| `loop.py` | `packages/agent/src/agent-loop.ts:202-207` | 工具调用判定 | `if not assistant.tool_calls: break` |

### 极简提示词（Pi 的 token 效率卖点）

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `prompt.py` | `packages/coding-agent/src/core/system-prompt.ts:28` | `buildSystemPrompt` | `build_system_prompt` |
| `prompt.py` | `system-prompt.ts:80-84` | 一行 snippet 机制 | 工具列表拼接 |
| `prompt.py` | `system-prompt.ts:86-119` | guidelines 推导 | guidelines 收集 |
| `prompt.py` | `system-prompt.ts:144-152` | `<project_context>` 注入 | context_files 段 |
| `prompt.py` | `system-prompt.ts:154-157` | skills 索引注入 | skills_section |
| `prompt.py` | `system-prompt.ts:121` | 角色设定开场 | 开场句 |

### 消息模型

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `messages.py` | `packages/agent/src/harness/messages.ts:124` | `convertToLlm` | `convert_to_llm` |
| `messages.py` | `packages/agent/src/types.ts:412` | `AgentContext` | 消息结构 |
| `messages.py` | `packages/agent/src/types.ts:53` | `AgentToolCall` | `ToolCall` |

### 工具系统（默认四件套）

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `tools.py` | `packages/agent/src/types.ts:386` | `AgentTool` | `Tool` |
| `tools.py` | `packages/coding-agent/src/core/tools/index.ts:168` | `createCodingTools` | `create_coding_tools` |
| `tools.py` | `tools/read.ts:356`（snippet `read.ts:28`） | `createReadTool` | `make_read_tool` |
| `tools.py` | `tools/truncate.ts:78`（常量 `:11-12`） | `truncateHead` | `truncate_head` |
| `tools.py` | `tools/truncate.ts:168` | `truncateTail` | `truncate_tail` |
| `tools.py` | `tools/bash.ts:502`（snippet `:47`） | `createBashTool` | `make_bash_tool` |
| `tools.py` | `tools/edit.ts:441`（snippet `:57`） | `createEditTool` | `make_edit_tool` |
| `tools.py` | `tools/write.ts:272`（snippet `:21`） | `createWriteTool` | `make_write_tool` |

### 技能与上下文（渐进式披露）

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `skills.py` | `packages/coding-agent/src/core/skills.ts:168` | `loadSkillsFromDir` | `load_skills_from_dir` |
| `skills.py` | `skills.ts:74-81` | `Skill` 接口 | `Skill` |
| `skills.py` | `skills.ts:11-14` | 64/1024 校验 | 常量 + 校验 |
| `skills.py` | `packages/agent/src/harness/system-prompt.ts:3` | `formatSkillsForSystemPrompt` | `format_skills_for_system_prompt` |
| `skills.py` | `docs/skills.md:27-31` | 技能目录约定 | `discover_skills` |
| `context.py` | `packages/coding-agent/src/core/resource-loader.ts:118` | `loadProjectContextFiles` | `load_project_context_files` |
| `context.py` | `resource-loader.ts:71` | 候选文件名 | `CONTEXT_FILE_CANDIDATES` |

### LLM 边界

| minimal-pi | 原版源码位置 | 原版函数 | 蒸馏函数 |
|---|---|---|---|
| `llm.py` | `packages/agent/src/stream-fn.ts:15` | `getDefaultStreamFn` | （等价入口） |
| `llm.py` | `packages/agent/src/agent-loop.ts:298-312` | LLM 调用上下文组装 | `complete` |

## 与 Pi 的差异速览

| 维度 | Pi | minimal-pi v1 |
|---|---|---|
| 语言 | TypeScript monorepo（5 包） | Python 单包 8 模块 |
| 系统提示词 | 极简 | **忠实复刻**（一行 snippet + 两条硬 guideline） |
| 主循环 | 双循环 + steering + 并行工具 | 双循环骨架（顺序执行，steering 砍掉） |
| 工具 | 4 默认 + 扩展生态 | 4 默认（schema 语义对齐） |
| 流式 | 事件流 + 差分渲染 TUI | 非流式，纯文本输出 |
| 会话 | 分叉树 + compaction + lane | 单线消息列表 |
| 安全 | 无内置权限（靠容器） | 继承：无权限层 |

## 目录结构

```
minimal-pi/
├── README.md              ← 本文件（含源码映射）
├── v1-what-is-discard.md  ← 丢弃清单（账目 + 逐项 + 路线图）
└── minimal_pi/
    ├── cli.py             ← 入口（print / 简易交互）
    ├── loop.py            ← ConversationLoop（对齐 runLoop）
    ├── prompt.py          ← build_system_prompt（极简提示词）
    ├── messages.py        ← 消息模型 + convert_to_llm
    ├── tools.py           ← Tool + read/bash/edit/write + 截断
    ├── skills.py          ← SKILL.md 发现 + 索引注入
    ├── context.py         ← AGENTS.md/CLAUDE.md 逐级加载
    ├── llm.py             ← OpenAI 兼容客户端
    ├── __main__.py        ← python -m minimal_pi
    └── __init__.py
```
