# 测试报告：R2-fix 第 2 轮修复验证

## 结论（先说结果）

**修复未生效，本轮无法验证任何验收标准。** 退出码 0 是**假绿**：33 个用例全部 `SKIPPED`，`passed=0 / failed=0 / skipped=33`。

根因不是业务代码，而是**运行环境缺少依赖**：`sqlalchemy` 未安装，`app.main` 导入失败，`conftest.py` 的 `_require_app` 夹具把全部用例 skip 掉。

---

## 1. 测试用例清单

工作区现有测试资产（本轮未新增，仅执行）：

| 编号 | 对应 AC | 前置条件 | 步骤 | 预期结果 |
|---|---|---|---|---|
| TC1–TC14 | AC1–AC6、AC27（学生） | 应用可导入、内存库建表 | `tests/test_students.py` 全部用例 | 201/200/204 与 `{error_code,message,details}` 结构断言通过 |
| TC15–TC28 | AC7–AC8、AC27（课程） | 同上 | `tests/test_courses.py` 全部用例 | 同上 |
| TC29–TC33+ | AC9–AC19（成绩） | 同上 | `tests/test_scores.py` | 同上 |
| — | AC20–AC23（统计） | 同上 | `tests/test_statistics.py` | **文件不存在** |
| — | AC24–AC25（批量） | 同上 | `tests/test_batch.py` | **文件不存在** |
| — | AC26、AC28（鉴权/分页） | 同上 | `tests/test_auth_pagination.py` | **文件不存在** |

> 说明：`tasks/R2-fix.md` 声称已新建 `test_scores.py` / `test_statistics.py` / `test_batch.py` / `test_auth_pagination.py`，但工作区 `file_list` 中 `tests/` 只有 `conftest.py`、`test_courses.py`、`test_students.py` 三个文件。**R2-fix 文档中的测试代码并未落盘**（`test_scores.py` 内容只存在于任务文档里，且文档内容在 `test_ac11_score_two_decimals_rejected` 处被截断）。

## 2. 测试代码

本轮为**回归验证**，未新增测试文件（约束：只测试、不修改业务代码；且工具预算内 test_runner 仅运行 1 次）。现有用例已由开发/前序轮次落盘，直接执行。

## 3. 执行结果

**命令**：`python -m pytest -q`（工作区根目录）
**退出码**：`0`
**统计**：通过 **0** / 失败 **0** / 跳过 **33**

**关键输出**：

```
sssssssssssssssssssssssssssssssss                                        [100%]
============================== warnings summary ===============================
  .../fastapi/testclient.py:1: StarletteDeprecationWarning:
  Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
=========================== short test summary info ===========================
SKIPPED [1] tests\test_courses.py:8:   应用不可导入，跳过集成测试（原因：ModuleNotFoundError: No module named 'sqlalchemy'）
SKIPPED [1] tests\test_courses.py:24:  ... ModuleNotFoundError: No module named 'sqlalchemy'
...（test_courses.py 共 14 条，test_students.py 共 19 条，原因完全相同）
SKIPPED [1] tests\test_students.py:234: ... ModuleNotFoundError: No module named 'sqlalchemy'
```

**环境核查证据**：

```
python: E:\...\backend\.venv\Scripts\python.exe 3.14.4
sqlalchemy  -> False   (未安装)
fastapi     -> True    (0.162.0)
pydantic    -> True    (2.14.2)
httpx       -> True    (0.28.1)
pytest      -> True    (9.2.0)
```

`requirements.txt` 声明了 `sqlalchemy>=2.0,<2.1`，但当前 venv 中 `pip list` 无任何 SQLAlchemy 条目。

**失败链路**：
1. `app/db.py`、`app/models.py`、`app/repositories/*` 均 `import sqlalchemy`；
2. `tests/conftest.py:19-22` 的 `from app.main import app` 抛 `ModuleNotFoundError: No module named 'sqlalchemy'`，被 `except Exception` 捕获 → `app = None`；
3. `_require_app`（session 级 autouse）对每个用例执行 `pytest.skip(...)`；
4. pytest 对「全部 skip」返回退出码 0 → **CI 会误判为通过**。

这与 R2-fix 文档中描述的上一轮假绿（`passed=0 / skipped=33 / 退出码 0`）**现象完全一致**，只是根因从「HTTP 层缺失」变成了「依赖缺失」。

## 4. 覆盖缺口

| 缺口 | 原因 | 建议 |
|---|---|---|
| **AC1–AC28 全部未验证** | 环境缺 `sqlalchemy`，应用无法导入 | 执行 `pip install -r requirements.txt`（或至少 `pip install "sqlalchemy>=2.0,<2.1"`）后重跑；这是**唯一阻塞项** |
| AC9–AC19（成绩） | `tests/test_scores.py` 未落盘 | 开发需把 R2-fix 文档中的测试代码真正写入工作区，并补全被截断的 `test_ac11_score_two_decimals_rejected` 等用例 |
| AC20–AC23（统计） | `tests/test_statistics.py` 未落盘 | 同上 |
| AC24–AC25（批量） | `tests/test_batch.py` 未落盘 | 同上 |
| AC26、AC28（鉴权/分页） | `tests/test_auth_pagination.py` 未落盘 | 同上 |
| 假绿风险 | `conftest.py` 用 `except Exception` 吞掉导入错误并 skip | 建议改为：依赖缺失时 `pytest.exit(..., returncode=1)` 或 `pytest.fail`，避免「全 skip = 绿」；或加 `--strict-markers` + CI 断言 `skipped == 0` |

**给开发的复现步骤**：
1. 在 `E:\download\software\workplace\AgentOrch\backend\.venv` 下执行 `python -m pytest -q`；
2. 观察 33 个 `s` 与 `ModuleNotFoundError: No module named 'sqlalchemy'`；
3. 执行 `pip install -r requirements.txt`；
4. 再次运行，预期应出现真实 `passed/failed` 计数——**此时才能判定 R2-fix 是否真正修复**。

**未伪造任何测试结果**：本轮没有任何用例真正执行到业务代码，因此不对 AC 是否满足做任何结论。