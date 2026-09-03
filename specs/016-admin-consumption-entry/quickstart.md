# Quickstart: 后台消费录入验证

本文件用于实现后的本地验证；`speckit.plan` 阶段不执行迁移或修改业务代码。

## Implementation baseline (2026-09-03)

- Backend contribution baseline: `12 passed` for the existing dashboard, consumption aggregation, and dashboard service suites.
- Admin test baseline: Vitest exits with code 1 because the project initially contains no test files; this feature will add the first component/page tests.
- Admin production build baseline: passed. Existing Rollup warnings concern the pre-existing large bundle and mixed static/dynamic import of `src/api/http.js`.
- US1 automated verification: `9 passed` for manual-consumption backend unit/contract tests and `3 passed` for the new admin dialog component tests.
- US2 automated verification: `12 passed` for consumption aggregation, end-to-end manual flow, and dashboard contracts; `2 passed` for source/customer display and write-permission visibility on the admin page.
- US3 automated verification: `10 passed` for write permission, system-admin seed, persistent idempotency, audit minimization, and rollback behavior; `2 passed` for admin-page permission visibility.

## Final verification (2026-09-03)

- Feature backend regression set: `22 passed` (manual service/API, end-to-end statistics, snapshot attribution and dashboard contract).
- Full backend suite: `415 passed, 6 failed`. The six failures are pre-existing and outside this feature: three bootstrap tests use a stale mocked session response, two WeChat login-flow tests exhaust their mocked DB result queue, and one contribution trend test hard-codes March 2026 as part of the last six months even though the current month is September 2026. No manual-consumption test or affected aggregation test failed.
- New backend code coverage: `80.42%` across the manual service, schema and admin API (`--cov-fail-under=80` passed).
- Migration verification: isolated 015-shaped SQLite database with a legacy paid bill completed `016 upgrade -> downgrade -> upgrade`; amount, transaction number and status remained unchanged, `source` was backfilled to `rutai_sync`, and the admin/idempotency unique constraint was present. Migration consistency suite: `5 passed`.
- Privacy review: no raw phone, ID card, medical account or note text is returned by the create response, written to the audit detail, rendered in the dashboard, or logged. Customer search returns masked values; short malformed identifiers are fully masked.
- Admin verification: Vitest `5 passed`; ESLint `0 errors` (104 pre-existing style warnings); Vite production build passed with the pre-existing bundle-size and mixed-import warnings.
- Local browser smoke: the project was started at `http://127.0.0.1:5175/admin/` and the login page rendered normally. Authenticated click-through and creation were not performed because that would require entering administrator credentials and mutating a connected database; the equivalent form/permission/submission paths are covered by automated tests.

## 1. Prepare environment

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

确认测试或本地数据库不是生产数据库后再执行迁移。系统管理员启动 seed 后应包含 `contributions.read` 和 `contributions.write`。

## 2. Run backend TDD suites

```bash
cd backend
pytest tests/unit/test_manual_consumption_service.py -q
pytest tests/contract/test_admin_manual_consumption.py -q
pytest tests/integration/test_admin_manual_consumption_flow.py -q
pytest -q
```

Expected:

- 有写权限可搜索绑定客户并创建人工消费。
- 只读账号被拒绝。
- 非法金额、未来时间、客户版本冲突、解绑/停用客户返回中文错误。
- 相同幂等键与相同内容只创建一条账单；不同内容返回冲突。
- 新记录进入总额、趋势、个人排行、组织排行和最新明细。
- 客户转移后，历史人工消费仍保留录入时归属。

## 3. Run admin tests and build

```bash
cd manageSystem
npm test -- --run
npm run lint
npm run build
```

Expected:

- `contributions.write` 控制录入按钮。
- 客户归属只读，金额正确转换为整数分。
- 二次确认和提交锁防止重复操作。
- 失败时保留表单，成功时刷新看板。

## 4. Manual local smoke test

Start backend and admin using the project's normal local commands, then open:

```text
http://<local-host>:<admin-port>/admin/contributions
```

Checklist:

1. 使用系统管理员登录，确认显示“录入消费”。
2. 用姓名、完整手机号或身份证号搜索一个已绑定客户。
3. 确认页面只显示脱敏信息，人员和组织不能修改。
4. 输入 `128.80` 元、当前时间和备注，检查确认摘要。
5. 连续点击最终确认，确认只生成一条记录。
6. 检查最新明细出现“人工录入”，金额为 `¥128.80`。
7. 检查当月总额、趋势、人员和组织排行按 `12880` 分更新。
8. 使用只有 `contributions.read` 的账号登录，确认无录入入口，直接调用创建接口返回 403。

## 5. Migration safety

```bash
cd backend
alembic current
alembic upgrade head
alembic downgrade 015
alembic upgrade head
```

在临时数据库验证：既有账单被标记为 `rutai_sync`，金额和状态不变；升级、降级、再次升级均无结构错误。生产部署前备份数据库，只执行一次正式升级。
