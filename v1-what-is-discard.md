# v1-what-is-discard.md — minimal-pi 丢弃清单

> 从 earendil-works/pi @ `086c32e`（v0.84.2，2026-08-16）蒸馏。
> 原则：**保留"让 agent 工作"的代码，砍掉"让 agent 在真实世界不崩"的代码。
> 生产代码多出来的行 ≈ 防御，每行防御背后是一个线上事故。**

## 账目总览

| 维度 | Pi 相关源码 | minimal-pi v1 | 砍掉 |
|---|---|---|---|
| 核心循环（agent-loop.ts） | 796 行 | ~160 行 | ~80% |
| 系统提示词（system-prompt.ts 162 + 34 行） | 196 行 | ~120 行 | ~39%（语义全保留） |
| 工具层（read/bash/edit/write + truncate） | 1,585 行 | ~350 行 | ~78% |
| 技能发现（skills.ts） | 487 行 | ~200 行 | ~59% |
| 上下文加载（resource-loader.ts） | 1,096 行 | ~95 行 | ~91% |
| 消息转换（messages.ts + types.ts 相关） | 611 行 | ~110 行 | ~82% |
| 合计（核心范围） | **~4,800 行** | **~1,155 行** | **~76%** |

*注：上表只统计 v1 覆盖的模块。Pi 全仓库另有 TUI/多 provider/扩展系统/
telemetry/evals/server 等包，全部未纳入 v1。*

## 逐项丢弃清单

每项格式：**被砍的东西** — 原版位置 — 它为什么存在 — v1 的决定。

### A. 循环层（agent-loop.ts）

1. **流式事件** — `agent-loop.ts:317-361`（text_delta/toolcall_delta 增量）—
   TUI 打字机渲染、中途可打断。v1 无 TUI，改同步非流式。
2. **steering（运行中 Enter 插话）** — `agent-loop.ts:167,259`（getSteeringMessages）—
   Pi 招牌交互：agent 跑的时候用户按 Enter 可以中途改方向。依赖 TUI 输入线程，v1 砍。
3. **follow-up 队列（Alt+Enter 排队）** — `agent-loop.ts:263-268`（外层循环检查）—
   排队的后续指令在 agent 要停时自动续跑。与 steering 同源，v1 砍。
4. **工具并行执行** — `agent-loop.ts:489-554`（executeToolCallsParallel）—
   一次 assistant 响应里的多个工具调用并发跑，快。v1 保留"批量执行"结构但顺序跑
   （Pi 本来也是 ordered results，只是内部并发）。重建路线图第 1 项。
5. **回合间钩子 prepareNextTurn** — `agent-loop.ts:226-245` — 每轮 turn 后可换模型、
   调 thinking level、替换上下文（compaction 的挂载点）。v1 单模型固定。
6. **beforeToolCall / afterToolCall 钩子** — `agent-loop.ts:619-634`、
   `types.ts:277-292` — 工具执行前审批（权限）、执行后改写结果（审计/后处理）。
   Pi 无内置权限系统，钩子是自建确认流的官方入口。v1 留了 ToolError 抛错路径。
7. **事件流 emit（agent_start/turn_start/message_*/tool_*）** — `agent-loop.ts:109-114`
   等 — UI 订阅用。v1 用 `--verbose` 打印代替。
8. **截断保护的细节** — `agent-loop.ts:381-406` 全保留；但 Pi 流式场景下参数是
   "best-effort JSON salvage" 解析的（注释 agent-loop.ts:376-378），v1 非流式
   直接拿完整 JSON，此路径基本不会触发——保留代码是为了语义对齐。

### B. 会话与状态（agent-harness.ts / session / compaction）

9. **会话树分叉** — `agent-harness.ts:16-24`（SessionTree/BranchSummaryEntry/leaf）—
   一条会话可以在任意点分叉出多分支（"这个方向不行，从这重来"）。v1 单线消息列表。
10. **compaction 上下文压缩** — `packages/agent/src/harness/compaction/` +
    `agent-harness.ts:95-98`（CompactionOutcome）— 长会话 token 爆掉时把历史
    摘要压缩。v1 消息全量保留（max_turns 兜底）。
11. **Lane 车道并发隔离** — `agent-harness.ts:28-55`（LaneBusy 等）— 同一 harness
    上 run/compaction/navigation 三类操作并发时互相隔离。v1 单进程单循环。
12. **Result/TaggedError 类型化错误** — `agent-harness.ts:105-125`（RunResult/
    RunRejected 等 8 种拒绝类型）— 调用方用类型判断每个失败分支。v1 用异常 + 返回值。
13. **会话持久化/恢复（--continue/--session）** — `packages/coding-agent/src/core/
    session-manager.ts` + `packages/agent/src/harness/session/` — 断点续跑。
    v1 每次会话内存态。

### C. 提示词与技能

14. **pi 自身文档指引段** — `system-prompt.ts:131-138` — 让模型按需 read pi 的
    文档（extensions.md/themes.md/skills.md…）。minimal-pi 没有自己的文档体系，砍。
15. **自定义提示词分支（customPrompt）** — `system-prompt.ts:46-72` — 用户用
    自己的提示词替换默认。v1 固定默认提示词。
16. **APPEND_SYSTEM.md 追加段** — `system-prompt.ts:140-142` — 全局行为规则文件。
    v1 砍（cli 可用 --prompt 替代）。
17. **gitignore 忽略规则** — `skills.ts:16-65`（.gitignore/.ignore/.fdignore 解析）—
    技能扫描时排除被忽略的目录（如 node_modules 里的 SKILL.md）。v1 不扫忽略。
18. **根目录 .md 直接当技能** — `skills.ts:163` 注释的第二种形态 +
    `docs/skills.md:37-39` — 在 ~/.pi/agent/skills/ 和 .pi/skills/ 里，
    根目录散落的 .md 文件也算技能。v1 只认 SKILL.md 目录形态。
19. **逐目录诊断（ResourceDiagnostic）** — `skills.ts:83-86` — 技能加载失败时
    给用户看哪坏了。v1 静默跳过。

### D. 工具层

20. **edit 的 diff 渲染 / unified patch 生成** — `edit.ts:6,13-22`（edit-diff.ts）—
    编辑前预览 diff、生成 patch 文件。v1 纯文本替换，保留"多段 + 非增量 + 不重叠"
    语义（`edit.ts:45-54` 的 schema 描述原样保留在 schema 里）。
21. **bash 进程树管理** — `bash.ts:11-17`（killProcessTree/trackDetachedChildPid）—
    超时/中断时杀整个进程树、跟踪后台进程防僵尸。v1 用 subprocess timeout。
22. **bash 环境与 shell 配置** — `bash.ts:12-13`（getShellConfig/getShellEnv）—
    继承用户 shell 的 env/alias。v1 直接 subprocess shell=True。
23. **工具渲染（行号高亮/diff 着色/输出折叠）** — `read.ts:170`（formatReadResult）、
    `bash.ts` 的 OutputAccumulator — 都是 TUI 渲染。v1 纯文本 + 行号前缀。
24. **TypeBox schema 校验（validateToolArguments）** — pi-ai — 参数进工具前先过
    JSON Schema 校验。v1 由每个工具自己兜底（ToolError）。
25. **文件变更队列（file-mutation-queue.ts）** — 并发工具调用时对同一文件的写串行化。
    v1 顺序执行，天然无竞态。
26. **工具采样（getExperimentalToolSampling）** — 实验性开关。v1 砍。
27. **图像处理（read 工具读图片转描述）** — `read.ts:29-33,93-97`（processImage/
    vision）— read 支持图片文件。v1 只读文本。

### E. 系统层（Pi 也没有/故意没有的，v1 继承）

28. **无内置权限系统** — Pi 官方设计（README Permissions 节：默认以启动用户权限
    运行，要隔离自己容器化）。v1 继承此哲学——这也是 Pi 与 Hermes 的最大分野
    （Hermes 有 toolset 命名空间 + shadow 防护 + check_fn 门控）。
29. **无 MCP / 无 sub-agents / 无 plan mode / 无内置 todo** — Pi 官方哲学
    （README Philosophy 节，全部"build it with extensions or install a package"）。
    v1 继承：这些是 Pi 的"减"，不是 v1 的"砍"。
30. **多 provider 模型目录（models.generated.ts）** — pi-ai 从各厂商 catalog 生成
    的模型元数据表。v1 单一 OpenAI 兼容端点，模型名手输。
31. **重试/退避/凭证轮换（RetryPolicy）** — pi-ai — 网络抖动、429、key 过期的
    防御。v1 裸调用（LLM error 直接返回给模型）。
32. **telemetry / evals / server / protocol / client / session-backends 包** —
    遥测契约、评测框架、RPC 进程集成、SDK 嵌入、多会话后端。v1 全砍。

## 扩展路线图（重建顺序 = 从易到难补防御）

1. **并行工具执行** — `agent-loop.ts:489` executeToolCallsParallel（concurrent.futures）
2. **流式输出** — `agent-loop.ts:317` 事件流（打字机效果）
3. **steering（Enter 中途插话）** — `agent-loop.ts:167,259`（Pi 招牌，值得做）
4. **compaction 上下文压缩** — 摘要历史（token 管理，面试高频考点）
5. **会话持久化 + 分叉** — session-manager + SessionTree
6. **重试/退避** — pi-ai RetryPolicy（429/超时）
7. **权限钩子** — beforeToolCall（自建确认流，Pi 官方推荐路线）
8. **多 provider** — 统一 client 接口
9. **扩展系统** — extensions + prompt templates（包管理形态）

每一步都可以单独做、单独验证，不破坏现有循环。
