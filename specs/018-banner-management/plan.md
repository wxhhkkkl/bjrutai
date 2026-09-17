# Implementation Plan: 首页轮播图管理

**Branch**: `018-banner-management` | **Date**: 2026-09-14 | **Spec**: `spec.md`

## Summary

新增 `banners` 数据表和公开/后台 API；后台管理页复用 COS 预签名上传模式，并在编辑时从已发布文章下拉列表中选择跳转目标；小程序首页以独立请求加载已启用轮播图，并在文章动作下复用现有文章详情路由。首页从业务工作台调整为健康内容首页，采用“轮播服务视觉 + 心脑维养一主两次 + 三条健康资讯 + 深色企业故事一主两次”的原生小程序编排；继续使用既有文章与轮播接口，不新增数据依赖。

## Constitution Check

- 规格先行：通过；轮播内容、状态、权限、跳转范围与失败状态均已定义。
- 视觉：采用现代健康服务的信息编排，以珍珠白、柔和青绿和深青企业影像建立节奏；保留必要的小圆角，不使用连续同质卡片、英文栏目眉标或装饰性渐变。
- 隐私：轮播图不存储或展示客户信息；后台不记录图片二进制或凭据。
- 外部依赖：图片经现有 COS 预签名上传；发布环境须将 COS 图片域名配置为小程序下载/图片合法域名。
- 测试：覆盖公开过滤与排序、管理员生命周期、前端数据适配和首页请求隔离。

## Files

- `backend/src/models/banner.py`
- `backend/src/schemas/banner.py`
- `backend/src/services/banner_service.py`
- `backend/src/api/v1/banners.py`
- `backend/src/api/v1/admin_banners.py`
- `backend/migrations/versions/017_add_banners.py`
- `manageSystem/src/pages/banners/index.vue`
- `manageSystem/src/router/index.js`
- `manageSystem/src/App.vue`
- `miniProgram/services/banner-service.js`
- `miniProgram/models/banner.js`
- `miniProgram/pages/home/index.js`
- `miniProgram/pages/home/index.wxml`
- `miniProgram/pages/home/index.wxss`
- `miniProgram/tests/integration/workbench-pages.test.js`
- backend and mini-program focused tests
