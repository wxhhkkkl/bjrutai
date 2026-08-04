# Quickstart: 业绩贡献页面增强

**Branch**: `007-contribution-dashboard` | **Date**: 2026-08-04

## 环境

- 后端 `backend/`（Python 3.11+），MySQL 8.0。
- 管理后台 `manageSystem/`（Vue 3 + Vite）。
- 无数据库迁移（纯聚合查询）。

## 后端

```bash
cd backend
./venv/Scripts/python.exe -m pytest -q                                  # 全量测试
./venv/Scripts/python.exe -m pytest -q tests/contract/test_admin_contribution_dashboard.py tests/unit/test_contribution_dashboard_service.py
./venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

登录：`admin` / `change-me-immediately`。

## 管理后台

```bash
cd manageSystem
npm install
npm run dev
```

页面：**业绩贡献** `/contributions` —— 看板（统计 + 趋势 + 排名 + 最新明细）。

## 手工验收路径（对照 spec SC-001~SC-006）

1. 进入业绩贡献页 → 2s 内看到统计与月度趋势（SC-001）。
2. 切换时间范围/月份 → 统计、趋势、明细随之更新且一致（SC-002）。
3. 组织业绩排名 → 与各组织当月贡献值汇总一致（SC-003）。
4. 个人业绩排名 → 与个人当月贡献记录一致（SC-004）。
5. 绑定数量排名（个人/组织切换）→ 与实际已绑定客户数一致（SC-005）。
6. 最新明细确为最近 30 条（按发生时间倒序）（SC-006）。
7. 组织树选择器筛选组织及子树 → 排名/统计限缩到该范围（FR-004）。

## 测试数据（dev 库）

- 组织树：总部(2)→华北区(3)→石家庄(4)；分销员 1/2/3 与既有客户/账单/贡献数据。
- 用现有 `contribution_records` 验证统计/趋势/排名口径。
