# Implementation Plan: 小程序注册自动挂载默认组织顶级部门

**Branch**: `012-register-default-dept` | **Date**: 2026-08-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-register-default-dept/spec.md`

## Summary

新用户通过微信小程序注册（微信授权或手机号+密码）时，系统自动创建 Distributor 记录并将其挂载到默认组织根节点（`parent_id = NULL` 且 `sort_order` 最小的组织节点）。同时将 profile-setup 页面改为可选信息完善页，消除"请联系管理员创建账号"的阻断提示。

Technical approach: 在现有 `wechat_login` 和 `distributor_login` 流程中注入自动挂载逻辑，新增 `source_channel` 字段区分注册来源，复用已有 `Distributor`/`Organization` 模型。

## Technical Context

**Language/Version**: Python 3.11+ (backend), JavaScript (WeChat Mini Program)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.0+ async, WeChat Mini Program SDK
**Storage**: MySQL 8.0 on TencentDB (tables: `users`, `distributors`, `organizations`)
**Testing**: pytest + pytest-asyncio (backend, TDD required per constitution)
**Target Platform**: Linux server (backend), WeChat Mini Program (iOS/Android)
**Project Type**: web-service + mobile mini-program
**Performance Goals**: 注册到挂载完成 < 30s (SC-001)
**Constraints**: Must not break existing phone+password distributor login flow
**Scale/Scope**: 预计百级分销员规模，无并发瓶颈

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. TDD (NON-NEGOTIABLE) | ✅ PASS | 所有后端变更将遵循 TDD：先写失败测试，再实现。前端变更通过手工验收测试覆盖。 |
| II. API-First Design | ✅ PASS | 仅修改现有 `/auth/wechat-login` 和 `/auth/session` 响应格式（向后兼容新增字段），无新 API 端点。 |
| III. Separation of Concerns | ✅ PASS | 自动挂载逻辑集中在 backend `auth_service.py`；前端仅处理路由和 UI 变更。 |
| IV. Database Integrity | ✅ PASS | 新增 `source_channel` 字段通过 Alembic 迁移管理；手机号脱敏沿用现有机制。 |
| V. Simplicity (YAGNI) | ✅ PASS | 无新增抽象层；直接复用 `Distributor` 模型；默认组织通过 SQL 查询动态确定，无需配置表。 |

**Gate result**: ALL PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/012-register-default-dept/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API response contracts)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (changes)

```text
backend/
├── src/
│   ├── models/
│   │   └── distributor.py          # ADD: source_channel field
│   ├── services/
│   │   ├── auth_service.py         # MODIFY: wechat_login auto-creates Distributor
│   │   └── distributor_service.py  # ADD: get_default_org(), register_distributor()
│   └── schemas/
│       └── auth.py                 # MODIFY: response schemas to include distributor info
├── migrations/
│   └── versions/
│       └── 012_add_distributor_source_channel.py  # NEW: migration
└── tests/
    ├── unit/
    │   └── test_auth_service.py    # MODIFY: add auto-mount test cases
    └── integration/
        └── test_auth_api.py        # MODIFY: add registration flow tests

miniProgram/
├── pages/auth/
│   ├── login/index.js             # MODIFY: routing logic for auto-mounted users
│   └── profile-setup/index.js     # MODIFY: optional info page, remove blocking modal
├── services/
│   ├── auth-service.js            # MODIFY: handle distributor info in wechatLogin response
│   └── session-service.js         # MODIFY: adjust getEntry() for optional profile page
└── models/
    └── auth-onboarding.js         # MODIFY: update DEFAULT_ORGANIZATION reference
```

## Complexity Tracking

*(No violations — table intentionally empty)*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
