# 验收记录（R1-fix 第 1 轮重测 · 复审）

## 1. 验收记录

| 标准编号 | 结论 | 证据 | 问题与修复建议 | 严重级别 |
|---|---|---|---|---|
| AC1 | failed | `test_runner` 输出 `sssssssssssssssssssssssssssssssss [100%]`，33 skipped / 0 passed；`tests/conftest.py:19-22` 因 `from app.main import app` 失败而 `app=None`，`_require_app` 全量 skip | 缺 `app/main.py` 与 `app/routers/students.py`，用例零断言执行 | P0 |
| AC2 | failed | 同上，`tests/test_students.py:test_ac2_duplicated_student_no` 未执行 | 同上 | P0 |
| AC3 | failed | 同上，`test_ac3_*` 4 个用例未执行 | 同上 | P0 |
| AC4 | failed | 同上，`test_ac4_*` 未执行 | 同上 | P0 |
| AC5 | failed | 同上，`test_ac5_*` 未执行 | 同上 | P0 |
| AC6 | failed | 同上，`test_ac6_*` 未执行 | 同上 | P0 |
| AC7 | failed | `tests/test_courses.py` 全部 skip，无执行证据 | 缺 `app/routers/courses.py` | P0 |
| AC8 | failed | 同上 | 同上 | P0 |
| AC9 | failed | `tests/test_scores.py` **文件不存在**（`file_list` 无此项）；`app/routers/scores.py` 不存在 | 缺路由与测试资产 | P0 |
| AC10 | failed | 同上；`app/models.py:96-103` 部分唯一索引已正确实现（`sqlite_where=text("is_deleted = 0")`），但无路由消费、无测试验证 | 补路由 + 补 `test_scores.py` | P0 |
| AC11 | failed | `app/services/score_service.py:31-45` `validate_score_value` 逻辑存在，但无 HTTP 层暴露、无测试执行 | 同上 | P0 |
| AC12 | failed | `score_service.py:48-60` `resolve_student/resolve_course` 存在，无路由、无测试 | 同上 | P0 |
| AC13 | failed | 无 `semester` 格式校验的 HTTP 层证据，无测试 | 同上 | P0 |
| AC14 | failed | `app/repositories/score_repo.py:60-107` `list_scores` 已实现组合过滤，但无路由、无测试执行 | 同上 | P0 |
| AC15 | failed | 同上（`class_name` 过滤在 `score_repo.py:76-77`） | 同上 | P0 |
| AC16 | failed | `score_repo.py:66` 已含 `Score.is_deleted == 0`，无路由、无测试 | 同上 | P0 |
| AC17 | failed | `score_service.py:96-127` `update_score` 返回 `(record, previous)`，无路由、无测试 | 同上 | P0 |
| AC18 | failed | `score_repo.py:47-55` `list_histories` 存在，无 `/histories` 路由、无测试 | 同上 | P0 |
| AC19 | failed | `score_service.py:130-135` `delete_score` 存在，无路由、无测试 | 同上 | P0 |
| AC20 | failed | `score_repo.py:110-141` `aggregate_by_course` 已改用 `sqlalchemy.case`（`score_repo.py:9` `from sqlalchemy import case`），但无 `statistics` 路由、无测试 | 补 `app/routers/statistics.py` + `test_statistics.py` | P0 |
| AC21 | failed | `score_repo.py:135-136` count=0 返回 None 分支存在，无路由、无测试 | 同上 | P0 |
| AC22 | failed | `score_repo.py:144-176` `aggregate_by_class` 用 `func.count(func.distinct(...))`，无路由、无测试 | 同上 | P0 |
| AC23 | failed | `score_repo.py:179-196` `list_transcript` 存在，无 `/transcript` 路由、无测试 | 同上 | P0 |
| AC24 | failed | `score_service.py:138-197` `batch_create` 存在，无 `batch` 路由、无 `test_batch.py` | 补 `app/routers/batch.py` + 测试 | P0 |
| AC25 | failed | 同上，records 1–200 校验无 HTTP 层证据 | 同上 | P0 |
| AC26 | failed | `app/security.py:29-72` 鉴权与 `ensure_student_self` 已实现，但无任何路由 `Depends` 消费方，无 `test_auth_pagination.py` | 路由挂载 `require_roles`/`ensure_student_self` + 补测试 | P0 |
| AC27 | failed | `tests/test_students.py:test_ac27_*` 未执行；`app/routers/students.py` 不存在 | 同上 | P0 |
| AC28 | failed | 无分页边界测试资产，无执行证据 | 补 `test_auth_pagination.py` | P0 |

> 说明：本轮 `test_runner` 退出码 0，但 `passed=0`、`skipped=33`，按判定规则「证据不足视为 failed」，且「测试未覆盖的 P0 验收标准视为 failed」，故 AC1–AC28 全部 failed。

## 2. 总体结论

**驳回。**

理由：
1. **交付物缺失（P0）**：`app/main.py` 与 `app/routers/{students,courses,scores,statistics,batch}.py` 在工作区中**均不存在**（`file_list` 29 个文件清单可核）。`app/routers/` 仅有 `__init__.py`、`deps.py`。
2. **假绿（P0）**：`python -m pytest -q` 退出码 0，但输出为 33 个 `s`，`passed=0`、`skipped=33`，**零断言执行**。退出码 0 不可作为通过依据。
3. **测试资产缺失（P0）**：`tests/test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` 均未落盘，AC9–AC26、AC28 无任何用例。
4. **修复部分有效但不可验收**：`app/models.py:96-103` 的 `ux_scores_active_triplet` 已含 `sqlite_where=text("is_deleted = 0")`（B3 已修复）；`app/repositories/score_repo.py:9,124` 已使用 `sqlalchemy.case`（B4 已修复）；`app/security.py`、`app/services/score_service.py`、`app/repositories/score_repo.py` 逻辑完整。但这些代码**无 HTTP 入口、无测试执行**，无法产生可核查的验收证据。
5. 与首轮结论一致：R1-fix 声称的 B1/B5 修复**未生效**，属交付物缺失而非逻辑缺陷。

## 3. 阻断项清单（P0）

| 编号 | 阻断项 | 复现方式 |
|---|---|---|
| B-1 | `app/main.py` 缺失，应用不可导入 | `cd run-3aa7a10d6d && python -c "from app.main import app"` → `ModuleNotFoundError: No module named 'app.main'` |
| B-2 | 路由模块缺失（students/courses/scores/statistics/batch） | `file_list` 中 `app/routers/` 仅 `__init__.py`、`deps.py`；`ls app/routers` 无上述文件 |
| B-3 | 测试全量 skip，零断言执行 | `python -m pytest -q` → 输出 33 个 `s`，`passed=0`、`skipped=33`、退出码 0 |
| B-4 | 测试资产缺失 | `tests/` 仅 `conftest.py`、`test_courses.py`、`test_students.py`；无 `test_scores.py`/`test_statistics.py`/`test_batch.py`/`test_auth_pagination.py` |
| B-5 | 鉴权无消费方，AC26 不可验证 | `app/security.py` 定义了 `require_roles`/`ensure_student_self`，但 `app/routers/` 无任何路由引用（无 `Depends` 挂载点） |

**修复建议（交开发 Agent）**：
1. 新建 `app/main.py`：FastAPI 实例、`init_db()` startup、挂载 `settings.api_prefix`（`/api/v1`）、注册 `AppError` → `{error_code, message, details}` 全局异常处理器。
2. 新建 5 个路由模块，复用已就绪的 `score_service`/`score_repo`/`security`；`students.py` 需完整重写（R1-fix 文档中该代码块被截断）。
3. 补齐 4 个测试文件，覆盖 AC9–AC26、AC28。
4. 验收门禁加严：必须同时满足 `passed > 0 且 skipped == 0`，`skipped > 0` 直接判失败。

## 4. 安全检查

| 检查项 | 结论 | 依据 |
|---|---|---|
| 注入风险 | 通过（静态审查） | `score_repo.py` 全部使用 SQLAlchemy 表达式/参数绑定，无字符串拼接 SQL；`list_scores` 条件为 ORM 表达式 |
| 越权访问 | 部分通过（不可验证） | `app/security.py:60-72` `ensure_student_self` 逻辑正确（学生仅可访问本人 `student_id`），`require_roles` 白名单正确；但**无路由消费方**，AC26 无法端到端验证 → 视为未验证 |
| 敏感信息泄露 | 通过（静态审查） | `security.py:47` 未知 token 仅 `logger.warning` 记录事件，不打印 token 值；`score_service.py` 日志仅记录 `error_code` 与索引，未输出成绩明细或凭证 |
| 异常处理缺失 | 部分通过 | `score_service.py:88-95`、`batch_create` 已捕获 `IntegrityError` 并 `rollback`；`AppError` 统一错误码体系完整。但 `app/main.py` 缺失导致**全局异常处理器未注册**，`AppError` 无法转为 `{error_code, message, details}` 响应 → 异常处理链路未闭环 |

**安全结论**：静态代码层面无高危缺陷，但因应用入口与路由缺失，越权与异常处理两项**无法通过运行时验证**，随 B-1/B-2 一并阻断。