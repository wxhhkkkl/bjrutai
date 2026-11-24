# 任务：互联网医院跳转统计

- [x] T001 新增 `hospital_visit_events` 模型与迁移（`backend/src/models/hospital.py`、`backend/src/models/__init__.py`、`backend/migrations/versions/050_hospital_visit_events.py`）。验证：`alembic heads` 为 050，后端契约测试建表通过。
- [x] T002 事件上报服务与公开接口（`backend/src/services/hospital_stats_service.py`、`backend/src/api/v1/hospital.py`、`backend/src/api/deps.py` 可选登录）。验证：匿名与登录上报、白名单事件、失败不影响客户端。
- [x] T003 后台统计接口与权限（`backend/src/api/v1/admin_hospital.py`、`backend/src/services/hospital_stats_service.py`、`backend/src/services/seed_service.py`）。验证：总览/按用户/按日、分页、日期校验、403、审计。
- [x] T004 后台路由与菜单（`manageSystem/src/router/index.js`、`manageSystem/src/App.vue`）。验证：有权限才显示入口。
- [x] T005 后台统计页与 API 模块（`manageSystem/src/api/hospital-stats.js`、`manageSystem/src/pages/hospital/stats.vue`）。验证：日期筛选、卡片、两个表格、口径说明。
- [x] T006 小程序上报与登录门槛（`miniProgram/services/hospital-service.js`、`miniProgram/pages/internet-hospital/index.js`、`index.wxml`、`miniProgram/pages/auth/login/index.js`）。验证：未登录跳登录、登录后返回、点击/长按各上报一次、失败静默。
- [x] T007 自动化测试（后端契约测试、管理端页面测试、小程序集成/契约测试）。验证：定向用例通过；全量无新增失败。
- [x] T008 文档（`design-assets/internet-hospital/README.md`、本 spec、任务表）。验证：口径、限制、权限与部署说明一致。
- [x] T009 「按用户统计」按筛选日期导出 Excel（.xlsx，`backend/src/services/hospital_stats_service.py`、`backend/src/api/v1/admin_hospital.py`、`manageSystem/src/api/hospital-stats.js`、`manageSystem/src/pages/hospital/stats.vue`）。验证：xlsx 列头/行数/手机号一致、列宽与文本格式、权限 403、日期校验、导出审计。

## 验证记录（2026-11-24）

- 后端：`pytest tests/contract/test_hospital_stats.py` 5 项通过（含导出）；权限种子测试通过；`tests/unit tests/contract` 全量 858 通过、10 失败，失败项均为既有本地 `.env`/数据问题（与本次无关，基线复现 6 项）。
- 管理端：`vitest run` 全部通过；`npm run build` 成功。
- 小程序：`node --test tests/` 365 通过、16 失败（均为既有首页/文章问题）；新增互联网医院页面集成测试 4 项通过。
- 端到端：本地 8018 接口验证上报/统计/403/422；Playwright 实际渲染后台页并点击「导出」，下载文件名与 xlsx 列头正确。
- 未验证：真实微信后台权限、真实设备长按识别上报（需真机与线上后端）。
