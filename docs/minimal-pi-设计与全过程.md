# minimal-pi 设计文档与蒸馏全过程

> **项目**：/root/projects/minimal-pi（git commit `aa0a3db`）
> **蒸馏对象**：earendil-works/pi @ `086c32e`（v0.84.2，2026-08-16 浅克隆）
> **形态**：Python 3.11，8 模块，1156 行，唯一依赖 `openai`
> **文档日期**：2026-08-16

---

# 第一部分：核心设计

## 0. 一句话

Pi 的核心 = **极简系统提示词（工具只列一行 snippet）+ 双循环 agent loop
（内层跑工具，外层等 follow-up）+ 截断保护（输出被 token 上限截断时
拒绝执行任何工具调用）**。minimal-pi 把这三件事用 1156 行 Python 复刻，
接 OpenAI 兼容 API（默认 DeepSeek）真实可跑。

## 1. 架构

```
minimal-pi/
├── README.md              ← 总览 + 源码映射表
├── v1-what-is-discard.md  ← 丢弃清单（32 项 + 账目 + 路线图）
└── minimal_pi/
    ├── cli.py             ← 入口：print 模式 / 简易交互（对齐 Pi 的模式路由）
    ├── loop.py            ← ConversationLoop（心脏：对齐 runLoop）
    ├── prompt.py          ← build_system_prompt（极简提示词）
    ├── messages.py        ← 消息模型 + convert_to_llm（LLM 边界转换）
    ├── tools.py           ← Tool 接口 + read/bash/edit/write + 截断
    ├── skills.py          ← SKILL.md 发现 + <available_skills> 索引注入
    ├── context.py         ← AGENTS.md/CLAUDE.md 逐级向上加载
    ├── llm.py             ← OpenAI 兼容客户端（同步非流式）
    ├── __main__.py        ← python -m minimal_pi
    └── __init__.py
```

数据流（与 Pi 同构）：

```
用户 prompt
   │
   ▼
ConversationLoop.run ────────────────┐   内层循环（while 有工具调用）
   │  llm.complete(system_prompt,     │
   │      messages, tools)            │
   │      │                           │
   │      ▼                           │
   │  assistant 消息                  │
   │   ├─ stop=length → 全部工具调用标记失败（截断保护）──┐
   │   ├─ 无工具调用 → break（回合结束）                  │
   │   └─ 有工具调用 → 批量执行 → 结果回注 ──────────────┘
   ▼
最终消息列表 → cli 输出 assistant 最后文本
```

## 2. 源码映射总表（全部实测行号，非估）

### 主循环

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `loop.py` `ConversationLoop.run` | `packages/agent/src/agent-loop.ts:155` | `runLoop` |
| `llm.complete` 调用体 | `agent-loop.ts:281` | `streamAssistantResponse` |
| `stop_reason=="length"` 分支 | `agent-loop.ts:381` | `failToolCallsFromTruncatedMessage` |
| 批量 `_execute_tool` | `agent-loop.ts:411` | `executeToolCalls` |
| 工具未找到分支 | `agent-loop.ts:607` | `prepareToolCall` 内联 |
| 无工具调用 break | `agent-loop.ts:202-207` | 工具调用判定 |

### 极简提示词

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `prompt.py` `build_system_prompt` | `packages/coding-agent/src/core/system-prompt.ts:28` | `buildSystemPrompt` |
| 工具一行 snippet 机制 | `system-prompt.ts:80-84` | 工具列表 |
| guidelines 收集 | `system-prompt.ts:86-119` | guidelines 推导 |
| `<project_context>` 注入 | `system-prompt.ts:144-152` | 上下文注入 |
| skills 索引注入 | `system-prompt.ts:154-157` | 技能注入 |
| 角色开场句 | `system-prompt.ts:121` | 开场 |

### 消息模型

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `messages.py` `convert_to_llm` | `packages/agent/src/harness/messages.ts:124` | `convertToLlm` |
| `ToolCall` | `packages/agent/src/types.ts:53` | `AgentToolCall` |
| 消息结构 | `packages/agent/src/types.ts:412` | `AgentContext` |

### 工具系统（默认四件套）

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `tools.py` `Tool` | `packages/agent/src/types.ts:386` | `AgentTool` |
| `create_coding_tools` | `packages/coding-agent/src/core/tools/index.ts:168` | `createCodingTools` |
| `make_read_tool`（snippet read.ts:28） | `tools/read.ts:356` | `createReadTool` |
| `truncate_head`（常量 :11-12） | `tools/truncate.ts:78` | `truncateHead` |
| `truncate_tail` | `tools/truncate.ts:168` | `truncateTail` |
| `make_bash_tool`（snippet :47） | `tools/bash.ts:502` | `createBashTool` |
| `make_edit_tool`（snippet :57） | `tools/edit.ts:441` | `createEditTool` |
| `make_write_tool`（snippet :21） | `tools/write.ts:272` | `createWriteTool` |

### 技能与上下文（渐进式披露）

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `skills.py` `load_skills_from_dir` | `packages/coding-agent/src/core/skills.ts:168` | `loadSkillsFromDir` |
| `Skill` dataclass | `skills.ts:74-81` | `Skill` 接口 |
| 64/1024 校验 | `skills.ts:11-14` | 常量 |
| `format_skills_for_system_prompt` | `packages/agent/src/harness/system-prompt.ts:3` | `formatSkillsForSystemPrompt` |
| `discover_skills` 目录约定 | `docs/skills.md:27-31` | 技能目录规范 |
| `context.py` `load_project_context_files` | `packages/coding-agent/src/core/resource-loader.ts:118` | `loadProjectContextFiles` |
| `CONTEXT_FILE_CANDIDATES` | `resource-loader.ts:71` | 候选文件名 |

### LLM 边界

| minimal-pi | 原版源码位置 | 原版函数 |
|---|---|---|
| `llm.py` `LLMClient` | `packages/agent/src/stream-fn.ts:15` | `getDefaultStreamFn` |
| 上下文组装 | `agent-loop.ts:298-312` | LLM 调用上下文 |

## 3. 关键设计决策

1. **Python 而非 TypeScript**：Pi 是 TS monorepo，但蒸馏目标是逻辑不是语言；
   传承用户已验证的 minimal-agent-v2（Python + openai 库）写法。
2. **零防御，纯直连**：无重试/退避/凭证轮换——一次请求，失败把错误文本
   回给模型（对齐 Pi 的 "throw on failure" 哲学）。
3. **保留截断保护**：这是 Pi 独有的防御（`agent-loop.ts:381`），小而精，
   语义对齐保留——虽然非流式下几乎不会触发。
4. **edit 保留"多段 + 非增量 + 不重叠"语义**（`edit.ts:45-54` schema 描述
   原样保留），砍 diff 渲染/patch 生成。
5. **无内置权限系统**：Pi 官方设计（"No permission popups"），v1 继承。
6. **消息结构内统一、LLM 边界转换**：对齐 Pi 的 "Agent loop works with
   AgentMessage throughout. Transforms to Message[] only at the LLM call
   boundary."

## 4. 运行方法

```bash
cd /root/projects/minimal-pi
export DEEPSEEK_API_KEY=sk-...

# print 模式（跑完输出最终回答）
python3 -m minimal_pi -p "看看当前目录有什么文件，读一下 README 开头" --cwd /path/to/dir

# 简易交互模式
python3 -m minimal_pi

# 换模型/端点（任何 OpenAI 兼容）
python3 -m minimal_pi -p "hi" --model gpt-4o-mini --base-url https://api.openai.com/v1

# 调试：看每轮工具调用
python3 -m minimal_pi -p "..." --verbose
```

---

# 第二部分：丢弃清单（v1-what-is-discard.md 全文）

## 账目总览

| 维度 | Pi 相关源码 | minimal-pi v1 | 砍掉 |
|---|---|---|---|
| 核心循环（agent-loop.ts） | 796 行 | ~160 行 | ~80% |
| 系统提示词（162+34 行） | 196 行 | ~120 行 | ~39%（语义全保留） |
| 工具层（4 工具 + truncate） | 1,585 行 | ~350 行 | ~78% |
| 技能发现（skills.ts） | 487 行 | ~200 行 | ~59% |
| 上下文加载（resource-loader.ts） | 1,096 行 | ~95 行 | ~91% |
| 消息转换（messages + types） | 611 行 | ~110 行 | ~82% |
| **合计（核心范围）** | **~4,800 行** | **~1,155 行** | **~76%** |

## 逐项清单（32 项）

### A. 循环层（agent-loop.ts）

1. **流式事件** — `agent-loop.ts:317-361`（text_delta/toolcall_delta 增量）—
   TUI 打字机渲染、中途可打断。v1 无 TUI，改同步非流式。
2. **steering（运行中 Enter 插话）** — `agent-loop.ts:167,259`（getSteeringMessages）—
   Pi 招牌交互：agent 跑的时候按 Enter 中途改方向。依赖 TUI 输入线程，v1 砍。
3. **follow-up 队列（Alt+Enter 排队）** — `agent-loop.ts:263-268`（外层循环检查）—
   排队的后续指令在 agent 要停时自动续跑。v1 砍。
4. **工具并行执行** — `agent-loop.ts:489-554`（executeToolCallsParallel）—
   多个工具调用并发跑，快。v1 保留批量结构但顺序执行。重建第 1 项。
5. **回合间钩子 prepareNextTurn** — `agent-loop.ts:226-245` — 每轮可换模型、
   调 thinking level、替换上下文（compaction 挂载点）。v1 单模型固定。
6. **beforeToolCall / afterToolCall 钩子** — `agent-loop.ts:619-634`、
   `types.ts:277-292` — 工具执行前审批（权限）、执行后改写结果（审计）。
   Pi 无内置权限，钩子是自建确认流的官方入口。v1 留 ToolError 抛错路径。
7. **事件流 emit** — `agent-loop.ts:109-114` 等 — UI 订阅用。v1 用 --verbose 代替。

### B. 会话与状态

8. **会话树分叉** — `agent-harness.ts:16-24`（SessionTree/BranchSummaryEntry）—
   一条会话任意点分叉多分支。v1 单线消息列表。
9. **compaction 上下文压缩** — `packages/agent/src/harness/compaction/` —
   长会话 token 爆掉时摘要压缩历史。v1 全量保留（max_turns 兜底）。
10. **Lane 车道并发隔离** — `agent-harness.ts:28-55`（LaneBusy）— run/compaction/
    navigation 操作互相隔离。v1 单进程单循环。
11. **Result/TaggedError 类型化错误** — `agent-harness.ts:105-125` — 8 种拒绝
    类型让调用方类型判断失败分支。v1 用异常 + 返回值。
12. **会话持久化/恢复** — `session-manager.ts` + `harness/session/` — 断点续跑。
    v1 每次会话内存态。

### C. 提示词与技能

13. **pi 自身文档指引段** — `system-prompt.ts:131-138` — 让模型按需 read pi 文档。
    minimal-pi 没有自己的文档体系，砍。
14. **自定义提示词分支** — `system-prompt.ts:46-72` — 用户替换默认提示词。
    v1 固定默认。
15. **APPEND_SYSTEM.md 追加段** — `system-prompt.ts:140-142` — 全局行为规则。
    v1 砍。
16. **gitignore 忽略规则** — `skills.ts:16-65` — 扫描时排除被忽略目录。
    v1 不扫忽略。
17. **根目录 .md 直接当技能** — `skills.ts:163` 注释形态二 + `docs/skills.md:37-39` —
    v1 只认 SKILL.md 目录形态。
18. **逐目录诊断** — `skills.ts:83-86`（ResourceDiagnostic）— v1 静默跳过。

### D. 工具层

19. **edit 的 diff 渲染 / unified patch** — `edit.ts:6,13-22`（edit-diff.ts）—
    编辑前预览、生成 patch。v1 纯文本替换，schema 语义原样保留。
20. **bash 进程树管理** — `bash.ts:11-17`（killProcessTree/trackDetachedChildPid）—
    超时/中断杀整个进程树、防僵尸。v1 用 subprocess timeout。
21. **bash 环境/shell 配置** — `bash.ts:12-13` — 继承用户 shell env。v1 直接 shell=True。
22. **工具渲染** — `read.ts:170`（formatReadResult）等 — TUI 渲染。v1 纯文本 + 行号前缀。
23. **TypeBox schema 校验** — pi-ai（validateToolArguments）— v1 工具自身兜底。
24. **文件变更队列** — `file-mutation-queue.ts` — 并发写串行化。v1 顺序执行无竞态。
25. **工具采样** — getExperimentalToolSampling — 实验开关。v1 砍。
26. **图像处理** — `read.ts:29-33,93-97`（vision）— read 支持图片。v1 只读文本。

### E. 系统层（Pi 也没有的，v1 继承）

27. **无内置权限系统** — Pi 官方设计（README Permissions：默认启动用户权限，
    要隔离自己容器化）。v1 继承——这是 Pi 与 Hermes 最大分野（Hermes 有
    toolset 命名空间 + shadow 防护 + check_fn 门控）。
28. **无 MCP / 无 sub-agents / 无 plan mode / 无内置 todo** — Pi 官方哲学
    （README Philosophy，全部 "build it with extensions or install a package"）。
29. **多 provider 模型目录** — models.generated.ts — v1 单一端点手输模型名。
30. **重试/退避/凭证轮换** — pi-ai RetryPolicy — v1 裸调用。
31. **telemetry / evals / server / protocol / client 包** — 遥测、评测、
    RPC 集成、SDK 嵌入。v1 全砍。

## 重建路线图（从易到难）

1. 并行工具执行 — `agent-loop.ts:489`
2. 流式输出 — `agent-loop.ts:317`
3. steering（Enter 中途插话）— `agent-loop.ts:167,259`（Pi 招牌）
4. compaction 上下文压缩 — 面试高频考点
5. 会话持久化 + 分叉
6. 重试/退避 — pi-ai RetryPolicy
7. 权限钩子 — beforeToolCall
8. 多 provider
9. 扩展系统

---

# 第三部分：蒸馏全过程

## 阶段 0：定位项目（用户任务：下载 pi 并研究 harness 特点）

- 从群名"Pi-harness调研" + 历史会话线索（"V4-Flash 接 Pi token 消耗只有
  DeepSeek Harness 三成"）定位：Pi 是终端 coding agent（pi.dev）
- GitHub API 确认：**earendil-works/pi**（badlogic/pi-mono 迁移至此），
  TypeScript、MIT、91k star、created 2025-08-09
- 克隆：`git clone --depth 1 https://github.com/earendil-works/pi.git /root/projects/pi`（28M）

## 阶段 1：harness 特点调研（第一轮交付）

深挖后发现核心特征（全部源码实证）：

1. **极简系统提示词**：`system-prompt.ts` 仅 162 行；agent 包仅 34 行；
   工具在提示词里只列一行 snippet（`system-prompt.ts:80-84`）；pi 文档不内联
   只给路径（`:131-138`）；两条硬 guideline（`:116-117`）
2. **双循环 loop**：`agent-loop.ts:155` runLoop——内层跑工具，外层等
   steering/follow-up；`prepareNextTurn` 回合间钩子（`:226-245`）；
   **截断保护**（`:381` failToolCallsFromTruncatedMessage）
3. **渐进式披露**：skills 只给索引（agent/harness/system-prompt.ts:3），
   模型用 read 按需读全文；AGENTS.md 逐级向上（resource-loader.ts:118）
4. **官方哲学"明确不做"**：No MCP / No sub-agents / No permission popups /
   No plan mode / No built-in to-dos / No background bash（README Philosophy）
5. **默认 4 工具**：read/write/edit/bash，TypeBox schema，Operations 可插拔

## 阶段 2：蒸馏设计（用户下令：minimal-pi + v1-what-is-discard.md + 源码映射）

- 加载 skill：`core-algorithm-demo-source-map`（行号实测铁律）、
  `code-distillation`（蒸馏三阶段法）
- 深挖源码拿行号：grep 实测 agent-loop.ts / messages.ts / system-prompt.ts /
  skills.ts / resource-loader.ts / truncate.ts / 4 个工具文件的函数行号
- 设计决策：Python（传承 minimal-agent-v2）+ 8 模块 + 只保留"让 agent 工作"的代码

## 阶段 3：实现（8 个模块，~1150 行）

按依赖顺序：messages → tools → skills → context → prompt → llm → loop → cli

## 阶段 4：测试与踩坑（真实记录）

**冒烟测试（无 LLM）**——工具层：
- write/edit（多段替换 + 唯一性校验 + 不重叠检测）/ read（截断）/ bash 全过
- 发现 2 个问题：
  - bash 非零退出时输出带前导空行 → 修复（`tools.py` 条件拼接）
  - "edit 不唯一报错"测试用例本身设计错（当时 oldText 恰好唯一所以替换成功，
    工具行为正确）→ 用真正不唯一的 oldText 重测，通过

**真实 API 端到端（DeepSeek）**：
- 第一跑失败：`400 - Failed to deserialize... messages[2]: invalid type: map,
  expected a string`
- **根因**：OpenAI 兼容 API 要求 `tool_calls[].function.arguments` 是 JSON
  **字符串**，初版传了 dict → 修复（`messages.py` 加 `json.dumps`）
- 第二跑成功，完整循环：
  ```
  [user]      当前目录有什么文件？...
  [assistant] stop=tool_use  tools=['bash']
  [tool bash] total 196 drwxr-xr-x ...
  [assistant] stop=tool_use  tools=['read']
  [tool read] 1	LINE ONE ...
  [assistant] stop=end_turn  输出最终回答
  ```
- `python -m minimal_pi` 缺 `__main__.py` → 补上；走 `-m` 入口（直接 `python3 minimal_pi/cli.py`
  因绝对 import 找不到 `minimal_pi` 包，README 用法纠正为 `python3 -m minimal_pi`）

## 阶段 5：行号抽查验证 + 文档 + 提交

- 抽查 10+ 个关键行号（grep 实测），与映射文档逐一核对：
  runLoop:155 ✓ buildSystemPrompt:28 ✓ convertToLlm:124 ✓
  failToolCallsFromTruncatedMessage:381 ✓ truncateHead:78 ✓
  loadSkillsFromDir:168 ✓（实测 168，非初记 165）AgentTool:386 ✓ ...
- 写 README.md + v1-what-is-discard.md（32 项）
- git commit `aa0a3db`，1156 行 Python
- 交互模式冒烟通过（真实 API 回答正常）

## 最终账目

| 项 | 值 |
|---|---|
| 蒸馏范围 | Pi 核心 ~4,800 行 → 1,156 行（砍 ~76%） |
| 源码映射 | 30+ 处 文件:行号，全部实测 |
| 真实 API 验证 | 工具循环端到端跑通 + 交互模式 |
| 踩坑修复 | 2 个真实 bug（arguments JSON 序列化、bash 前导换行） |
| 交付物 | 项目 + README（映射表）+ 丢弃清单 + 本全程文档 |
