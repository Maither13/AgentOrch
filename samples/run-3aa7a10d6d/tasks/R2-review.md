# 验收记录（R2-fix 第 2 轮重测 · 复审）

## 1. 验收记录

| 标准编号 | 结论 | 证据 | 问题与修复建议 | 严重级别 |
|---|---|---|---|---|
| AC1 | failed | `test_runner` 输出 `sssssssssssssssssssssssssssssssss [100%]`，退出码 0，passed=0 / skipped=33；`tests/conftest.py:19-22` 的 `from app.main import app` 抛 `ModuleNotFoundError: No module named 'sqlalchemy'` → `app=None`，`_require_app`（`conftest.py:52-55`）全量 skip | 环境缺依赖，零断言执行；先 `pip install -r requirements.txt` 再重跑 | P0 |
| AC2 | failed | 同上，`tests/test_students.py` 全部用例 SKIPPED，无执行证据 | 同上 | P0 |
| AC3 | failed | 同上 | 同上 | P0 |
| AC4 | failed | 同上 | 同上 | P0 |
| AC5 | failed | 同上 | 同上 | P0 |
| AC6 | failed | 同上 | 同上 | P0 |
| AC7 | failed | `tests/test_courses.py` 14 条全部 SKIPPED（`R2-test.md` §3 输出摘要） | 同上 | P0 |
| AC8 | failed | 同上 | 同上 | P0 |
| AC9 | failed | `tests/test_scores.py` **文件不存在**（`file_list` 中 `tests/` 仅 `conftest.py`、`test_courses.py`、`test_students.py`）；`app/routers/scores.py:28-45` 路由已实现但无测试执行 | 开发需把 R2-fix 文档中的测试代码真正落盘 | P0 |
| AC10 | failed | 无 `test_scores.py`；`app/models.py` 唯一索引无法运行时验证 | 同上 | P0 |
| AC11 | failed | 无 `test_scores.py`；`app/services/score_service.py` 校验逻辑无执行证据 | 同上 | P0 |
| AC12 | failed | 无 `test_scores.py` | 同上 | P0 |
| AC13 | failed | 无 `test_scores.py` | 同上 | P0 |
| AC14 | failed | 无 `test_scores.py`；`app/routers/scores.py:48-90` 组合过滤已实现但未执行 | 同上 | P0 |
| AC15 | failed | 同上 | 同上 | P0 |
| AC16 | failed | 同上 | 同上 | P0 |
| AC17 | failed | 无 `test_scores.py`；`app/routers/scores.py:110-127` PATCH 已实现但未执行 | 同上 | P0 |
| AC18 | failed | 无 `test_scores.py`；`app/routers/scores.py:141-166` `/histories` 已实现但未执行 | 同上 | P0 |
| AC19 | failed | 无 `test_scores.py`；`app/routers/scores.py:130-138` DELETE 已实现但未执行 | 同上 | P0 |
| AC20 | failed | `tests/test_statistics.py` **文件不存在**；`app/routers/statistics.py:24-58` 已实现但无执行证据 | 补 `test_statistics.py` | P0 |
| AC21 | failed | 同上；`statistics.py:38-48` count=0 返回 null 分支未验证 | 同上 | P0 |
| AC22 | failed | 同上；`statistics.py:61-92` 班级统计未验证 | 同上 | P0 |
| AC23 | failed | 同上；`statistics.py:95-131` 成绩单未验证 | 同上 | P0 |
| AC24 | failed | `tests/test_batch.py` **文件不存在**；`app/routers/batch.py` 存在但无测试 | 补 `test_batch.py` | P0 |
| AC25 | failed | 同上 | 同上 | P0 |
| AC26 | failed | `tests/test_auth_pagination.py` **文件不存在**；`app/routers/scores.py:56-62` 学生越权拦截已实现但无执行证据 | 补 `test_auth_pagination.py` | P0 |
| AC27 | failed | `tests/test_students.py` 全部 SKIPPED，`test_ac27_*` 未执行 | 修环境后重跑 | P0 |
| AC28 | failed | 无分页边界测试资产，无执行证据 | 补 `test_auth_pagination.py` | P0 |

> 判定依据：`test_runner` 退出码 0 但 `passed=0 / skipped=33`，属**假绿**，按规则「证据不足视为 failed」「测试未覆盖的 P0 验收标准视为 failed」，AC1–AC28 全部 failed。

## 2. 总体结论

**驳回。**

理由：
1. **零断言执行（P0）**：本轮 `test_runner` 实测输出 33 个 `s`，`passed=0`、`skipped=33`、退出码 0。没有任何一条验收标准获得可核查的运行时证据。
2. **根因是环境缺依赖（P0）**：`sqlalchemy` 未安装，`app/main.py:15` 的 `from app.db import init_db` 链路导入失败，`conftest.py:19-22` 捕获后 `app=None`，`_require_app` 全量 skip。`requirements.txt` 已声明 `sqlalchemy>=2.0,<2.1`，但 venv 未安装。
3. **测试资产仍缺失（P0）**：`tests/test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` 在工作区中**均不存在**（`file_list` 可核）。`tasks/R2-fix.md` 声称已新建这些文件，但**未落盘**，且文档中 `test_scores.py` 内容在 `test_ac11_score_two_decimals_rejected` 处被截断。
4. **代码侧确有实质进展，但仍不可验收**：`app/main.py`（全局异常处理器 `main.py:44-105`、路由挂载 `main.py:108-112`）、`app/routers/{students,courses,scores,statistics,batch}.py` 均已落盘，首轮 B-1/B-2 的「交付物缺失」已修复；`app/routers/scores.py:56-62` 已消费 `ensure_student_self`，首轮 B-5「鉴权无消费方」已修复。但这些只能作为静态审查证据，不能替代测试执行。
5. **假绿机制未修复（P0）**：`conftest.py:52-55` 仍用 `pytest.skip` 吞掉导入失败，CI 会把「全 skip」判为通过。这是本轮最危险的工程缺陷——它让第 1 轮和第 2 轮连续两次出现假绿。

## 3. 阻断项清单（P0）

| 编号 | 阻断项 | 复现方式 |
|---|---|---|
| B-1 | 运行环境缺 `sqlalchemy`，应用不可导入 | `python -c "import sqlalchemy"` → `ModuleNotFoundError`；`python -c "from app.main import app"` → 同样报错 |
| B-2 | 测试全量 skip，零断言执行（假绿） | `python -m pytest -q` → 输出 33 个 `s`，`passed=0 / skipped=33`，退出码 0 |
| B-3 | `tests/test_scores.py` 缺失，AC9–AC19 无用例 | `file_list` 中 `tests/` 仅 3 个文件；`ls tests/test_scores.py` → 不存在 |
| B-4 | `tests/test_statistics.py` 缺失，AC20–AC23 无用例 | 同上 |
| B-5 | `tests/test_batch.py` 缺失，AC24–AC25 无用例 | 同上 |
| B-6 | `tests/test_auth_pagination.py` 缺失，AC26、AC28 无用例 | 同上 |
| B-7 | 假绿门禁未加严 | `tests/conftest.py:52-55` 仍为 `pytest.skip(...)`；应改为 `pytest.exit(..., returncode=1)` 或 `pytest.fail`，并在 CI 断言 `skipped == 0` |

**修复顺序建议（交开发 Agent）**：
1. `pip install -r requirements.txt`（唯一能解锁全部验证的动作）；
2. 把 R2-fix 文档中的 4 个测试文件真正 `file_write` 落盘，并补全被截断的 `test_ac11_score_two_decimals_rejected` 等用例；
3. 修改 `conftest.py` 的 skip 策略，杜绝假绿；
4. 重跑 `python -m pytest -q`，验收门禁必须同时满足 `passed > 0` 且 `skipped == 0`。

## 4. 安全检查

| 检查项 | 结论 | 依据 |
|---|---|---|
| 注入风险 | 通过（静态审查） | `app/repositories/score_repo.py` 全部使用 SQLAlchemy 表达式与参数绑定，无字符串拼接 SQL；`app/routers/scores.py:48-90` 查询参数经 `Query(max_length=...)` 约束后传入 ORM 表达式 |
| 越权访问 | 部分通过（不可运行时验证） | `app/routers/scores.py:56-62` 学生角色强制覆盖 `student_id` 为本人并调用 `ensure_student_self`；`scores.py:100-102`、`statistics.py:103` 单条查询与成绩单同样校验。逻辑正确，但 AC26 无测试执行 → 视为未验证 |
| 敏感信息泄露 | 通过（静态审查） | `app/main.py:47` 业务异常仅记录 `error_code` 与 `message`；`main.py:88-96` `IntegrityError` 对外返回通用文案，不泄露 SQL；`main.py:99-105` `SQLAlchemyError` 对外返回 `INTERNAL_ERROR`，堆栈仅入日志 |
| 异常处理缺失 | 部分通过 | `app/main.py:44-105` 已注册 `AppError` / `RequestValidationError` / `IntegrityError` / `SQLAlchemyError` 四类处理器，首轮「异常链路未闭环」已修复；但**无任何运行时验证**，且 `conftest.py` 的 `except Exception` 会掩盖真实导入错误，属异常处理反模式 |

**安全结论**：静态代码层面无高危缺陷，首轮指出的「全局异常处理器未注册」已修复；但越权与异常处理两项仍**无法通过运行时验证**，随 B-1/B-2 一并阻断。另需注意 `tests/conftest.py:19-22` 的宽泛 `except Exception` 会吞掉真实故障，建议收窄为 `except ImportError` 并区分「依赖缺失」与「代码缺陷」。