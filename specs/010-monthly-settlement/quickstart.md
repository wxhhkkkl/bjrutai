# Quickstart: 绩效计算模块月度核算（未核算月份选择 + 数据报表展示 + 审核冻结/打回）

开发与测试本功能的快速上手。

## 前置

- 后端依赖：`backend/requirements.txt`（FastAPI、SQLAlchemy 2.0 async、aiomysql、pydantic v2、pytest、APScheduler、openpyxl）
- 数据库：腾讯云 MySQL 8.0，连接串见 `backend/.env` 的 `DATABASE_URL`
- 管理端：`manageSystem/`（Vue 3 + Vite + Element Plus）

## 运行后端

```bash
cd backend
python -m pip install -r requirements.txt

# 迁移（013：reports 加 source/period/status 列）
alembic upgrade head

# 启动（开发）
python -m uvicorn src.main:app --reload --port 8000
```

启动时自动创建缺失表、seed 系统管理员与权限（复用既有 `sharing_rules.read` / `performance.settle`）。

## 运行测试

```bash
cd backend
pytest tests/            # 全部（unit / integration / contract）
pytest tests/contract/   # 仅契约测试
pytest tests/unit/test_settlement_service.py tests/contract/test_admin_performance.py  # 本功能核心
```

## 验证路径（对照 SC）

1. 配置某组织绩效规则（`sharing_rules.write`）→ 产生某月消费数据（账单）。
2. `GET /admin/performance/settleable-periods` → 列出该月（SC-001：已冻结/待审核月份不可选）。
3. `POST /admin/performance/settlements/{period}/settle` → 核算成功，该月进入 `pending`（SC-002 数值与规则一致）。
4. `GET /reports` → 看到该月核算报表记录，`status=pending`（SC-003/SC-007 2 秒内可见）。
5. 数据报表查看详情 → 汇总+明细与核算结果一致（SC-006）。
6. `review` → 状态 `reviewed`（冻结）；再次 `settle` 被拒绝、数值不变（SC-004）。
7. 对另一月 `reject`（填原因）→ `rejected` → 可重新核算 → 回到 `pending`（SC-005）。
8. 报表记录导出 Excel → 含「绩效核算」sheet，与页面一致（SC-007）。
9. 无 `sharing_rules.read` 的调用者 → 数据报表列表不见核算记录、详情/导出 403（SC-008/FR-011）。

## 管理端页面

- `manageSystem/src/pages/performance/settlement.vue`：月份选择器仅列可核算月份；选中后展示估算 +「发起核算」；核算成功后展示审核状态与「确认/打回/重算/导出」。
- `manageSystem/src/pages/reports/index.vue`：历史报表列表展示核算来源记录及状态标记（待审核/已确认/已打回），可查看明细与下载 Excel。

## 权限

| 权限点 | 作用 |
|--------|------|
| `sharing_rules.read` | 查看估算、查询可核算月份、查看/导出核算报表记录 |
| `performance.settle` | 发起核算、审核确认、打回、重算 |
