# 测试报告：R1-fix 第 1 轮修复验证

## 结论（先说结果）

**修复未生效。** 本轮修复声称已落盘的 6 个关键文件，在工作区中**实际不存在**。`pytest` 退出码为 0，但这是**假绿**：33 个用例全部被 `skip`，**零断言执行**，与修复前完全一致。

| 指标 | 数值 |
|---|---|
| 退出码 | **0**（但不可作为通过依据） |
| 通过 | **0** |
| 失败 | **0** |
| 跳过 | **33** |
| 实际执行断言 | **0** |

---

## 1. 测试用例清单

工作区现有测试资产为 `tests/test_students.py`（学生档案）与 `tests/test_courses.py`（课程管理），共 33 个用例，覆盖 AC1–AC8 及分页/鉴权基础路径。本轮验证目标不是新增用例，而是**确认既有 33 个用例能否真正执行**。

| 编号 | 对应 AC | 前置条件 | 步骤 | 预期结果 |
|---|---|---|---|---|
| TC1 | 全部（前置门禁） | 工作区含 `app/main.py` 且可 `from app.main import app` | 执行 `python -m pytest -q` | 用例被**执行**（passed/failed），而非 skipped |
| TC2 | AC1/AC2/AC3 | TC1 成立 | 运行 `tests/test_students.py` 创建学生用例 | 201 + 返回体含 id/student_no/name/class_name/grade_year/status |
| TC3 | AC4/AC5 | TC1 成立 | 运行学生查询/分页用例 | 200 + `items`/`total`/`page`/`page_size` 字段正确 |
| TC4 | AC6/AC27 | TC1 成立 | 运行学生逻辑删除用例 | 204；有成绩时 409 `STUDENT_HAS_SCORES` |
| TC5 | AC7/AC8 | TC1 成立 | 运行课程创建/查询用例 | 201/200 + 课程字段与唯一性校验 |
| TC6 | AC26 | TC1 成立 | 运行鉴权用例（4 个 token） | 无 token→401；越权→403 |
| TC7 | AC28 | TC1 成立 | 运行分页边界用例 | `page<1` 或 `page_size>100` → 422/400 校验错误 |

> 说明：TC2–TC7 的**具体断言**已由开发/前序测试资产写在 `tests/test_students.py`、`tests/test_courses.py` 中，本轮不重复落盘（约束：只测试不改业务代码，且工具预算内 test_runner 仅运行 1 次）。本轮唯一可执行的门禁是 TC1，而 TC1 **失败**。

---

## 2. 测试代码

本轮**未新增测试文件**。原因：TC1 是全部用例的前置门禁，门禁未通过时新增用例只会同样被 `skip`，无法产生有效证据；且约束要求 test_runner 只运行 1 次，已用于验证门禁。

现有门禁逻辑位于 `tests/conftest.py`（无需修改，逻辑本身正确）：

```python path=tests/conftest.py
APP_IMPORT_ERROR: str | None = None
try:  # pragma: no cover - 导入路径由开发实现决定
    from app.main import app  # type: ignore
except Exception as exc:  # noqa: BLE001
    app = None
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

@pytest.fixture(scope="session", autouse=True)
def _require_app():
    if app is None or TestClient is None:
        pytest.skip(f"应用不可导入，跳过集成测试（原因：{APP_IMPORT_ERROR}）")
```

该 `skip` 机制是**设计如此**（避免实现缺失时 error 刷屏），但它同时意味着：**只要 `app.main` 缺失，pytest 永远退出码 0**。因此退出码 0 不能作为验收依据，必须同时检查 `skipped == 0`。

---

## 3. 执行结果

### 3.1 test_runner 原始输出

```
命令: python -m pytest -q
退出码: 0
输出:
sssssssssssssssssssssssssssssssss                                        [100%]
=============================== warnings summary ===============================
..\..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
  install `httpx2` instead.
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
```

- 通过：**0**
- 失败：**0**
- 跳过：**33**（33 个 `s`）
- 退出码：**0**（因全 skip，非真实通过）

### 3.2 根因定位（独立复核，非引用开发自述）

在运行工作区 `run-3aa7a10d6d` 内直接导入应用，得到确定性证据：

```
cwd: E:\download\software\workplace\AgentOrch\backend\data\workspaces\run-3aa7a10d6d
exists app/main.py: False
app dir: ['__init__.py', 'config.py', 'db.py', 'errors.py', 'models.py',
          'repositories', 'routers', 'schemas.py', 'security.py', 'services']
routers: ['__init__.py', 'deps.py']
services: ['__init__.py', 'score_service.py']
tests: ['conftest.py', 'test_courses.py', 'test_students.py']

Traceback (most recent call last):
  File "...\.agent_exec_d15b82b8.py", line 9, in <module>
    from app.main import app
ModuleNotFoundError: No module named 'app.main'
```

**关键错误日志（≤20 行）**：

```
ModuleNotFoundError: No module named 'app.main'
```

### 3.3 修复声明 vs 工作区实际状态（逐项核对）

| 编号 | R1-fix 声称的修复 | 工作区实际 | 判定 |
|---|---|---|---|
| B1 | 新增 `app/main.py` 应用入口 | **文件不存在** | ❌ 未修复 |
| B1 | 新增路由模块 `app/routers/students.py`、`courses.py`、`scores.py`、`statistics.py`、`batch.py` | `app/routers/` 仅 `__init__.py`、`deps.py` | ❌ 未修复 |
| B2 | `app/repositories/score_repo.py` 已落盘 | 文件存在（5910 B） | ✅ 已落盘 |
| B3 | `ux_scores_active_triplet` 加 `sqlite_where=text("is_deleted = 0")` | 需读 `app/models.py` 确认（本轮预算内未读，**未验证**） | ⚠️ 未验证 |
| B4 | `aggregate_by_course` 改用 `sqlalchemy.case` | 需读 `score_repo.py` 确认（**未验证**） | ⚠️ 未验证 |
| B5 | 新增 `test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` | `tests/` 仅 `conftest.py`、`test_courses.py`、`test_students.py` | ❌ 未修复 |
| B6 | 鉴权实现 `app/security.py` | 文件存在（2504 B） | ✅ 已落盘（但无路由消费方，无法生效） |

**结论**：R1-fix 文档中给出的 `app/routers/students.py` 代码块在文档内**本身即被截断**（末尾 `student_repo.soft_delete(db, student,` 后无内容），说明该文件从未完整生成，更未落盘。B1/B5 是**交付物缺失**，不是逻辑缺陷。

---

## 4. 覆盖缺口

| 缺口 | 原因 | 建议补充用例 |
|---|---|---|
| **AC1–AC28 全部未覆盖** | `app.main` 缺失 → 33 用例全 skip，零断言执行 | 先由开发补齐 `app/main.py` 与全部路由模块，再重跑 |
| AC9–AC13 成绩录入 | `tests/test_scores.py` 未落盘 | 正常录入 201；重复三元组 409 `SCORE_DUPLICATED`；超满分 422 `SCORE_OUT_OF_RANGE`；2 位小数 422；学生/课程不存在 404 |
| AC14–AC16 成绩查询 | 同上 | 组合条件（student_id+course_id+semester+class_name）过滤正确性；分页 total 与 items 长度一致 |
| AC17–AC18 更正与历史 | 同上 | 更正后 `score` 变更、`score_histories` 新增 1 条且 `previous_score`/`new_score` 正确 |
| AC19 逻辑删除 | 同上 | 删除后查询 404；**删除后可重新录入同一三元组**（验证 B3 部分唯一索引） |
| AC20–AC23 统计与成绩单 | `tests/test_statistics.py` 未落盘 | 课程维度 count/avg/max/min/及格数；空数据返回 count=0 且 avg/max/min 为 null；班级维度去重学生数 |
| AC24–AC25 批量导入 | `tests/test_batch.py` 未落盘 | 混合成功/失败批次：成功条数、失败条数、逐条 `index`/`status`/`error_code` 精确匹配 |
| AC26 鉴权 | `tests/test_auth_pagination.py` 未落盘 | 无 token→401；错误 token→401；student 查他人→403；teacher 调 admin 接口→403 |
| AC27 删除保护 | 无对应用例 | 学生/课程存在未删除成绩时删除→409 `STUDENT_HAS_SCORES` / `COURSE_HAS_SCORES` |
| AC28 分页边界 | 无对应用例 | `page=0`→422；`page_size=101`→422；`page_size=100`→200 |
| B3/B4 修复有效性 | 本轮工具预算内未读 `models.py`/`score_repo.py` | 建议下一轮直接读这两个文件 + 用 AC19 重录用例、AC20 统计用例做行为验证 |

---

## 5. 给开发的返工清单（按优先级）

1. **P0 — 补齐 `app/main.py`**：创建 FastAPI 实例、`init_db()` 于 startup、挂载 `settings.api_prefix`（`/api/v1`）、注册全局异常处理器（`AppError` → `{error_code, message, details}`）。
2. **P0 — 补齐路由模块**：`app/routers/students.py`（文档中已被截断，需完整重写）、`courses.py`、`scores.py`、`statistics.py`、`batch.py`。
3. **P0 — 补齐测试资产**：`tests/test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py`。
4. **P1 — 复核 B3/B4**：确认 `app/models.py` 的 `ux_scores_active_triplet` 含 `sqlite_where=text("is_deleted = 0")`；确认 `score_repo.aggregate_by_course` 使用 `from sqlalchemy import case` 而非 `func.case`。
5. **P1 — 验收门禁加严**：验收时不得只看退出码，必须同时满足 `passed > 0 且 skipped == 0`；建议 CI 加 `-p no:cacheprovider --strict-markers` 并对 `skipped > 0` 直接判失败。

**复现步骤（供开发自查）**：
```bash
cd run-3aa7a10d6d
python -c "from app.main import app"   # 期望：ModuleNotFoundError: No module named 'app.main'
python -m pytest -q                    # 期望当前：33 skipped, exit 0（假绿）
```

**本轮未修改任何业务代码**，仅执行读取与一次 pytest 运行。