# Admin Page Contract: 意见与反馈

**Feature**: 013-feedback-management  
**Route**: `/feedbacks`  
**Route permission**: `feedbacks.read`

## 1. Navigation and permission

- 侧栏新增“意见与反馈”，仅 `authStore.hasPermission('feedbacks.read')` 时显示。
- 路由 meta 使用 `permission: 'feedbacks.read'`；直接访问无权限时由现有守卫跳转仪表盘。
- 页面不能根据前端权限替代后端鉴权；任何 403 均显示“没有操作权限”。
- `feedbacks.write` 只控制处理表单和提交按钮，只有 read 的账号仍可查看完整详情。

## 2. Page layout

```text
┌────────────────────────────────────────────────────────────────┐
│ 意见与反馈                                           [刷新]   │
├────────────────────────────────────────────────────────────────┤
│ 状态 [全部▼] 类型 [全部▼] 日期 [开始 - 结束]                  │
│ 反馈编号/用户姓名 [________________] [搜索] [重置]             │
├────────────────────────────────────────────────────────────────┤
│ 编号 │ 类型 │ 内容摘要 │ 图片 │ 用户 │ 手机号 │ 状态 │ 时间 │
│ ...                                                        查看 │
├────────────────────────────────────────────────────────────────┤
│ 共 N 条                       20条/页   < 1 2 3 >               │
└────────────────────────────────────────────────────────────────┘
```

- 过滤区和表格放在白色内容容器中，沿用管理端现有间距、边框和状态标签。
- 日期使用日期范围选择器；请求发送当天开始/结束的明确时间值。
- 状态和类型使用选择器，不增加统计卡或批量操作。

## 3. List behavior

### Columns

| Column | Behavior |
|--------|----------|
| 反馈编号 | 单行展示，可复制；不解析编号格式 |
| 类型 | 功能异常/产品建议/其他标签 |
| 内容摘要 | 最多两行，溢出省略；hover tooltip 展示 API 返回的摘要，不请求全文 |
| 图片 | 显示数量，0 时 `-` |
| 提交用户 | 无姓名显示“未完善姓名”；已注销显示“用户不可用” |
| 手机号 | 仅使用 `phoneMasked`，不得尝试恢复明文 |
| 状态 | 待处理 warning、处理中 primary、已解决 success |
| 提交时间 | 中国本地时间 `YYYY-MM-DD HH:mm` |
| 更新时间 | 中国本地时间；无值显示 `-` |
| 操作 | “查看”打开详情抽屉 |

### Query state

- 页面状态：`listLoading`, `items`, `filters`, `page`, `pageSize`, `total`, `hasMore`。
- 首次进入立即加载；搜索、筛选、重置都将 page 设为 1。
- 翻页保留全部筛选条件。
- “刷新”保留筛选和当前页并重新请求。
- 加载期间表格 loading；无数据展示“暂无符合条件的反馈”；失败使用 `ElMessage.error(error.userMessage || '获取反馈列表失败')`，保留筛选供重试。
- 不将正文、预览 URL 或处理备注写入 console、埋点或异常文案。

## 4. FeedbackDetailDrawer

- 使用右侧抽屉，建议宽度 760–860px；加载完成前展示 skeleton/loading。
- 打开时通过详情 API 获取最新数据，不复用列表摘要作为详情。
- 点击遮罩不应在正在保存时关闭；保存期间禁用重复提交。

### Read-only sections

1. **基本信息**：编号、类型、状态、提交用户、脱敏手机号、提交时间、更新时间、首位处理人、解决人。
2. **问题描述**：保留换行、自动换行，不执行 HTML。
3. **问题截图**：0–3 张缩略图；仅使用详情 API 返回的短时 `previewUrl`，通过 Element Plus 图片预览查看。`available=false` 显示“附件不可用”。
4. **处理记录**：按时间升序的 timeline；展示操作人、前后状态、内部备注和用户可见结果。
5. **处理结果**：已解决时只读展示 resolution 和 notificationStatus。

### Write section

仅 `feedbacks.write` 且反馈未解决时显示：

| Current status | Target options | Form rules |
|----------------|----------------|------------|
| submitted | processing, resolved | processing 的备注可选；resolved 的处理结果必填 |
| processing | processing, resolved | 保持 processing 时内部备注必填；resolved 的处理结果必填 |
| resolved | none | 不渲染处理表单 |

- 内部备注最多 1000 字。
- 用户可见结果最多 500 字，文案提示“该内容将出现在用户站内通知中”。
- 请求始终携带详情中的 `expectedVersion`。

## 5. Success, conflict and failure

### Success

- 使用 PATCH 返回的最新详情替换抽屉数据。
- 清空处理表单，显示“处理已保存”。
- 重新加载当前列表页，保持筛选和页码。
- resolved 后隐藏处理表单并展示站内通知状态。

### HTTP 409

- 显示“反馈已被其他管理员更新，已为你刷新最新内容”。
- 立即重新请求详情和当前列表。
- 不自动重放旧表单，也不覆盖最新结果；旧输入可以清空，管理员基于最新状态重新填写。

### Other errors

- 422：在对应字段展示校验错误，保留输入。
- 403：关闭处理区并提示权限已变化。
- 404：关闭抽屉、提示反馈不存在并刷新列表。
- 网络/500：保留输入，允许再次提交；保存按钮恢复可用。

## 6. Accessibility and responsive behavior

- 所有输入有可见 label，按钮文案不能只依赖图标。
- 状态同时使用文字和颜色，不能仅靠颜色区分。
- 图片缩略图支持键盘聚焦和明确的“预览第 N 张截图”说明。
- 1280px 宽度下列表无需横向遮挡操作列；更窄窗口允许表格横向滚动，操作列固定右侧。
- 抽屉内正文和时间线不得产生页面级横向滚动。

## 7. Component and API boundaries

- `pages/feedbacks/index.vue`: 列表查询、筛选/分页状态、打开/关闭抽屉、成功后刷新。
- `components/feedbacks/FeedbackDetailDrawer.vue`: 详情加载、权限派生、处理表单、版本冲突恢复，并通过事件通知父页刷新。
- `api/feedbacks.js`: `list(params)`, `detail(feedbackNo)`, `update(feedbackNo, body)`，统一解包 response envelope。
- 不创建 Pinia store；本功能没有跨页面共享状态。

## 8. UI acceptance matrix

| State | Expected UI |
|-------|-------------|
| Loading list | table loading，不闪现空状态 |
| Empty list | “暂无符合条件的反馈”，筛选仍可操作 |
| List error | 错误消息 + 可点刷新 |
| Loading detail | drawer loading/skeleton |
| Missing attachment | 单图占位“附件不可用”，其他内容正常 |
| Read-only admin | 可查看详情/图片/时间线，无处理表单 |
| Writable admin | 按状态显示允许动作 |
| Resolved | 终态只读，显示结果和通知状态 |
| 409 conflict | 提示、拉新详情、不覆盖 |
| Notification failed | 反馈仍显示已解决，标注“站内通知补发中” |
