# Quickstart: 小程序文章资讯与阅读

**Feature**: 014-article-reading  
**Date**: 2026-08-10

## 1. Prerequisites

- 当前分支：`014-article-reading`。
- 后端与管理端可运行，数据库已存在文章与文章分类表。
- 使用测试文章，不录入真实患者、手机号、身份证号或其他敏感信息。
- 文章封面和正文图片使用开发环境可访问地址；体验/生产使用微信允许的 HTTPS 域名。
- 微信开发者工具已指向当前后端 API base。

## 2. Prepare acceptance articles

在管理端“文章管理”准备并发布：

1. 3 篇带封面、摘要、分类和作者的普通文章；
2. 1 篇无封面/摘要/分类的最小文章；
3. 1 篇包含标题、段落、列表、粗体、长图和宽图的富文本文章；
4. 超过 20 篇用于分页的已发布文章；
5. 至少 1 篇草稿和 1 篇已下架文章。

草稿和已下架文章不能出现在任何小程序文章入口、列表或详情中。

## 3. TDD checks

### Baseline recorded before article-reading changes (2026-08-10)

- Backend focused baseline: bundled Python 3.12 + `python -m pytest tests/contract/test_articles.py tests/integration/test_article_flow.py -q`; **38 passed**. Only existing dependency deprecation warnings were emitted.
- Mini-program baseline: the system `node` does not support `--test`, so tests use the bundled Node runtime documented below. The full suite reported **159 passed, 2 pre-existing failures**:
  - `tests/contract/api-boundary-contract.test.js`: existing `services/cos-upload.js` calls `wx.request` directly.
  - `tests/contract/page-framework-contract.test.js`: the existing help-feedback contract still expects `profileService.uploadAvatar`, while the accepted implementation now uses `feedbackService.uploadFeedbackImage`.
- These two baseline failures are outside feature 014 and must not be attributed to article-reading changes. Focused feature tests must be green; the final full-suite delta must introduce no additional failures.
- Bundled Node used for this workspace: `/Users/leelee/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.

### Mini-program focused tests

```bash
cd miniProgram
node --test \
  tests/unit/article.test.js \
  tests/contract/article-api-contract.test.js \
  tests/contract/navigation-contract.test.js \
  tests/contract/page-framework-contract.test.js \
  tests/integration/article-reading-flow.test.js \
  tests/integration/workbench-pages.test.js
```

重点验证：

- 列表/详情字段适配、空字段和 malformed response；
- 首页 `limit=3`、列表 `limit=20`、cursor 原样回传；
- 刷新与分页迟到响应隔离、按 ID 去重、无无限加载；
- 两个入口路径一致、详情参数有效编码、防重复导航；
- 详情 404 与网络失败不显示旧正文；
- 文章请求失败不改变首页工作台成功状态。

### Existing backend regression

```bash
cd backend
pytest tests/contract/test_articles.py tests/integration/test_article_flow.py -q
```

现有后端测试必须继续证明仅 published 可见、cursor 分页稳定、下架后 404、详情浏览量递增。

## 4. Start local services

### Backend

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
```

### Admin

```bash
cd manageSystem
npm run dev -- --host 0.0.0.0 --port 5174
```

### Mini-program

在微信开发者工具中打开 `miniProgram/` 并重新编译。本功能不增加 npm 依赖，无需重新构建 npm。

## 5. Manual acceptance

### A. Homepage discovery and isolation

1. 登录进入首页，确认“文章资讯”位于业务概览之后。
2. 确认最多显示 3 篇最新发布文章，点击文章进入正确详情。
3. 点击“查看全部”进入完整列表。
4. 模拟文章接口断网/500，确认首页工作台、快捷服务和业务概览仍正常；文章区域提供轻量错误/入口。

### B. Profile entrance

1. 普通用户进入“我的”，确认文章入口填入指定 2×2 空位。
2. 组织管理员进入“我的”，确认组织业绩和文章入口均存在，宫格分隔与点击正常。
3. 点击文章入口进入同一文章列表，不进入占位页。

### C. List and pagination

1. 首屏按发布时间倒序，卡片展示可用封面、标题、摘要、分类、发布时间。
2. 连续加载超过 20 篇，无重复、无遗漏。
3. 分页时模拟失败，已加载内容保留；点击重试后继续追加。
4. 下拉刷新回到最新首屏并清除旧 cursor。
5. 空数据时只显示空状态，不读取 Mock。

### D. Rich-text detail

1. 从首页和列表分别打开富文本文章。
2. 检查标题、元信息、封面、摘要和正文与后台一致。
3. 检查段落、列表、粗体和图片；宽图不得横向溢出。
4. 页面显示/切后台再返回不应再次请求详情；重新退出再进入可形成新的查看。
5. 从详情返回，原列表内容和滚动位置保持。

### E. Unpublished and failures

1. 打开列表中的文章后，在后台将其下架；再次从旧入口打开应显示“文章已下架或不存在”。
2. 输入无效文章 ID，页面不得发接口请求。
3. 模拟超时、断网、500 和 malformed envelope，验证明确状态与重试，不展示其他文章正文。
4. 正文单图加载失败不影响其他段落阅读。

## 6. Full regression

```bash
cd miniProgram
node --test tests/unit/*.test.js tests/contract/*.test.js tests/integration/*.test.js

cd ../backend
pytest -q
```

若必需检查失败，不进入合并；记录失败命令、环境和未完成的真机验证。

## 7. Visual checks

- 以已确认首页 v4、“我的”Tab v2 和用户当前截图为基线。
- 检查窄屏、常见 iOS/Android 屏幕、微信状态栏/胶囊、安全区和自定义 TabBar。
- 检查普通用户 2×2 宫格、管理员多行宫格、长标题、无封面、空列表、分页失败、404 和宽图正文。

## 8. Implementation verification record (2026-08-10)

- Feature-focused mini-program tests: all article model, API, navigation, page-contract and integration checks passed, including refresh stale-response isolation and homepage failure isolation.
- Full mini-program suite after implementation: **180 passed, 2 failed, 0 skipped**. The two failures are exactly the pre-existing baseline failures recorded in section 3; feature 014 introduced no additional failure.
- Existing backend article regression: **38 passed**; no backend production logic was changed.
- JS syntax, page JSON parsing, `git diff --check`, credential scan and the no-`web-view`/no-script execution-path check passed.
- Local read-only probe to `http://127.0.0.1:8001/api/v1/articles?limit=3` could not connect because the backend service was not running at verification time. Therefore sample preparation, WeChat Developer Tools, legal-domain, real-device and 320/375/390px visual checks remain manual items T002/T014/T021/T028/T034/T038/T039.
