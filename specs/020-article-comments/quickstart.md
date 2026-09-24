# 文章评论功能验证指南

## 1. 环境准备

本功能不新增第三方依赖。使用仓库现有 Python、Node.js、FastAPI、Vue、微信小程序工具链和数据库配置。

```bash
cd /Users/leelee/Desktop/北京鲁泰微信小程序项目/LuTaiMiniProgram
cp backend/.env.example backend/.env  # 如本地尚未创建，按项目说明填写
```

确认数据库连接、JWT 配置和已有文章测试数据已准备好；评论内容审查词表由后端本地配置维护，不放入小程序包。

## 2. 迁移与启动

```bash
cd backend
alembic upgrade head
uvicorn src.main:app --reload --host 127.0.0.1 --port 8001
```

另开终端启动管理后台：

```bash
cd manageSystem
npm install
npm run dev
```

小程序端使用微信开发者工具打开 `miniProgram/`，将请求基地址指向上述后端；生产环境必须使用已配置的 HTTPS 合法域名。

## 3. 自动化验证

先按 TDD 顺序运行新增测试，确认未实现时失败，再实现最小代码使其通过：

```bash
cd backend
pytest tests/contract/test_comments.py tests/contract/test_admin_comments.py \
  tests/unit/test_comment_moderation.py tests/unit/test_comment_service.py \
  tests/integration/test_comment_cleanup.py -q

cd ../manageSystem
npm run test -- --run
npm run build

cd ../miniProgram
node --test tests/unit/comment.test.js tests/contract/comment-api-contract.test.js \
  tests/integration/article-comments-flow.test.js
```

提交前再运行项目现有的后端全量测试、管理后台测试和小程序测试。

## 4. 手工验收场景

1. 未登录打开已发布文章：正文仍按现有登录前置流程处理；评论数量、评论正文、点赞状态和评论输入区均不请求、不显示。
2. 普通用户、客户顾问、组织管理员登录后打开同一文章：可以读取可见评论并发表评论；后台管理员账号不因后台角色自动成为小程序评论用户。
3. 提交 1–500 字纯文本和文字表情：本地审查通过后立即显示；提交命中性、暴力、政治规则或审查不确定内容：不进入公开列表，显示待审核或受控拒绝提示。
4. 提交链接、图片、语音、HTML、脚本、控制字符、空白或 501 字：服务端拒绝且保留客户端草稿；1 分钟内第 4 次提交被限流。
5. 对同一评论重复点赞和取消点赞：结果幂等，点赞数不重复增加且不低于零；刷新评论列表后 `liked` 与服务端一致。
6. 管理后台仅有 `comments.read`：可以筛选、查看详情和动作时间线，但没有处置按钮；增加 `comments.write` 后可以审核、隐藏、恢复、置顶、取消置顶和软删除。
7. 同一文章置顶另一条评论：旧置顶自动取消；隐藏、拒绝或删除置顶评论时自动取消置顶并从公开列表消失。
8. 两个管理员同时修改一条评论：后提交者收到 `40910`，刷新后看到最新状态，不能覆盖新版本。
9. 将删除评论的 `deleted_at` 调整到 8 天前运行清理任务：正文、业务动作快照和评论点赞关系按策略清理；安全 `AuditLog` 不因本任务删除。

## 5. 隐私检查

- 公开接口响应不得包含手机号、身份证号、user ID、token、完整审查词条或点赞用户列表。
- 管理端只能看到显示名快照和必要的评论内容；API 和 UI 都不得使用 `v-html` 渲染正文。
- 日志与安全审计只记录 commentId、articleId、动作、结果和脱敏标识，不复制完整评论正文或命中片段。
