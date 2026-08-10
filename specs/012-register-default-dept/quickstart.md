# Quickstart: 小程序注册自动挂载默认组织顶级部门

**Feature**: 012-register-default-dept
**Date**: 2026-08-08

## 前置条件

1. 数据库中存在至少一个根组织节点（`parent_id = NULL`）。如果不确定，运行：
   ```sql
   SELECT id, name, parent_id, sort_order FROM organizations WHERE parent_id IS NULL ORDER BY sort_order;
   ```

2. 数据库 `distributors` 表和 `users` 表中无测试残留数据（如需清空参考下方）。

3. 微信小程序已配置 AppID 和 AppSecret（通过 `.env` 中的 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`）。

## 开发环境启动

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

### 数据库迁移

```bash
cd backend
alembic upgrade head  # 应用 012_add_distributor_source_channel 迁移
```

## 测试流程

### 1. 微信注册自动挂载（TDD 测试）

```bash
cd backend
pytest tests/unit/test_auth_service.py::test_wechat_register_auto_mount -v
pytest tests/integration/test_auth_api.py::test_wechat_register_creates_distributor -v
```

### 2. 手机号注册自动挂载（TDD 测试）

```bash
pytest tests/unit/test_auth_service.py::test_phone_register_auto_mount -v
pytest tests/integration/test_auth_api.py::test_phone_register_creates_distributor -v
```

### 3. 已有用户绑定不重复创建（TDD 测试）

```bash
pytest tests/unit/test_auth_service.py::test_existing_user_wechat_bind_no_duplicate -v
```

### 4. 手动验收测试

1. 清空测试数据：
   ```sql
   SET FOREIGN_KEY_CHECKS = 0;
   DELETE FROM customers WHERE distributor_id IN (SELECT id FROM distributors);
   DELETE FROM binding_requests WHERE distributor_id IN (SELECT id FROM distributors);
   DELETE FROM commission_results WHERE distributor_id IN (SELECT id FROM distributors);
   DELETE FROM promotion_codes WHERE distributor_id IN (SELECT id FROM distributors);
   DELETE FROM distributors;
   DELETE FROM users WHERE id NOT IN (SELECT id FROM admin_accounts);
   SET FOREIGN_KEY_CHECKS = 1;
   ```

2. 打开微信开发者工具，编译运行小程序。

3. 点击「微信授权登录」→ 授权手机号 → 验证：
   - 是否直接进入首页（或可选信息完善页）
   - 数据库 `distributors` 表中是否新增记录，`source_channel = 'wechat_register'`
   - `org_id` 是否指向 sort_order 最小的根节点

## 关键验证点

| 检查项 | 方法 |
|--------|------|
| 自动挂载成功 | 查询 `SELECT * FROM distributors WHERE source_channel = 'wechat_register'` |
| 不重复创建 | 同一手机号注册两次，`SELECT COUNT(*) FROM distributors WHERE user_id IN (SELECT id FROM users WHERE phone = '...')` = 1 |
| profile-setup 可选 | 在 profile-setup 页点击「跳过」，能进入首页 |
| 默认组织选择正确 | 验证 `org_id` = `(SELECT id FROM organizations WHERE parent_id IS NULL ORDER BY sort_order LIMIT 1)` |
