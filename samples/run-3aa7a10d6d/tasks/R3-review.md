# 第 3 轮修复后重新验收报告（Reviewer）

## 1. 验收记录

| 标准编号 | 结论 | 证据 | 问题与修复建议 | 严重级别 |
|---|---|---|---|---|
| AC1 | failed | `tests/test_students.py:10-40` 有用例；`python -m pytest -q` 实跑输出 `ssss...`（29 skipped，exit 0），无任何 passed | 环境缺 `sqlalchemy` 导致 `app.main` 导入失败（`app/main.py:15` `from app.db import init_db`），全部用例 skip，零运行时证据。需环境侧 `pip install -r requirements.txt` 后重跑 | P0 |
| AC2 | failed | `tests/test_students.py:43-56`；同上全 skip | 同上 | P0 |
| AC3 | failed | `tests/test_students.py:59-92`；同上全 skip | 同上 | P0 |
| AC4 | failed | `tests/test_students.py:95-113`；同上全 skip | 同上 | P0 |
| AC5 | failed | `tests/test_students.py:116-152`；同上全 skip | 同上 | P0 |
| AC6 | failed | `tests/test_students.py:155-170`；同上全 skip | 同上 | P0 |
| AC7 | failed | `tests/test_courses.py:10-33`；同上全 skip | 同上 | P0 |
| AC8 | failed | `tests/test_courses.py:36-79`；同上全 skip | 同上 | P0 |
| AC9 | failed | `tests/test_scores.py` **不存在**（`file_list` 已核，`tests/` 仅 conftest.py、test_courses.py、test_students.py） | R3-fix 自述“未落盘”。必须 `file_write` 落盘成绩录入用例 | P0 |
| AC10 | failed | 同上，文件不存在 | 同上 | P0 |
| AC11 | failed | 同上；`test_ac11_score_two_decimals_rejected` 缺失 | 需覆盖超满分、负分、两位小数三类边界 | P0 |
| AC12 | failed | 同上，文件不存在 | 同上 | P0 |
| AC13 | failed | 同上，文件不存在 | 需覆盖 `2024-3`、`2024/1` | P0 |
| AC14 | failed | 同上，文件不存在 | 同上 | P0 |
| AC15 | failed | 同上，文件不存在 | 同上 | P0 |
| AC16 | failed | 同上，文件不存在 | 同上 | P0 |
| AC17 | failed | 同上，文件不存在 | 同上 | P0 |
| AC18 | failed | 同上，文件不存在 | 需断言 histories 条数与最新一条字段 | P0 |
| AC19 | failed | 同上，文件不存在 | 同上 | P0 |
| AC20 | failed | `tests/test_statistics.py` **不存在** | 需断言 count=3、average=60.00、max=90、min=30、pass_rate=0.6667 具体数值 | P0 |
| AC21 | failed | 同上，文件不存在 | 需断言空集时四项为 null 且 HTTP 200 | P0 |
| AC22 | failed | 同上，文件不存在 | 需覆盖缺 semester → 400 | P0 |
| AC23 | failed | 同上，文件不存在 | 需断言 items 条数与 average 数值 | P0 |
| AC24 | failed | `tests/test_batch.py` **不存在** | 需断言 succeeded=2/failed=1/results 长度 3 及失败项 error_code | P0 |
| AC25 | failed | 同上，文件不存在 | 需覆盖空数组与 >200 条 | P0 |
| AC26 | failed | `tests/test_auth_pagination.py` **不存在** | 需覆盖无 token→401、学生越权→403 | P0 |
| AC27 | failed | `tests/test_students.py:173-196`、`tests/test_courses.py:118-135` 有用例；实跑全 skip | 同 AC1 环境阻断 | P0 |
| AC28 | failed | `tests/test_auth_pagination.py` **不存在** | 需覆盖 page_size=0/101 → 400 | P0 |
| 门禁（B-2/B-7） | failed | `tests/conftest.py:52-55` 仍为 `pytest.skip(...)`；`tests/conftest.py:19-22` 仍为 `except Exception`；实跑 exit 0 + 29 skipped | R3-fix 文档称“已改为 `pytest.exit(returncode=1)`”，但工作区文件未变，声明与事实不符。必须落盘门禁修改并收窄异常类型 | P0 |

## 2. 总体结论

**驳回（不可验收）。**

理由：
1. **零运行时证据**：本轮 `test_runner` 实跑 `python -m pytest -q`，退出码 **0**，输出为 29 个 `s`（skipped），**passed = 0**。按判定规则“证据不足视为 failed”，AC1–AC28 全部 failed。
2. **假绿门禁未修复**：`tests/conftest.py:52-55` 仍用 `pytest.skip` 吞掉导入失败，CI 会把“全 skip”判为通过。这是最危险的缺陷——它让所有后续轮次的“绿”都不可信。
3. **测试资产仍缺失**：`tests/test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` 四个文件在工作区中不存在（`file_list` 已核）。R2、R3 两轮均只在文档中给出代码而未 `file_write` 落盘。
4. **修复文档与事实不符**：`tasks/R3-fix.md` 的“本轮实际改动”一节声称修改了 conftest 门禁，但 `tests/conftest.py` 内容与修改前一致；该文档末尾又自认“未落盘”，前后矛盾。文档自述“本轮未产生任何可核查的运行时证据”，与我的独立复现一致。

值得肯定的是：R3-fix 与 R3-test 都如实承认了未完成，没有伪造通过结论，这一点符合流程诚信要求。但**如实承认失败不等于验收通过**。

## 3. 阻断项清单（P0）

**B-1 环境缺依赖，应用不可导入**
- 复现：`python -c "import sqlalchemy"` → `ModuleNotFoundError: No module named 'sqlalchemy'`
- 复现：`python -c "from app.main import app"` → 同上（`app/main.py:15` 导入链失败）
- 修复：执行环境侧 `pip install -r requirements.txt`（需 `sqlalchemy>=2.0,<2.1`）。此项测试侧与开发侧均无法绕过，必须由环境侧解决。

**B-2 假绿门禁：全 skip 却退出码 0**
- 复现：`python -m pytest -q` → 输出 `sssssssssssssssssssssssssssssssss [100%]`，退出码 **0**
- 位置：`tests/conftest.py:52-55` `_require_app` 使用 `pytest.skip`
- 修复：改为 `pytest.exit(returncode=1)`（或 `pytest.fail`），使依赖缺失时硬失败。

**B-3 宽泛异常捕获掩盖真实缺陷**
- 位置：`tests/conftest.py:19-22` `except Exception as exc`
- 修复：收窄为 `except ImportError`，区分“依赖缺失”与“代码缺陷”；后者应直接 error 而非 skip。

**B-4 四个测试文件未落盘**
- 复现：`file_list` 显示 `tests/` 下仅 `conftest.py`、`test_courses.py`、`test_students.py`
- 缺失：`tests/test_scores.py`（AC9–AC19）、`tests/test_statistics.py`（AC20–AC23）、`tests/test_batch.py`（AC24–AC25）、`tests/test_auth_pagination.py`（AC26、AC28）
- 修复：用 `file_write` 真正落盘，不得只写在任务文档里。

**B-5 修复文档声明与工作区不一致**
- 复现：对比 `tasks/R3-fix.md`“本轮实际改动”与 `tests/conftest.py:52-55` 实际内容
- 修复：文档中的“已改动”必须与工作区文件逐字一致；未落盘内容不得写入“已交付”章节。

**建议的下一轮顺序**：先由环境侧完成 B-1 → 开发落盘 B-2/B-3 门禁修改 → 落盘 B-4 四个测试文件 → 测试 Agent 实跑并附退出码与 `passed/skipped` 计数。门禁修好之前，任何“测试通过”的结论都不具备验收效力。

## 4. 安全检查

| 检查项 | 结论 | 说明 |
|---|---|---|
| 注入风险 | 无法验证（failed） | 代码层面 `app/repositories/*` 使用 SQLAlchemy ORM 参数化查询，未见字符串拼接 SQL 的迹象；但因应用不可导入，无法通过运行时用例验证。需在 B-1 解除后补测。 |
| 越权访问 | 未覆盖（failed） | AC26 对应的 `tests/test_auth_pagination.py` 不存在，学生越权查他人成绩（应 403）与无凭证（应 401）均无任何运行时证据。`tests/conftest.py:36-39` 已备好四类 token 夹具，但无用例消费。 |
| 敏感信息泄露 | 部分通过（passed，静态） | `app/main.py:88-96` 的 `IntegrityError` 处理器对外返回通用文案，未回显 SQL 细节；`app/main.py:99-107` 的 `SQLAlchemyError` 处理器记录堆栈但对外仅返回 `INTERNAL_ERROR`。静态看符合要求，但无运行时验证。 |
| 异常处理缺失 | failed | ① `tests/conftest.py:19-22` 宽泛 `except Exception` 会掩盖真实代码缺陷，属测试侧异常处理缺陷；② 应用侧异常处理器因导入失败无法验证是否真正生效；③ 门禁以 skip 冒充通过，属流程级异常处理缺失。 |

**安全结论**：本轮不具备安全验收条件。越权访问（AC26）是 P1 需求 F12 的核心安全控制点，当前零覆盖，必须在下一轮补齐并通过后才能放行。