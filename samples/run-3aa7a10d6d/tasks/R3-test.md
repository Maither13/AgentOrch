# 第 3 轮修复验证报告（R3-fix）

## 结论：**未通过（不可验收）**。修复未生效，且测试门禁仍为“假绿”（全 skip 却退出码 0）

---

## 1. 测试用例清单

本轮为“回归验证”性质，用例清单沿用既有测试资产（`tests/test_courses.py`、`tests/test_students.py`），并列出 R3-fix 声称应落盘但实际缺失的用例组。

| 编号 | 对应 AC | 前置条件 | 步骤 | 预期结果 |
|---|---|---|---|---|
| TC1 | AC1–AC8（学生/课程 CRUD） | 应用可导入、内存 SQLite 建表 | 运行 `tests/test_students.py` 全部用例 | 全部 passed，校验 201/200 与响应体关键字段（student_no、name、class_name、grade_year、status） |
| TC2 | AC1–AC8（课程 CRUD） | 同上 | 运行 `tests/test_courses.py` 全部用例 | 全部 passed，校验 course_code、credit、full_score 及唯一键冲突 409 |
| TC3 | AC9–AC19（成绩录入/校验/两位小数） | 同上 | 运行 `tests/test_scores.py` | 文件存在且全部 passed；含 `test_ac11_score_two_decimals_rejected` 边界用例 |
| TC4 | AC20–AC23（统计） | 同上 | 运行 `tests/test_statistics.py` | 文件存在且全部 passed，校验平均分/最高分/及格率数值 |
| TC5 | AC24–AC25（批量导入） | 同上 | 运行 `tests/test_batch.py` | 文件存在且全部 passed，校验部分成功明细 |
| TC6 | AC26、AC28（鉴权与分页） | 同上 | 运行 `tests/test_auth_pagination.py` | 文件存在且全部 passed；无 token → 401，越权 → 403，分页 total/page/page_size 正确 |
| TC7 | 门禁（B-2/B-7） | 依赖缺失场景 | 在缺 `sqlalchemy` 时运行 `pytest -q` | 退出码非 0（`pytest.exit(returncode=1)`），不得以 skip 冒充通过 |

---

## 2. 测试代码

**本轮未新增或修改任何测试文件**（约束：只测试、不修改业务代码；且 R3-fix 声称的 4 个测试文件与 conftest 门禁修改均未落盘，我无法对不存在的文件编写“验证其存在”的 pytest 用例并伪造结果）。

现有测试资产（工作区实际内容，未改动）：

```python path=tests/conftest.py
# 关键片段（实际文件 5017 B，此处仅摘录与门禁相关的部分）
APP_IMPORT_ERROR: str | None = None
try:
    from app.main import app
except Exception as exc:  # noqa: BLE001
    app = None
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

@pytest.fixture(scope="session", autouse=True)
def _require_app():
    if app is None or TestClient is None:
        pytest.skip(f"应用不可导入，跳过集成测试（原因：{APP_IMPORT_ERROR}）")
```

> 注：`_require_app` 仍为 `pytest.skip`，R3-fix 声称的“改为 `pytest.exit(returncode=1)`”**未落盘**。

---

## 3. 执行结果

### 3.1 环境探测（python_exec）

```
fastapi 0.162.0
sqlalchemy MISSING ModuleNotFoundError No module named 'sqlalchemy'
pydantic 2.14.2
httpx 0.28.1
pytest 9.2.0
3.14.4 (tags/v3.14.4:23116f4, Dec 17 2025, 14:10:54) [MSC v.1944 64 bit (AMD64)]
app import FAIL ModuleNotFoundError No module named 'sqlalchemy'
```

### 3.2 pytest 实跑（test_runner，命令 `python -m pytest -q`）

- **退出码：0**
- **通过：0 / 失败：0 / 跳过：29**
- 原始输出：

```
sssssssssssssssssssssssssssssssss                                        [100%]
=============================== warnings summary ===============================
..\..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
```

### 3.3 判定

| 项 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 退出码 | 非 0（依赖缺失应硬失败） | **0** | ❌ 假绿门禁未修复 |
| passed | > 0 | **0** | ❌ 无任何运行时证据 |
| skipped | 0 | **29** | ❌ 全量跳过 |
| `tests/test_scores.py` | 存在 | **不存在** | ❌ 未落盘 |
| `tests/test_statistics.py` | 存在 | **不存在** | ❌ 未落盘 |
| `tests/test_batch.py` | 存在 | **不存在** | ❌ 未落盘 |
| `tests/test_auth_pagination.py` | 存在 | **不存在** | ❌ 未落盘 |
| `conftest.py` 门禁加严 | `pytest.exit(1)` | 仍为 `pytest.skip` | ❌ 未落盘 |

**根因（与 R3-fix 自述一致，已由我独立复现）**：`sqlalchemy` 未安装 → `app/main.py` 导入链失败 → `conftest.py` 捕获后 `app=None` → `_require_app` 全量 skip → pytest 以退出码 0 结束。**这是 CI 层面的假绿，必须视为失败。**

R3-fix 文档中“本轮实际改动”一节声称修改了 conftest 门禁，但工作区文件内容与修改前一致，**该声明与事实不符**（文档自身末尾也承认“未落盘”，前后矛盾）。

---

## 4. 覆盖缺口

| 未覆盖 AC | 原因 | 建议补充用例 |
|---|---|---|
| AC1–AC8 | 用例文件存在，但因缺 `sqlalchemy` 全部 skip，零运行时证据 | 环境预装依赖后重跑 `test_students.py` / `test_courses.py` |
| AC9–AC19 | `tests/test_scores.py` 不存在 | 落盘该文件，必须含 `test_ac11_score_two_decimals_rejected`（两位小数拒绝）与 0/满分边界 |
| AC20–AC23 | `tests/test_statistics.py` 不存在 | 落盘并断言具体数值（平均分、最高分、及格率），禁止只断言 200 |
| AC24–AC25 | `tests/test_batch.py` 不存在 | 落盘并断言部分成功明细（成功条数、失败条数、失败原因） |
| AC26、AC28 | `tests/test_auth_pagination.py` 不存在 | 落盘：无 token→401、越权→403、分页 total/page/page_size 精确值 |
| 门禁 B-2/B-7 | conftest 仍 `pytest.skip` | 改为 `pytest.exit(returncode=1)`，并收窄 `except Exception` 为 `except ImportError` |

---

## 5. 交给开发的修复清单（按优先级）

1. **P0 环境**：执行环境侧预装依赖 `pip install -r requirements.txt`（当前缺 `sqlalchemy>=2.0,<2.1`）。这是所有 AC 的前置阻断项，测试侧无法绕过。
2. **P0 门禁**：`tests/conftest.py` 的 `_require_app` 改为 `pytest.exit(returncode=1)`，使“全 skip”不再被 CI 判为通过。
3. **P0 测试资产**：`file_write` 落盘 `test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py`（R2/R3 两轮均只在文档中给出代码，未落盘）。
4. **流程**：修复文档中的“已改动”声明必须与工作区实际文件一致，禁止把未落盘内容写成已交付。

**复现命令**：
```
python -c "import sqlalchemy"          # 当前 ModuleNotFoundError
python -c "from app.main import app"   # 当前 ModuleNotFoundError
python -m pytest -q                    # 当前 29 skipped, exit 0（假绿）
```

**本轮判定：未完成，不可验收。** 依赖装好并落盘上述 4 个测试文件与门禁修改后，请再给我一轮预算做完整回归。