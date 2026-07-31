# Research: 文章管理增强

**Feature**: 003-article-editor-cos | **Date**: 2026-07-31

## 1. 富文本编辑器选型

**Decision**: Quill (via `@vueup/vue-quill`)

**Rationale**:
- 成熟稳定的开源富文本编辑器,中文社区活跃
- Vue 3 官方适配 (`@vueup/vue-quill`), 开箱即用
- 轻量 (~200KB gzipped), 工具栏可定制
- 原生支持自定义图片上传 handler (替换为后端COS上传)
- 内置危险标签过滤 (script/iframe)

**Alternatives considered**:
- TinyMCE: 功能丰富但体积大, 云服务收费
- Tiptap: 基于ProseMirror, Vue 3 支持好但集成复杂度高
- CKEditor 5: 功能强大但体积大, 定制复杂

## 2. 分类数据模型设计

**Decision**: 新建 `ArticleCategory` 表, Article 增加 `category_id` FK

**Rationale**:
- Article 已有 `category` 字符串字段, 改为外键关联确保数据一致性
- 保留 `category` 字段作为迁移过渡 (填充旧数据后逐步废弃)
- 排序序号 `sort_order` 控制列表展示顺序

**Schema**:
```
ArticleCategory: id, name (unique), sort_order (default 0), created_at
Article: +category_id FK → ArticleCategory.id
```

## 3. COS客户端通用化

**Decision**: `generate_upload_token()` 增加可选 `key_prefix` 参数, 默认 `"qualifications/"`

**Rationale**:
- 现有客户端硬编码 `qualifications/` 前缀, 将前缀参数化即可复用
- 文章图片路径: `articles/{YYYY/MM}/{uuid}.{ext}`
- 允许的文件类型拓展为: image/jpeg, image/png, image/gif, image/webp
- 前端通过后端获取预签名URL后直传COS → 返回COS URL → 插入编辑器

**Alternatives**: 新建独立 ArticleCOSClient — 过度设计, 违反YAGNI

## 4. 文章预览方案

**Decision**: 新标签页独立预览页面 (`/articles/preview/:id`), 服务端渲染文章HTML

**Rationale**:
- 新标签页不影响编辑状态, 编辑内容通过路由参数或临时存储传递
- 预览页面展示完整布局: 标题、分类标签、正文HTML (v-html)
- 无需独立预览API, 复用现有文章详情接口

## 5. 图片上传流程

**Decision**: 前端 → 后端获取预签名URL → 前端直传COS → 返回COS URL → 插入编辑器

**Rationale**:
- 前端不持有COS凭证 (安全)
- 图片不经后端中转 (节省带宽和内存)
- 后端负责验证文件类型/大小并生成预签名URL
- 预签名URL有效期10分钟
