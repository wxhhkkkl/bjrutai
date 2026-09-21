# Implementation Plan: 文章评论、点赞与审查

**Branch**: `020-article-comments` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/020-article-comments/spec.md`

## Summary

为已登录的小程序用户增加文章评论阅读、发表评论、点赞/取消点赞能力；评论先经过后端本地化规则审查，安全内容自动公开，命中或不确定内容进入待审核/受控拒绝状态。普通用户、客户顾问和组织管理员均可评论，但后台管理员身份不自动获得小程序评论身份。管理后台新增评论列表、详情、审查、隐藏/恢复、置顶/取消置顶和软删除能力，并使用 `comments.read` / `comments.write` 权限。通过独立评论表、点赞唯一约束、动作快照、幂等键和版本号保证数据一致性；删除业务数据在 7 天后清理，安全审计仍按系统策略保留。

## Technical Context

**Language/Version**: Python 3.11+；JavaScript（Vue 3.5、原生微信小程序 JavaScript）  
**Primary Dependencies**: FastAPI 0.115、SQLAlchemy 2.0 async、Pydantic v2、Alembic；Vue 3、Vite、Element Plus、Pinia、Axios；微信小程序原生 API  
**Storage**: 腾讯云 MySQL 8.0（生产）；SQLite/测试数据库（自动化测试）  
**Testing**: pytest + pytest-asyncio（后端单元、契约、集成）；Vitest + Vue Test Utils（管理后台）；Node test/现有小程序测试工具  
**Target Platform**: Linux 后端服务、现代桌面浏览器管理后台、微信小程序  
**Project Type**: Web service + admin SPA + mobile mini-program  
**Performance Goals**: 评论公开列表和点赞接口在正常网络下 p95 < 500ms（不含冷启动）；使用索引 cursor 分页，单次最多 50 条公开评论、100 条后台记录  
**Constraints**: 所有评论接口需登录；正文仅纯文本/文字表情，最多 500 字；每用户每分钟最多 3 次提交；本地审查不得调用第三方；不支持回复、链接、图片和语音；后台操作必须审计并使用乐观锁  
**Scale/Scope**: 每篇文章最多约 100,000 条评论的索引查询范围；一篇文章最多 1 条置顶；新增 3 张评论相关表、5 组 API 动作、一个管理后台页面及文章详情评论区

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Pre-design | Post-design | Evidence |
|---|---|---|---|
| I. Test-Driven Development | PASS | PASS | 先写评论/点赞/权限/审查契约测试，再实现模型和服务；补充前端状态测试、完整登录到审核的集成测试及 7 天清理测试。 |
| II. API-First Design | PASS | PASS | [API contract](./contracts/api.md) 先定义登录前置、统一响应、幂等键、cursor、动作、错误码和隐私边界；两端只调用后端 API。 |
| III. Separation of Concerns | PASS | PASS | 后端负责认证、文章状态、审查、限流、置顶、幂等、权限和审计；管理后台与小程序只负责展示、输入校验和交互状态。 |
| IV. Database Integrity | PASS | PASS | 使用 `020` Alembic 迁移、唯一约束和事务；点赞计数与关系原子更新；公开响应脱敏；业务动作写入 `comment_actions`，安全摘要写入既有 `AuditLog`。 |
| V. Simplicity (YAGNI) | PASS | PASS | 复用现有 JWT、文章 API、请求服务、权限和维护任务；本地规则服务为单一实现，不引入第三方审核、回复树、媒体存储或额外仓储抽象。 |

Gate status: PASS。不存在需要豁免的宪章违规，也没有未解决的需求澄清项。

## Project Structure

### Documentation (this feature)

```text
specs/020-article-comments/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md
│   └── admin-page.md
└── tasks.md                 # 后续 /speckit-tasks 生成，本阶段不创建
```

### Source Code (repository root)

```text
backend/
├── migrations/versions/
│   └── 020_article_comments.py
├── src/
│   ├── api/v1/
│   │   ├── article_comments.py
│   │   └── admin_comments.py
│   ├── models/
│   │   ├── article_comment.py
│   │   ├── comment_like.py
│   │   ├── comment_action.py
│   │   └── __init__.py
│   ├── schemas/comment.py
│   ├── services/
│   │   ├── comment_moderation.py
│   │   ├── comment_service.py
│   │   └── seed_service.py
│   ├── tasks/maintenance_tasks.py
│   └── main.py
└── tests/
    ├── contract/
    │   ├── test_comments.py
    │   └── test_admin_comments.py
    ├── integration/test_comment_cleanup.py
    └── unit/
        ├── test_comment_moderation.py
        └── test_comment_service.py

manageSystem/
├── src/
│   ├── api/comments.js
│   ├── constants/permissions.js
│   ├── router/index.js
│   ├── App.vue
│   └── pages/comments/index.vue
└── tests/comments.spec.js

miniProgram/
├── models/comment.js
├── services/comment-service.js
├── pages/article-detail/
│   ├── index.js
│   ├── index.wxml
│   └── index.wxss
└── tests/
    ├── contract/comment-api-contract.test.js
    ├── integration/article-comments-flow.test.js
    └── unit/comment.test.js
```

**Structure Decision**: 沿用仓库现有三层结构。评论业务集中在后端 `comment_service.py` 和 `comment_moderation.py`，路由仅做认证/权限/输入输出转换；文章详情页复用现有文章页面并在正文下方增加评论区；后台新增独立页面，不把评论管理塞入文章编辑页；维护任务复用既有 `maintenance_tasks.py`，避免新增调度抽象。

## Implementation Sequence

1. **Red tests and contracts**：新增 API 契约、审查规则、状态迁移、并发版本、点赞幂等、权限和清理测试；确认未实现时失败。
2. **Schema and models**：创建 `020` 迁移、三张评论表、索引/唯一约束、模型导入；实现软删除和置顶约束。
3. **Moderation and domain service**：实现 Unicode NFKC/空白标点归一化、本地规则版本、性/暴力/政治/其他分类、链接/HTML/控制字符校验、3 次/分钟限流、显示名/头像快照和 7 天动作清理。
4. **Mini-program API**：新增评论列表、创建、点赞和取消点赞；接入现有 JWT、统一响应、幂等键和文章发布校验；通过测试后接入请求服务和模型适配。
5. **Admin API/RBAC**：增加 `comments.read/write` 权限、列表/详情/动作接口、审计摘要和 `expectedVersion` 冲突；用测试固定脱敏和动作边界。
6. **Mini-program UI**：在文章详情正文后加入登录可见的评论列表、加载更多、输入/字符计数、待审查反馈、点赞状态和失败重试；不得使用富文本 HTML 渲染评论。
7. **Admin UI**：增加路由、菜单、筛选表格、详情抽屉、时间线、权限控制和危险动作确认；处理空态、局部错误和版本冲突。
8. **Maintenance and regression**：注册每日清理任务，运行后端/后台/小程序测试、迁移检查和生产构建，最后核对公开 API 隐私输出。

## Implementation Design

### Moderation flow

评论文本先在后端进行长度、控制字符、链接/媒体/HTML 校验，再进行 NFKC 归一化和本地规则匹配。明确命中性、暴力、政治规则时拒绝或进入受控待审核；规则未覆盖或服务异常时进入 `pending`，不会公开。规则词表与版本仅存在服务端配置，动作记录保存分类和版本，不保存命中片段。

### Consistency flow

创建评论通过 `(user_id, idempotency_key)` 唯一键防止重试重复；点赞通过 `(comment_id, user_id)` 唯一键和事务计数防止重复；置顶在同一事务内取消同文章旧置顶；后台动作必须携带 `expectedVersion` 并在更新和动作快照同一事务中提交。

### Retention flow

软删除立即从公开查询中排除并删除公开点赞关系；`article_comments.content`、审查信息和 `comment_actions` 业务快照保留 7 天。维护任务只清理已删除且超过 7 天的业务数据，不删除安全 `AuditLog`。

## Complexity Tracking

无宪章违规，不需要复杂度豁免。
