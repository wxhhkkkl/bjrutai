# Quickstart: 组织人员管理（组织架构 + 分销员 + 组织管理员业绩视图）

## Prerequisites

- Python 3.11+
- Node.js 18+（管理后台 `manageSystem/`）
- MySQL 8.0（腾讯云，TLS 可达）
- Git
- 已有 001 系统运行环境（本特性在其上进行演进迁移）

## Environment Setup

沿用 001 quickstart：配置 `backend/.env`（DATABASE_URL、WECHAT、JWT、RUTAI、COS）。本特性不新增环境变量类型。

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # 编辑真实值
```

## Migration

```bash
cd backend
alembic upgrade head      # 执行 004 迁移序列（建表 + 数据迁移 + 外键切换）
```

迁移包含：`organizations`、`distributors`、`org_qualifications` 建表，`users` 加 `password_hash`，旧 `promoters`/`hierarchy_nodes`/`qualifications` 数据迁移与废弃，`customers`/`promotion_codes`/`contribution_records`/`binding_requests` 外键切换，`roles` 权限点更新。

**迁移前置**：数据库备份/快照。**迁移后**：运行一致性校验（行数、贡献值求和、客户绑定数、推广码数），见 `backend/tests/integration/test_migration_*`。

## Test

```bash
cd backend
pytest                          # unit + integration + contract（含迁移正确性）
cd ../manageSystem
npm test                        # admin 组件测试（如配置）
```

## Feature Walkthrough

### 后台：组织人员管理（管理后台）

1. 登录后台 → 进入"组织人员管理"（新增菜单）。
2. **组织树**：创建多级组织（如总部 → 华北区 → 石家庄）、编辑、整体迁移；尝试环路迁移应被拦截。
3. **组织详情 → 资质文件**：上传资质（营业执照等）→ 审核通过 → 组织业务可用；到期前 30 天提醒。
4. **组织详情 → 分销员**：新建分销员账户（姓名+手机号+初始密码）→ 该分销员归属本组织；调整归属/停用/重置凭证。
5. **组织详情 → 组织管理员**：将若干分销员设为管理员（`org_admin:assign` 权限）。
6. 权限：组织/分销员/管理员设置由细分权限点控制；无权限角色操作被拒。

### 小程序：组织管理员业绩视图

1. 分销员用手机号+密码登录 → 首次登录强制绑定微信。
2. 被授权为组织管理员的用户出现"组织业绩"入口。
3. 进入后查看授权组织及其全部下级组织的业绩汇总 + 各分销员本月/累计贡献值（无客户明细）。
4. 非管理员分销员无该入口；授权撤销后入口消失。

## Acceptance Walkthrough（对应 spec）

| Spec 成功标准 | 验证方式 |
|---|---|
| SC-001 5 分钟闭环 | 后台创建组织 + 新建分销员计时 |
| SC-003/007 组织管理员可见/越权不可见 | 管理员账号登录小程序 vs 非管理员账号 |
| SC-004 非法操作拦截 | 环路迁移、重复手机号、删除非空组织 |
| SC-005 资质提醒/过期暂停 | 设置 30 天内到期资质，观察提醒与暂停 |
| SC-006 汇总一致性 | 组织业绩汇总 vs 各分销员个人贡献值求和 |
| SC-009/010 迁移完整 | 迁移校验脚本 + 迁移后功能走查 |
| SC-011 权限拦截 | 无权限角色访问组织管理接口 |
