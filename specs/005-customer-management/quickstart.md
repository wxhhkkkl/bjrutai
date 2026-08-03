# Quickstart: 客户管理模块

**Branch**: `005-customer-management` | **Date**: 2026-08-03

## 环境

- 后端: `backend/`，Python 3.11+，venv 已存在于 `backend/venv/`。
- 数据库: MySQL 8.0（Tencent Cloud）；连接串在 `backend/.env`（gitignored）。
- 哈尔滨互联网医院接口: `RUTAI_MOCK=true` 时为本地 mock（`bind_bj_user` 恒返回 matched）。
- 管理后台: `manageSystem/`，Vue 3 + Vite + Element Plus。

## 后端

### 安装依赖
```bash
cd backend
./venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 运行测试（TDD 主入口）
```bash
cd backend
./venv/Scripts/python.exe -m pytest -q
```

新功能相关测试：
```bash
./venv/Scripts/python.exe -m pytest -q tests/contract/test_admin_customers.py tests/unit/test_customer_admin_service.py
./venv/Scripts/python.exe -m pytest -q tests/contract/test_binding.py   # 含去重用例
```

### 迁移
```bash
cd backend
./venv/Scripts/python.exe -m alembic upgrade head   # 应用 008_customer_change_logs
```

### 启动服务
```bash
cd backend
./venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```
> 每次修改后端代码后需重启（settings 有 lru_cache）。API 文档: http://127.0.0.1:8000/docs

### 登录（验收用）
- 管理员: `admin` / `change-me-immediately`（见 `backend/.env.example`，生产必须改）
- 分销员示例: `13800000001` / `pass12345`（组织管理员，org 2）

## 管理后台

```bash
cd manageSystem
npm install
npm run dev        # 访问 http://127.0.0.1:5173
```

页面:
- **客户管理** `/customers`：左组织树 + 右客户列表，默认选中根组织；"新建客户"手工录入；客户行"更改推广员"。
- **客户详情** `/customers/:id`：基本信息（身份证/医保账户脱敏可编辑）、绑定记录、贡献、跟进；"推广员变更记录"。

## 手工验收路径（对照 spec SC-001~SC-009）

1. 登录后台 → 客户管理 → 默认展示根组织子树客户（SC-002）。
2. 切换组织 → 客户列表按该组织及下级范围变化。
3. 新建客户（选推广员）→ 录入即匹配，mock 下 status=已绑定；查看详情可见脱敏身份证/医保账户（SC-001/SC-003/SC-004/SC-009）。
4. 编辑敏感字段不填原因 → 被拦截（SC-006）。
5. 更改推广员 → 填原因 → 成功；详情"推广员变更记录"可见完整记录（SC-005）。
6. 菜单中已无"绑定管理"（SC-007）。
7. 用无 `customers.write` 权限角色操作写接口 → 拒绝（SC-008）。
