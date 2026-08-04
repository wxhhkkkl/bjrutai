# Quickstart: 绩效规则模块

**Branch**: `006-performance-rules` | **Date**: 2026-08-03

## 环境

- 后端 `backend/`（Python 3.11+，venv 在 `backend/venv/`），MySQL 8.0（Tencent Cloud）。
- 管理后台 `manageSystem/`（Vue 3 + Vite）。
- 沿用既有月度结算调度（`monthly_settlement_job`）。

## 后端

```bash
cd backend
./venv/Scripts/python.exe -m pytest -q                          # 全量测试
./venv/Scripts/python.exe -m pytest -q tests/contract/test_admin_performance_rules.py tests/unit/test_commission_service.py
./venv/Scripts/python.exe -m alembic upgrade head               # 应用 009/010
./venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

登录：`admin` / `change-me-immediately`（生产必须改）。

## 管理后台

```bash
cd manageSystem
npm install
npm run dev
```

页面：
- **绩效规则** `/performance-rules`（原分成规则）：左组织树 + 右两种提成方式配置、阶梯编辑、变更历史、实时预览、月度结果。

## 手工验收路径（对照 spec SC-001~SC-009）

1. 导航显示"绩效规则"，无"分成规则"（SC-006）。
2. 左组织树默认选中根组织；切换组织 2s 内展示对应配置（SC-002）。
3. 为组织配置"组织内绩效提成"阶梯 → 保存 → 版本递增、变更历史可查（SC-001/SC-005）。
4. 配置"组织管理绩效提成"阶梯 → 保存生效。
5. 阶梯区间重叠 → 被拒（SC-007）。
6. 实时预览某周期 → 成员/管理员提成与规则一致；月度结算后结果落库可查（SC-008/SC-009）。
7. 将已有管理员的组织再设第二管理员 → 被拒；撤销后可设（SC-003/SC-004）。
8. 旧"分成规则"入口不可访问（FR-010）。

## 测试数据（dev 库）

- 组织树：总部(2)→华北区(3)→石家庄(4)；分销员 1 = org2 管理员（13800000001），分销员 2/3 = org3 成员。
- 用现有客户/账单数据验证提成预览。
