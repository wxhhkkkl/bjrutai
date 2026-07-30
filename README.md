# 北京儒泰分销管理系统

北京儒泰公司与哈尔滨儒泰互联网医院的业务协作平台。北京负责客户拓展，儒泰负责在线诊疗及医药服务，双方通过接口打通实现客户流转、绑定归属、账单同步和贡献值自动计算。

## 项目结构

```
├── backend/              # Python FastAPI 后端 API
│   ├── src/
│   │   ├── models/       # SQLAlchemy 数据模型 (25 张表)
│   │   ├── schemas/      # Pydantic 请求/响应模型
│   │   ├── api/v1/       # API 路由 (89+ 接口)
│   │   ├── services/     # 业务逻辑层
│   │   ├── integrations/ # 外部 API 客户端 (微信、儒泰、COS)
│   │   ├── core/         # 配置、安全、数据库、中间件
│   │   └── tasks/        # APScheduler 定时任务
│   └── tests/            # 329+ 测试 (contract / integration / unit)
│
├── admin/                # Vue 3 + Vite 管理后台
│   ├── src/
│   │   ├── pages/        # 16 个页面
│   │   ├── components/   # 7 个可复用组件
│   │   ├── stores/       # 10 个 Pinia 状态管理
│   │   ├── api/          # Axios HTTP 客户端 (JWT 自动刷新)
│   │   └── router/       # Vue Router (权限守卫)
│   └── tests/
│
├── miniProgram/           # 微信小程序前端 (已有，不修改)
├── specs/                 # 规格文档 (spec, plan, tasks, contracts, data-model)
└── docs/                  # 需求文档和接口文档
```

## 技术栈

| 层 | 技术 |
|---|------|
| **后端** | Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| **管理后台** | Vue 3 (Composition API), Vite, Element Plus, Pinia, Axios |
| **数据库** | MySQL 8.0 (腾讯云, TLS 连接) |
| **文件存储** | 腾讯云 COS |
| **测试** | pytest + pytest-asyncio (后端), Vitest (前端) |
| **部署** | Docker |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8.0 (腾讯云远程或本地)

### 后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际的数据库、微信、儒泰 API 等配置

# 运行数据库迁移
alembic upgrade head

# 初始化种子数据 (管理员账号、角色、根节点)
python -m src.seed

# 启动开发服务器
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档自动生成：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 管理后台

```bash
cd admin

# 安装依赖
npm install

# 配置 API 地址
cp .env.example .env
# 编辑 VITE_API_BASE_URL

# 启动开发服务器
npm run dev
```

### 运行测试

```bash
# 后端测试 (TDD)
cd backend
pytest                          # 全部测试
pytest tests/contract/          # 接口契约测试
pytest tests/integration/       # 集成测试
pytest tests/unit/              # 单元测试
pytest --cov=src --cov-report=html  # 覆盖率报告

# 管理后台测试
cd admin
npm run test
```

## 核心功能

| 模块 | 说明 |
|------|------|
| 微信登录 | 小程序微信授权登录 + 手机号绑定，管理后台账号密码登录 |
| 层级管理 | 5-6 级树形层级结构，环路检测，分支迁移，历史快照 |
| 资质审核 | 法人公司资质上传 (营业执照等)，管理员审核通过/驳回，到期提醒 |
| 推广码 | 资质通过后自动生成专属二维码 (含 BJTR 来源标识)，支持刷新和统计 |
| 客户绑定 | 医生录入患者信息 → 调用儒泰接口匹配 → 绑定至拓展人，支持解绑/转移 |
| 数据同步 | 每分钟轮询儒泰 getBindUser，自动拉取 getUserBill，游标分页防漏 |
| 贡献值计算 | 实付金额 × 换算系数，逐级向上汇总至整棵层级树 |
| 分账规则 | 按层级配置 (固定比例/固定金额/阶梯)，生效时间调度，变更日志 |
| 对账报表 | 多维报表 (客户/收款/折扣/分配)，Excel 导出，数据偏差 ≤ 0.01% |
| 内容管理 | 科普文章 CMS (富文本编辑、发布/下架、分类管理) |
| 权限管控 | RBAC 角色权限模型 (管理员/财务/运营)，JWT 双令牌机制 |
| 合规 | 隐私协议弹窗、数据脱敏、完整审计日志 (永久保留) |

## 外部接口对接

| 接口 | 提供方 | 说明 |
|------|--------|------|
| bindBjUser | 哈尔滨儒泰 | 北京录入患者信息后调用，儒泰进行匹配绑定 |
| getBindUser | 哈尔滨儒泰 | 每分钟轮询，获取新标记的北京来源用户 |
| getUserBill | 哈尔滨儒泰 | 按用户查询账单明细 (诊费/医药费/折扣/实付) |
| getAllUsersBill | 哈尔滨儒泰 | 日终补偿对账，按日期查询全部北京来源账单 |

接口文档：`docs/2026.7.17-与哈尔滨小程序接口对接技术文档V1.0.pdf`

## 规格文档

完整的设计和任务文档在 `specs/001-distribution-management-api/`：

| 文档 | 说明 |
|------|------|
| spec.md | 功能规格 (10 个用户故事, 75 条功能需求) |
| plan.md | 实施计划 (技术上下文, 架构, 项目结构) |
| research.md | 15 项技术调研 (FastAPI, JWT, RBAC, 幂等, 分页...) |
| data-model.md | 25 张表的完整 DDL, ER 图, 状态机 |
| contracts/ | 89 个 API 接口契约 (9 个模块) |
| tasks.md | 200 项实施任务 (全部完成) |
| quickstart.md | 环境搭建和验证清单 |

## 后端定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| sync-bind-users | 每 60 秒 | 轮询儒泰 getBindUser |
| sync-user-bills | 每 5 分钟 | 为新增绑定用户拉取账单 |
| retry-failed-sync | 每 10 分钟 | 重试失败的同步 |
| monthly-settlement | 每月 1 日 00:05 | 批量结算上月贡献值 |
| qualification-expiry-check | 每日 09:00 | 检查即将到期的资质 |
| idempotency-cleanup | 每小时 | 清理超过 24 小时的幂等记录 |

## 环境变量

关键环境变量（详见 `backend/.env.example`）：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | MySQL 连接字符串 (mysql+aiomysql://) |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信小程序凭证 |
| `JWT_SECRET_KEY` | JWT 签名密钥 |
| `RUTAI_API_BASE_URL` | 哈尔滨儒泰 API 地址 |
| `RUTAI_API_KEY` / `RUTAI_API_SECRET` | 儒泰接口认证密钥 |
| `COS_SECRET_ID` / `COS_SECRET_KEY` | 腾讯云 COS 凭证 |
| `ADMIN_DEFAULT_USERNAME` / `ADMIN_DEFAULT_PASSWORD` | 管理员初始账号 |

## License

私有项目 — 北京儒泰公司内部使用
