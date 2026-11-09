# AgentOrch · 多智能体编排调度平台

> 赛题一「Agent 编排创新应用」参赛项目。
> 当前进度：**Sprint 0（骨架 + 大模型链路）** + **模块 1（Agent 定义与配置）** + **模块 2（任务调度器）** + **验收维度 / 落盘交接 / Self-Loop** 已完成。

第一阶段把 FastAPI 分层骨架与 DeepSeek 调用链路跑通；模块 1 定义了 6 个固定角色、
写死工具权限，并用一份 JSON 描述团队；模块 2 实现了
「任务清单 → 依赖检查 → 拓扑排序 → 顺序执行」的调度闭环；
之后又把「执行状态」和「验收结论」拆成两个正交维度，代码改为落盘交接，
并在验收驳回时自动进入修复循环。

![联调台](docs/console.png)

---

## 当前已实现

| 能力 | 说明 |
| --- | --- |
| FastAPI 分层骨架 | `api / core / llm / agents / web`，配置、日志、异常统一出口 |
| DeepSeek 客户端 | 基于 OpenAI 兼容协议封装：普通调用、SSE 流式、JSON 模式、推理模型 |
| 错误归一化 | 鉴权失败、限流、超时、网络不可达、上游 5xx 全部映射为业务错误码 |
| 6 个内置 Agent | 队长 / 产品经理 / 架构师 / 开发 / 测试 / 评审，各自独立 system prompt |
| 工具权限 | 每个角色写死 `allowed_tools`，import 时校验，越权抛 403 |
| 团队配置 | `teams/software_team.json`：定义队长与成员映射，启动时装配并校验 |
| 单 Agent 试跑 | `POST /agents/{id}/run` 与 CLI，验证「prompt + 调 API」链路 |
| 任务调度器 | 任务清单 + 依赖检查（含环检测）+ 拓扑排序 + 顺序执行 |
| 队长自动拆解 | 一句 goal → 队长输出 DAG → 解析校验 → 顺序执行 |
| 双维度状态 | 执行状态（调度器）与验收结论（评审 Agent）分离，汇总为 `completed` / `rejected` |
| 工作区落盘 | 每个 run 独立 `data/workspaces/<run_id>/`，代码与产出可打开、可追溯 |
| 文件工具 | `file_list` / `file_read` / `file_write`，Agent 按权限调用，交接只给清单 |
| Self-Loop | 验收驳回后自动追加「修复 + 复评」任务，最多 N 轮，超限转人工 |
| 运行记录 | 内存存储任务状态、耗时、token 与输出，支持运行详情查询 |
| 失败传播 | 上游失败 → 下游 `skipped`，无关任务继续执行 |
| 离线 Mock | `LLM_MOCK=true` 时不发真实请求，单测与前端联调无需 Key |
| 联调台页面 | `http://127.0.0.1:8000/`，可直接对话、流式输出、查看延迟与用量 |
| 单元测试 | 62 个用例，覆盖链路、角色、团队校验、依赖检查、调度状态机、拆解、工作区与 Self-Loop |

## 模块 1：Agent 定义与配置

### 6 个内置角色

角色是**固定写死**的 6 个类，不做动态注册；每个类的核心就是一段 system prompt。

| Agent id | 角色 | 职责 | 工具权限 |
| --- | --- | --- | --- |
| `captain` | 队长 | 拆解任务 DAG、按依赖调度、汇总验收 | `task_plan` `task_dispatch` `knowledge_search` |
| `product_manager` | 产品经理 | 需求规格、接口定义、数据字段、验收标准 | `knowledge_search` `web_search` `file_write` |
| `architect` | 架构师 | 技术方案、模块划分、表结构、接口契约 | `knowledge_search` `file_read` `file_write` |
| `developer` | 开发 | 按设计编码，按失败日志修复 | `file_read` `file_write` `python_exec` `shell_exec` |
| `tester` | 测试 | 生成并运行 pytest，输出测试报告 | `file_read` `file_write` `python_exec` `test_runner` |
| `reviewer` | 评审 | 独立验收、证据化结论、安全检查 | `file_read` `knowledge_search` `test_runner` |

队长不持有任何代码执行工具（`shell_exec` / `python_exec`），与执行成员完全隔离；
评审不持有写权限，只能读代码、跑测试、给结论。

### 团队 JSON

团队配置只决定「队长是谁、有哪些成员」，不承载 prompt：

```json
{
  "id": "software_team",
  "name": "软件需求工程 AI 团队",
  "captain": "captain",
  "members": [
    { "id": "captain", "role": "captain" },
    { "id": "product_manager", "role": "product_manager" },
    { "id": "architect", "role": "architect" },
    { "id": "developer", "role": "developer" },
    { "id": "tester", "role": "tester" },
    { "id": "reviewer", "role": "reviewer" }
  ]
}
```

启动时装配并校验：成员 id 唯一、角色必须存在、队长必须在成员列表里且角色为 `captain`，
配置错误直接启动失败，避免带病运行。成员支持可选 `name` 覆盖显示名。

### 单独试跑一个 Agent

```powershell
cd AgentOrch\backend

# 查看团队成员与工具权限
.\.venv\Scripts\python.exe scripts\run_agent.py --list

# 队长拆解任务
.\.venv\Scripts\python.exe scripts\run_agent.py --agent captain --task "做一个学生成绩管理系统的后端 API"

# 架构师基于需求文档做设计
.\.venv\Scripts\python.exe scripts\run_agent.py --agent architect --task "设计表结构与接口" --context "需求文档内容……"

# 无 Key 时加 --mock
.\.venv\Scripts\python.exe scripts\run_agent.py --agent captain --task "演示" --mock
```

也可以走 HTTP：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/agents/captain/run `
  -H "Content-Type: application/json" `
  -d "{\"task\":\"做一个学生成绩管理系统的后端 API\"}"
```

响应包含 `content`、`model`、`usage`、`latency_ms`、`allowed_tools`，便于后续调度与审计。

## 模块 2：任务调度器

调度链路支持两种入口：

- **队长自动拆解**：`POST /runs {"goal": "..."}`，队长先产出任务 DAG，解析校验后直接顺序执行；
- **手动任务清单**：`POST /runs {"tasks": [...]}`，跳过拆解，直接执行给定清单。

拆解与执行之间可以插入人工确认：`POST /runs/plan` 只出计划不执行。

```json
{
  "goal": "做一个学生成绩管理系统的后端 API",
  "tasks": [
    { "id": "T1", "title": "需求规格", "owner": "product_manager", "goal": "写需求文档" },
    { "id": "T2", "title": "技术设计", "owner": "architect", "goal": "写设计文档", "depends_on": ["T1"] },
    { "id": "T3", "title": "编码实现", "owner": "developer", "goal": "实现接口", "depends_on": ["T2"] }
  ]
}
```

### 队长拆解（goal → 任务清单）

- 调用队长 Agent，要求输出「说明 + json 代码块形式的任务 DAG」；
- [planner.py](backend/app/orchestration/planner.py) 从输出里提取 JSON，兼容围栏和非围栏两种写法；
- 逐个任务按 `TaskSpec` 校验，再交给调度器做依赖检查与拓扑排序；
- 解析失败返回 422（`plan_parse_failed`），不会创建空 run；
- `plan_source` 字段标明这次是 `captain` 拆的还是 `manual` 传入的。

### 依赖检查（执行前）

- 任务 id 唯一、负责人必须在当前团队中
- 依赖必须存在、不能依赖自己、不能重复声明
- Kahn 拓扑排序检测环，有环直接 400（`task_cycle`）
- 单次运行任务数上限 20

`POST /api/v1/runs/validate` 只校验不执行，返回拓扑序，便于前端画图或人工确认。

### 顺序执行

- 按拓扑序逐个执行，同一时刻只有一个任务在跑，同层任务也不会并行
- 代码与产出落盘到运行工作区，下游 `context` 只有工作区清单（文件名 + 大小），不再贴全文
- Agent 通过 `file_list` / `file_read` / `file_write` 工具按需读写文件
- 任务失败：下游标记 `skipped`，无关任务继续执行；整个 run 最终为 `failed`
- 每个任务记录状态、耗时、token 用量、模型、产出文件与错误信息
- `POST /api/v1/runs` 默认异步执行（返回 202 + run_id），加 `?wait=true` 则等执行完返回

状态机：任务 `pending → running → completed / failed / skipped`；
运行 `pending → running → completed / failed`。

### 真实运行示例

**手动清单**：3 个任务（产品经理 → 架构师 → 开发）顺序执行，22.2s、6945 tokens，
架构师引用了上游的 AC1，开发沿用了架构师定的三张表。

**队长自动拆解**：一句需求拆出 6 个任务（产品经理 → 架构师 → 开发 ×2 → 测试 → 评审），
队长 4.6s 出计划，全链路 125s、约 39k tokens，6/6 执行完成。
这次运行也暴露了一个真实问题：开发产出被上下文截断，测试和评审都据此判了「不完整」——
**执行完成 ≠ 验收通过**，这正是下一步 Self-Loop 要接的口子。

```powershell
# 只拆解，不执行
curl.exe -X POST http://127.0.0.1:8000/api/v1/runs/plan `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"做一个学生成绩管理系统的后端 API\"}"

# 一句话需求直接跑完
curl.exe -X POST "http://127.0.0.1:8000/api/v1/runs?wait=true" `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"做一个学生成绩管理系统的后端 API\"}"
```

也可以直接用 CLI 看拆解结果和执行进度：

```powershell
cd AgentOrch\backend

# 拆解 + 顺序执行
.\.venv\Scripts\python.exe scripts\run_pipeline.py --goal "做一个学生成绩管理系统的后端 API"

# 只看队长拆出什么，不执行
.\.venv\Scripts\python.exe scripts\run_pipeline.py --goal "..." --plan-only

# 离线跑通全流程
.\.venv\Scripts\python.exe scripts\run_pipeline.py --goal "..." --mock
```

已知限制：运行记录存在内存里，进程重启即丢失；并发、重试、断点续跑留给下一阶段。

## 模块 3：验收与 Self-Loop

### 执行 ≠ 验收

一次 run 同时维护两个正交维度：

| 字段 | 取值 | 谁负责 |
| --- | --- | --- |
| `execution_status` | `pending / running / completed / failed` | 调度器（有没有异常） |
| `acceptance.status` | `pending / passed / rejected` | 评审 Agent（内容合不合格） |
| `status` | `completed / rejected / failed / running` | 汇总 |

评审输出里的「总体结论」被解析成验收结论：`通过` / `有条件通过` → `passed`，
`驳回` → `rejected`。执行全部完成但评审驳回时，`status=rejected`、`execution_status=completed`，
两个维度不会互相覆盖。

### 验收驳回 → 自动修复

`max_repair_rounds`（默认 2）控制 Self-Loop：

1. 首轮执行结束后由评审 Agent 给出结论；
2. 若驳回，追加 `R<n>-fix`（开发，读取评审记录和代码后修复）与 `R<n>-review`（复评）；
3. 复评通过 → `status=completed`；仍驳回且轮次用尽 → `status=rejected` + `needs_human=true`。

修复任务会先 `file_read` 读 `tasks/<评审任务>.md` 里的完整评审记录，再检查工作区代码，
修复后用 `file_write` 写回完整文件——不再依赖 prompt 里的残缺代码片段。

完整的可验证清单见 [docs/verification.md](docs/verification.md)（含「故意制造失败」的降级测试）。

实测：一句需求拆 5 个任务，下游 context 只有 47–480 字符，工作区落盘 14 个真实文件，
评审「有条件通过」被正确解析为 `passed`，run 状态 `completed`。

## 目录结构

```
AgentOrch/
├── backend/
│   ├── app/
│   │   ├── main.py              # 应用入口：lifespan、中间件、异常处理、静态页
│   │   ├── api/
│   │   │   ├── deps.py          # 依赖注入（LLM 客户端、团队）
│   │   │   ├── schemas.py       # Pydantic 请求/响应模型
│   │   │   └── v1/
│   │   │       ├── router.py    # 路由聚合，后续挂 workflows/tasks/runs
│   │   │       ├── system.py    # 健康检查、模型列表、LLM ping
│   │   │       ├── chat.py      # 普通对话 + SSE 流式对话
│   │   │       ├── agents.py    # 角色、工具、团队、单 Agent 试跑
│   │   │       └── runs.py      # 依赖校验、创建运行、查询运行
│   │   ├── agents/
│   │   │   ├── base.py          # BaseAgent / AgentSpec / AgentRunResult
│   │   │   ├── tools.py         # 工具注册表与权限异常
│   │   │   ├── tooling.py       # 文件工具的 function-calling 定义
│   │   │   ├── registry.py      # 团队装配与配置校验
│   │   │   ├── teams/software_team.json
│   │   │   └── roles/           # 6 个角色类（prompt 都在这里）
│   │   ├── orchestration/
│   │   │   ├── models.py        # TaskSpec / TaskState / RunState / AcceptanceState
│   │   │   ├── planner.py       # 队长输出解析、任务校验
│   │   │   ├── scheduler.py     # 依赖校验、拓扑排序、顺序执行
│   │   │   ├── acceptance.py    # 评审结论解析（通过 / 驳回）
│   │   │   ├── self_loop.py     # 驳回后追加修复与复评任务
│   │   │   ├── workspace.py     # 运行工作区：落盘、清单、文件工具执行
│   │   │   └── store.py         # 内存运行记录
│   │   ├── core/                # config / errors / logging
│   │   ├── llm/client.py        # DeepSeek 客户端封装（含 function calling 循环）
│   │   └── web/index.html       # 零构建联调台
│   ├── tests/                   # pytest
│   ├── scripts/
│   │   ├── smoke.py             # 端到端冒烟
│   │   ├── run_agent.py         # 单 Agent 试跑 CLI
│   │   └── run_pipeline.py      # 队长拆解 + 顺序执行 + Self-Loop CLI
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                   # python run.py
├── docs/
│   ├── console.png              # 联调台截图
│   └── verification.md          # 验收与 Self-Loop 验证清单
└── README.md
```

## 快速开始

```powershell
cd AgentOrch\backend

# 1. 创建虚拟环境并安装依赖（已创建过可跳过）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 配置密钥
Copy-Item .env.example .env
#   编辑 .env，填写 DEEPSEEK_API_KEY=sk-xxxx

# 3. 启动
python run.py
```

启动后：

- 联调台：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>
- 团队配置：<http://127.0.0.1:8000/api/v1/team>

### 无 Key 也能跑

```powershell
$env:LLM_MOCK="true"
python run.py
```

Mock 模式下所有接口照常返回（内容带 `【MOCK 模式】` 前缀），便于单测和前端联调。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 服务状态与 LLM 配置状态 |
| GET | `/api/v1/llm/models` | 可选模型列表 |
| POST | `/api/v1/llm/ping` | 真实调用一次模型，验证连通性 |
| POST | `/api/v1/chat` | 对话，一次性返回 |
| POST | `/api/v1/chat/stream` | 对话，SSE 流式返回 |
| GET | `/api/v1/agents/roles` | 6 个内置角色及工具权限 |
| GET | `/api/v1/agents/tools` | 全部工具及说明 |
| GET | `/api/v1/team` | 当前团队配置与成员详情（含 prompt） |
| GET | `/api/v1/agents/{agent_id}` | 单个 Agent 配置 |
| POST | `/api/v1/agents/{agent_id}/run` | 试跑单个 Agent |
| POST | `/api/v1/runs/plan` | 队长拆解任务，只出计划不执行 |
| POST | `/api/v1/runs/validate` | 依赖检查，只返回拓扑序不执行 |
| POST | `/api/v1/runs` | 创建并执行（给 tasks 直接跑，只给 goal 先拆解） |
| GET | `/api/v1/runs` | 最近运行列表（摘要，不含输出） |
| GET | `/api/v1/runs/{run_id}` | 运行详情（含每个任务的输出与用量） |

`POST /runs` 的 `max_repair_rounds` 控制验收驳回后的修复轮次（默认 2，0 表示不循环）。
Run 响应里除了任务列表，还包含 `execution_status`、`acceptance`、`rounds`、
`needs_human` 与 `workspace_dir`。

### 调用示例

```powershell
# 连通性探测
curl.exe -X POST http://127.0.0.1:8000/api/v1/llm/ping

# 普通对话
curl.exe -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"用一句话介绍 AgentOrch\"}]}"

# 流式对话（SSE）
curl.exe -N -X POST http://127.0.0.1:8000/api/v1/chat/stream `
  -H "Content-Type: application/json" `
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"写一个 Python 快排\"}]}"
```

流式事件格式：

```
data: {"type":"delta","delta":"你"}
data: {"type":"delta","delta":"好"}
data: {"type":"done","finish_reason":"stop","latency_ms":1234,"usage":{...},"mode":"live"}
```

错误事件：`{"type":"error","code":"llm_timeout","message":"..."}`。

## 配置项（backend/.env）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 密钥，为空且非 mock 时对话接口返回 503 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容任意 OpenAI 协议网关 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 默认模型 |
| `DEEPSEEK_REASONER_MODEL` | `deepseek-reasoner` | 推理模型（自动忽略 temperature） |
| `LLM_TEMPERATURE` | `0.7` | 默认温度 |
| `LLM_TIMEOUT` | `120` | 单次请求超时（秒） |
| `LLM_MAX_RETRIES` | `2` | SDK 层重试次数 |
| `LLM_MOCK` | `false` | 本地模拟开关 |
| `DEFAULT_TEAM` | `software_team` | 启动时装配的团队配置 id |
| `ENVIRONMENT` | `dev` | `dev` 时 uvicorn 开启热重载 |
| `PORT` | `8000` | 监听端口 |

## 测试

```powershell
cd AgentOrch\backend

# 单元测试（mock，不产生真实调用）
.\.venv\Scripts\python.exe -m pytest

# 端到端冒烟（需先启动服务，会真实调用模型）
.\.venv\Scripts\python.exe scripts\smoke.py
```

测试默认注入 `LLM_MOCK=true`，不会产生真实调用与费用。

> 小坑：若本机配置了系统代理，`httpx` 默认会走代理导致访问 127.0.0.1 返回 502，
> `scripts/smoke.py` 已固定 `trust_env=False`；自己写脚本时注意同样处理。

## 设计说明：为什么这样分层

- **LLM 客户端与业务解耦**：Agent、工作流只依赖 `DeepSeekClient` 的数据结构
  （`ChatResult` / `StreamChunk` / `Usage`），将来接多模型路由只改一个文件。
- **Prompt 就是配置**：每个角色一个类，prompt 作为类属性；改 prompt 只改一个文件，
  可 diff、可 review，不散落在数据库或 JSON 里。
- **权限在 import 阶段校验**：`BaseAgent.__init_subclass__` 检查工具是否注册、
  prompt 是否为空、温度是否合法；写错直接启动失败，不会带病运行。
- **错误先归一化再抛给 API**：`openai` 的异常类型不外泄，前端拿到稳定的
  `{code, message}`，便于调度引擎按错误类型决定重试 / 降级。
- **连接复用**：`AsyncOpenAI` 在 lifespan 中创建一次、全局共享，避免每请求建连。
- **Mock 是一等公民**：没有 Key 也能演示完整链路，评审复现成本低。
- **依赖先校验再执行**：调度器不信任输入，环、悬空依赖、未知负责人在建 run 前就拒绝，
  执行阶段不需要再处理这类错误。
- **失败只影响下游**：一个任务失败不会拖垮整张图，无关分支继续跑，
  失败原因写进 `TaskState.error`，便于 Self-Loop 后续生成修复任务。
- **拆解与执行解耦**：`/runs/plan` 只出计划，`/runs` 才执行；
  计划可以先人工看一眼，也可以直接 `plan_source=captain` 一路跑到底。
- **执行与验收解耦**：调度器只对「有没有跑完」负责，评审 Agent 才对「合不合格」负责；
  两个状态分开存，驳回时不会被 `completed` 掩盖。
- **交接靠文件，不靠 prompt**：代码落盘、下游拿清单按需读取，
  避免几万字的代码在上下文里被截断。
- **工具调用双层兼容**：优先标准 `tool_calls`；上游网关偶尔把调用写成 DSML 文本时，
  自动解析并执行，避免工具调用半途丢失。

## 下一步

1. **代码执行工具**：`python_exec` / `test_runner` 真正跑起来，让测试 Agent 能执行 pytest，而不只是写用例
2. **并行调度**：无依赖任务并发执行（信号量限流），把「顺序」升级成「分层并行」
3. **结构化验收**：把评审表格解析成「每条 AC 的通过情况」，修复任务只带失败项
4. **调度引擎升级**：`attempt_id` 原子认领、事件驱动派发、超时回收、SQLite 持久化
5. **实时推送**：WebSocket 事件总线，前端监控面板接入
6. **前端编排画布**：Vue 3 + AntV X6，拖拽生成任务清单

> 详细设计见《AgentOrch_设计方案.docx》，验证步骤见 [docs/verification.md](docs/verification.md)。
