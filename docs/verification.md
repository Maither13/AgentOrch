# 验收与 Self-Loop 验证清单

对应三个改造点的观察指标。所有命令都在 `AgentOrch/backend` 下执行。

## 1. 两个正交维度

一次 run 同时给出两个状态：

| 字段 | 含义 | 谁负责 |
| --- | --- | --- |
| `execution_status` | 任务有没有跑完/报错 | 调度器 |
| `acceptance.status` | 产出合不合格 | 评审 Agent |
| `status` | 汇总：`completed` / `rejected` / `failed` / `running` | 由前两者推导 |

验收结论从评审输出的「总体结论」段落解析：`通过` / `有条件通过` → `passed`，
`驳回` → `rejected`。

**验证方式**：跑一次评审会驳回的流程，检查 run 响应：

```
status = rejected
execution_status = completed
acceptance.status = rejected
acceptance.verdict = 驳回
```

这说明执行没问题，是验收没过——两个维度没有被混在一起。

## 2. 落盘 + 清单交接

代码与产出写到 `backend/data/workspaces/<run_id>/`：

```
<run_id>/
├── app/...              开发 Agent 用 file_write 写的代码
├── tests/...            测试 Agent 写的用例
├── artifacts/...        Agent 自己写的设计/报告
└── tasks/<task_id>.md   系统留档的每个任务完整回复
```

下游任务的 context 只有工作区清单（文件名 + 大小）和上游任务指针，不再贴全文。
Agent 通过 `file_list` / `file_read` 工具按需读取，`file_write` 落盘。

**验证方式**：

```powershell
# 1) 打开工作区，能看到真实 .py 文件
Get-ChildItem data\workspaces\<run_id> -Recurse -File

# 2) 看日志里的 context 长度（应从几万字符降到几百字符）
#    形如：任务 T3 启动（owner=developer，context=312 字符，工作区文件 4 个）
```

## 3. Self-Loop

评审驳回后自动追加 `R<n>-fix`（开发）和 `R<n>-review`（复评）两个任务并继续顺序执行，
轮次由请求参数 `max_repair_rounds` 控制（默认 2）。

**验证方式**：看日志与任务列表：

```
Self-Loop: 第 1 轮修复，追加 2 个任务（R1-fix, R1-review）
```

任务列表里确实出现 `R1-fix` / `R1-review`，且都执行过；复评通过后 `status` 变为 `completed`。

## 4. 降级路径（必做）

修复到上限仍未通过时：

```
status = rejected
execution_status = completed
rounds = max_repair_rounds
needs_human = true
```

**确定性验证**（不消耗模型额度，假 Agent 精确控制每一轮结论）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_self_loop.py -q
```

其中 `test_self_loop_exhausted_needs_human` 模拟评审连续两次驳回，
断言最终状态为 `rejected`、`needs_human=True`、共追加 4 个修复任务。

**真实模型验证**：挑一个评审大概率挑出问题的需求（比如故意不给验收标准），
把 `max_repair_rounds` 设为 1 或 2，观察 `rounds` 与 `needs_human`：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/runs?wait=true" `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"做一个成绩查询接口，简单点就行\",\"max_repair_rounds\":2}"
```

## 5. 回归命令

```powershell
.\.venv\Scripts\python.exe -m pytest                 # 62 个用例
.\.venv\Scripts\python.exe scripts\run_pipeline.py --goal "..." --max-rounds 2
.\.venv\Scripts\python.exe scripts\run_pipeline.py --goal "..." --mock
```

## 6. 实测记录（2026-11-09）

一句需求自动拆出 5 个任务（架构师 → 开发 ×2 → 测试 → 评审），全链路 117s：

| 任务 | 负责人 | context 长度 | 工作区文件数 | 本轮新增/修改 |
| --- | --- | --- | --- | --- |
| T1 | 架构师 | 47 字符 | 0 | `artifacts/design.md` |
| T2 | 开发 | 161 字符 | 2 | `app/main.py`、`tests/` 等 7 个文件 |
| T3 | 开发 | 402 字符 | 11 | `tests/test_health.py` |
| T4 | 测试 | 424 字符 | 12 | `tests/test_health_contract.py` |
| T5 | 评审 | 480 字符 | 14 | — |

结果：`execution_status=completed`、评审「总体结论：有条件通过」→ `acceptance.status=passed`、
`status=completed`、`rounds=0`。工作区落盘 14 个真实文件，`app/main.py` 2.4 KB、
测试文件 4 个，可直接打开检查。

评审驳回与轮次耗尽的路径由 `tests/test_self_loop.py` 用可脚本化的假 Agent 确定性覆盖
（真实模型下评审结论有随机性，不适合作为回归断言）。

