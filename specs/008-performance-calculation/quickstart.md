# Quickstart: 绩效计算模块

开发与测试本功能的快速上手。

## 前置

- 后端依赖：`backend/requirements.txt`（FastAPI、SQLAlchemy 2.0 async、aiomysql、pydantic v2、pytest、APScheduler）
- 数据库：腾讯云 MySQL 8.0，连接串见 `backend/.env` 的 `DATABASE_URL`
- 管理端：`manageSystem/`（Vue 3 + Vite + Element Plus）
- 小程序：`miniProgram/`（微信开发者工具）

## 运行后端

```bash
cd backend
# 首次：安装依赖
python -m pip install -r requirements.txt

# 迁移（新增 performance_settlements 表 + commission_results.rule_snapshot）
alembic upgrade head

# 启动（开发）
python -m uvicorn src.main:app --reload --port 8000
```

启动时自动创建缺失表、seed 系统管理员与权限（含新的 `performance.settle`）。

## 运行测试

```bash
cd backend
pytest tests/            # 全部（unit / integration / contract）
pytest tests/contract/   # 仅契约测试
```

## 验证路径（对照 SC）

1. 配置某组织绩效规则（`sharing_rules.write`）→ 产生消费数据。
2. 触发某月核算（自动结算或 `recompute` 接口）→ 结算批次 `pending`。
3. 小程序查询 → 当月为 `estimate`，该月不在 `confirmed`（SC-003）。
4. 管理端 `review` → 批次 `reviewed`（SC-006）。
5. 小程序查询 → 该月出现在 `confirmed` 且数值冻结（SC-004）。
6. 修改规则后 `recompute` → `reviewed` 月份结果不变（SC-005，快照生效）。
7. `export` → CSV 与页面/接口数据一致（SC-007）。
8. 管理端估算 = 小程序当月预估（SC-008）。

## 管理端页面

`manageSystem/src/pages/performance/settlement.vue`：左侧组织树 + 右侧人员估算、结算状态与审核操作（确认/打回/重算/导出）。菜单「绩效计算」，权限 `sharing_rules.read`（查看）/ `performance.settle`（审核/导出）。

## 小程序页面

`miniProgram/pages/performance/`（推广员本人）+ `miniProgram/pages/org-performance/`（组织维度，增加提成区块）。
