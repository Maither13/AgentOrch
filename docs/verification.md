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

两种触发条件（任一即可）：

1. **测试门**：`test_runner` 的 pytest 退出码非 0，即使评审说「通过」也强制 `rejected`；
2. **评审驳回**：评审「总体结论」为 `驳回`。

每轮追加 3 个任务，串行执行：

```
R<n>-fix（开发：带失败日志和评审记录修代码）
   ↓
R<n>-test（测试：重新跑 pytest）
   ↓
R<n>-review（评审：重新验收）
```

轮次由 `max_repair_rounds` 控制（默认 3）。

**验证方式**：看日志与任务列表：

```
Self-Loop 第 1 轮：追加 3 个任务（R1-fix, R1-test, R1-review）
```

任务列表里出现 `R1-fix` / `R1-test` / `R1-review`；`R1-test.test_result.exit_code` 为 0
且复评通过后 `status` 变为 `completed`。

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

其中 `test_self_loop_exhausted_needs_human` 模拟评审连续两轮驳回，
断言最终状态为 `rejected`、`needs_human=True`、共追加 6 个修复任务；
`test_failing_test_overrides_review_and_marks_human` 验证「评审通过但 pytest 失败」会被测试门拦下，
`test_failing_test_triggers_repair_then_passes` 验证测试失败能触发循环且重测通过后收口。

**真实模型验证**：挑一个评审大概率挑出问题的需求（比如故意不给验收标准），
把 `max_repair_rounds` 设为 1 或 2，观察 `rounds` 与 `needs_human`：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/runs?wait=true" `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"做一个成绩查询接口，简单点就行\",\"max_repair_rounds\":2}"
```

## 5. 回归命令

```powershell
.\.venv\Scripts\python.exe -m pytest                 # 84 个用例
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

### Self-Loop 实测

早期版本用 2 任务链（修复 → 复评）以真实模型验证过闭环：

```
T1         completed  → 只落盘 app/health.py
T2         completed  → 总体结论：驳回（缺 tests/test_health.py）
Self-Loop: 第 1 轮修复
R1-fix     completed  → 补齐 tests/test_health.py、pytest.ini
R1-review  completed  → 总体结论：有条件通过
最终：status=completed, acceptance=passed, rounds=1
```

模块 5 把每轮扩展成「修复 → 重测 → 复评」并加入测试门后，为避免重复消耗模型额度，
新链路改用确定性单测覆盖：

- `test_self_loop_repairs_and_passes`：评审驳回 → 追加 R1-fix / R1-test / R1-review → 通过；
- `test_failing_test_overrides_review_and_marks_human`：评审通过但 pytest 失败 → 测试门判 rejected；
- `test_failing_test_triggers_repair_then_passes`：测试失败触发循环，重测通过后收口；
- `test_self_loop_exhausted_needs_human`：两轮仍失败 → `needs_human=true`。

`test_runner` 的真实执行此前已单独实测（12 个用例工作区，报告 `12 passed`）。

## 7. 固定工作流与分层并行实测（真实模型）

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/workflows/software_development/runs?wait=true" `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"做一个最小 FastAPI 服务\",\"max_parallel\":2,\"max_repair_rounds\":0}"
```

7 个任务按 6 层执行，日志：

```
19:22:49 并行层启动：2 个任务（S3, S4）
19:22:49 任务 S3 启动（owner=developer，context=207 字符）
19:22:49 任务 S4 启动（owner=tester，context=207 字符）
19:23:36 并行层启动：1 个任务（S5）      ← 等 S3/S4 都结束才进入下一层
```

S3 用时 20.6s、S4 用时 46.2s，并行层总耗时取两者最大值而不是相加（67s）。
全链路 154s，评审驳回（测试执行证据缺失），`max_repair_rounds=0`：

```
status = rejected
execution_status = completed
acceptance.status = rejected
acceptance.verdict = 驳回
needs_human = true
```

这同时验证了「执行完成 ≠ 验收通过」和「轮次耗尽转人工」两条降级路径。

## 8. 执行日志与测试执行

### 执行日志

每个 run 的 `logs` 会记录任务开始/完成/失败、并行层、Self-Loop 与验收结论：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/runs/{run_id}/logs
```

单测 `tests/test_scheduler.py::test_run_logs` 断言日志存在且包含任务与运行结束记录。
日志是内存列表（上限 200 条），和运行记录同生命周期。

### 测试执行

`test_runner` 在工作区根目录执行 `python -m pytest -q`，返回退出码与输出。
单测 `tests/test_workspace.py::test_test_runner_passes` / `test_test_runner_failure`
分别验证通过和失败两条路径；pytest 产生的缓存目录不会进入工作区清单。

真实模型实测：测试 Agent 在 12 个用例的工作区里调用 `test_runner`，
工作区生成 `.pytest_cache`，报告 `12 passed`。

## 9. 验收缺失探针

有评审任务、但没有解析出「总体结论」时：

```
acceptance.status = needs_revision
status = needs_revision
needs_human = true
```

不会进入 Self-Loop，也绝不会算 `completed`。单测：
`tests/test_self_loop.py::test_review_without_conclusion_needs_revision`。

没有评审任务的 run 仍然保持 `acceptance=pending`、`status=completed`（执行完成，未要求验收）。

## 10. 真机失败链路（必做验收）

手动构造首轮必失败场景：T1 开发只写 `app/main.py`；T2 评审要求同时存在
`app/main.py`、`tests/test_health.py`、`docs/acceptance.md`，缺一即驳回。

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/runs?wait=true" `
  -H "Content-Type: application/json" `
  -d "{\"goal\":\"真机制造失败\",\"max_repair_rounds\":2,\"tasks\":[...]}"
```

实测结果（84s）：

```
T1         completed  → app/main.py
T2         completed  → 总体结论：驳回；test_runner 退出码 5（没有测试可收集）
Self-Loop 第 1 轮：追加 3 个任务（R1-fix, R1-test, R1-review）
R1-fix     completed  → 补齐 tests/test_health.py、docs/acceptance.md
R1-test    completed  → test_runner 退出码 0
R1-review  completed  → 总体结论：通过
最终：status=completed, rounds=1, needs_human=false
```

工具留痕示例：T1 调用了 `file_list` / `file_write` / `python_exec`；
T2 调用了 `file_list` / `file_read` / `test_runner`；R1-test 调用了
`file_read` / `test_runner` / `python_exec`。




