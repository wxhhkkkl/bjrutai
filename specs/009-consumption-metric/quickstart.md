# Quickstart: 业绩贡献口径统一为消费金额

开发与验证本功能的快速上手。功能已实现（未提交），以下为验证路径。

## 前置

- 后端依赖：`backend/requirements.txt`（FastAPI、SQLAlchemy 2.0 async、aiomysql、pydantic v2、pytest）
- 数据库：腾讯云 MySQL 8.0，连接串见 `backend/.env` 的 `DATABASE_URL`
- 管理端：`manageSystem/`（Vue 3 + Vite + Element Plus）
- 小程序：`miniProgram/`（微信开发者工具）

## ⚠️ 迁移（破坏性）

迁移 012 会**删除** `contribution_records` / `settlement_logs` / `contribution_coefficient` 三表，并把无账单的贡献记录合成为消费账单。**升级前必须备份数据库**：

```bash
cd backend
# 备份数据库（示例：mysqldump）
mysqldump -u <user> -p <dbname> > backup_before_012_$(date +%Y%m%d).sql

# 升级（包含 011 绩效结算 + 012 删贡献表）
alembic upgrade head

# 验证当前版本
alembic current   # 应为 012
```

迁移完成后检查：`contribution_records` / `settlement_logs` / `contribution_coefficient` 已删除；合成账单存在（`SELECT * FROM bills WHERE transaction_id LIKE 'legacy-contrib-%'`）。

> 注意：数据库当前可能在旧版本，需先 `alembic upgrade head` 才到 012。011（008 的绩效结算表）也一并应用。

## 运行测试

```bash
cd backend
pytest tests/            # 全部（unit / integration / contract），当前 353 passed
pytest tests/unit/test_consumption_service.py   # 新增口径单元测试
```

## 验证路径（对照 SC）

1. 打开管理后台「消费业绩」页 → 本月/累计消费金额（¥）、月度趋势、组织/个人排名、最新消费明细均为消费金额（SC-001/SC-005）。
2. 工作台首页 → 「本月消费（¥）」替代「本月业绩（分）」（SC-005）。
3. 客户详情 → 本月/累计消费金额与「消费记录」账单列表（SC-001）。
4. 小程序贡献明细页 → 「本月消费 ¥…」，明细状态「已支付/待支付」；首页「我的消费」（SC-005）。
5. 小程序组织绩效页 → 成员/下级组织「本月消费 / 累计消费」（¥）（SC-001）。
6. 抽查任一分销员的消费金额，与 `consumption_by_distributor` 手算结果核对（排除退款/取消，部分退款全额计入）（SC-002）。
7. 迁移前若有「测试分销 150」等贡献记录 → 迁移后以 ¥1.50 消费账单形式可见（SC-003）。
8. 全量测试通过、代码无 `ContributionRecord`/`ContributionCoefficient`/`batch_settle` 残留（SC-004）。

## 相关文件

- 口径实现：`backend/src/services/consumption_service.py`
- 迁移：`backend/migrations/versions/012_drop_contribution_records.py`
- 单元测试：`backend/tests/unit/test_consumption_service.py`
- 管理端页面：`manageSystem/src/pages/contributions/index.vue`、`dashboard/index.vue`、`customers/detail.vue`
- 小程序：`miniProgram/pages/contribution/index.*`、`contribution-detail/index.*`、`home/index.wxml`、`org-performance/index.wxml`
