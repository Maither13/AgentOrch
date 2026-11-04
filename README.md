# AgentOrch · 多智能体编排调度平台

> 赛题一「Agent 编排创新应用」参赛项目。当前处于 **Sprint 0：骨架 + 大模型链路打通**。

本阶段目标很小但很关键：把 **FastAPI 后端分层骨架** 与 **DeepSeek API 调用链路** 先跑通，
为后续的 Agent 团队、DAG 工作流、调度引擎、Self-Loop 提供稳定的底座。

![联调台](docs/console.png)

---

## 当前已实现

| 能力 | 说明 |
| --- | --- |
| FastAPI 分层骨架 | `api / core / llm / web` 四层，配置、日志、异常统一出口 |
| DeepSeek 客户端 | 基于 OpenAI 兼容协议封装：普通调用、SSE 流式、JSON 模式、推理模型 |
| 错误归一化 | 鉴权失败、限流、超时、网络不可达、上游 5xx 全部映射为业务错误码 |
| 连通性探测 | `POST /api/v1/llm/ping` 发一次最小真实请求，返回回复、延迟与 token 用量 |
| 离线 Mock | `LLM_MOCK=true` 时不发真实请求，单测与前端联调无需 Key |
| 联调台页面 | `http://127.0.0.1:8000/`，可直接对话、流式输出、查看延迟与用量 |
| 单元测试 | pytest 覆盖健康检查、模型列表、普通对话、流式对话、参数校验 |

## 目录结构

```
AgentOrch/
├── backend/
│   ├── app/
│   │   ├── main.py              # 应用入口：lifespan、中间件、异常处理、静态页
│   │   ├── api/
│   │   │   ├── deps.py          # 依赖注入（共享 LLM 客户端）
│   │   │   ├── schemas.py       # Pydantic 请求/响应模型
│   │   │   └── v1/
│   │   │       ├── router.py    # 路由聚合，后续挂 agents/workflows/tasks
│   │   │       ├── system.py    # 健康检查、模型列表、LLM ping
│   │   │       └── chat.py      # 普通对话 + SSE 流式对话
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings 配置
│   │   │   ├── errors.py        # 领域异常（LLMError 等）
│   │   │   └── logging.py       # 日志初始化
│   │   ├── llm/
│   │   │   └── client.py        # DeepSeek 客户端封装（唯一接触 openai SDK 的地方）
│   │   └── web/
│   │       └── index.html       # 零构建联调台
│   ├── tests/                   # pytest
│   ├── scripts/smoke.py         # 端到端冒烟测试
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                   # python run.py
├── docs/console.png             # 联调台截图
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
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

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
- **错误先归一化再抛给 API**：`openai` 的异常类型不外泄，前端拿到的是稳定的
  `{code, message}`，便于调度引擎按错误类型决定重试 / 降级。
- **连接复用**：`AsyncOpenAI` 在 lifespan 中创建一次、全局共享，避免每请求建连。
- **Mock 是一等公民**：没有 Key 也能演示完整链路，评审复现成本低。

## 下一步（按设计方案推进）

1. **Agent 定义与管理**：`AgentSpec` 数据模型、注册表、版本管理、工具白名单
2. **工作流编排**：`WorkflowStep` + DAG 校验、拓扑分层、`asyncio.gather` 并行执行
3. **任务调度引擎**：三态状态机、`attempt_id` 原子认领、事件驱动派发、超时回收
4. **Self-Loop 控制器**：执行 → 验证 → 修复循环，最大轮次与升级策略
5. **结果验证**：结构化验收记录、双轨验证（自动化测试 + 评审 Agent）
6. **实时推送**：WebSocket 事件总线，前端监控面板接入
7. **持久化**：SQLite（任务、团队配置、日志），后续迁移 PostgreSQL

> 详细设计见《AgentOrch_设计方案.docx》。
