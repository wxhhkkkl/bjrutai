<template>
  <div class="articles-page">
    <div class="page-header">
      <h2 class="page-title">文章管理</h2>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon><Plus /></el-icon>
        新建文章
      </el-button>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <el-radio-group v-model="store.filterStatus" @change="handleFilterChange">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="draft">草稿</el-radio-button>
        <el-radio-button value="published">已发布</el-radio-button>
        <el-radio-button value="unpublished">已下架</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="store.filterKeyword"
        placeholder="搜索文章标题"
        clearable
        style="width: 240px; margin-left: 12px"
        @keyup.enter="handleFilterChange"
        @clear="handleFilterChange"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-input
        v-model="store.filterCategory"
        placeholder="分类筛选"
        clearable
        style="width: 180px; margin-left: 12px"
        @keyup.enter="handleFilterChange"
        @clear="handleFilterChange"
      >
        <template #prefix>
          <el-icon><Folder /></el-icon>
        </template>
      </el-input>
      <el-button type="default" @click="handleFilterChange" style="margin-left: 8px">
        搜索
      </el-button>
    </div>

    <!-- Table -->
    <el-table
      v-loading="store.loading"
      :data="store.articles"
      stripe
      style="width: 100%; margin-top: 16px"
      empty-text="暂无文章数据"
    >
      <el-table-column prop="title" label="标题" min-width="200">
        <template #default="{ row }">
          <span class="article-title-link">{{ row.title }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="120">
        <template #default="{ row }">
          <span>{{ row.category || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="store.getStatusType(row.status)" size="small">
            {{ store.getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="author" label="作者" width="120">
        <template #default="{ row }">
          {{ row.author || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="viewCount" label="浏览" width="80" align="center" />
      <el-table-column prop="publishedAt" label="发布时间" width="180">
        <template #default="{ row }">
          {{ row.publishedAt ? formatDate(row.publishedAt) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="updatedAt" label="更新时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.updatedAt) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button
            text
            type="primary"
            size="small"
            @click="handleEdit(row)"
          >
            编辑
          </el-button>
          <el-button
            v-if="row.status !== 'published'"
            text
            type="success"
            size="small"
            @click="handlePublish(row)"
          >
            发布
          </el-button>
          <el-button
            v-if="row.status === 'published'"
            text
            type="warning"
            size="small"
            @click="handleUnpublish(row)"
          >
            下架
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination (load more) -->
    <div v-if="store.hasMore" class="load-more">
      <el-button
        :loading="store.loading"
        size="default"
        @click="handleLoadMore"
      >
        加载更多
      </el-button>
    </div>

    <!-- Article Editor Dialog -->
    <ArticleEditor
      v-model:visible="editorVisible"
      :article="editingArticle"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Search, Folder } from '@element-plus/icons-vue'
import { useArticlesStore } from '@/stores/articles'
import ArticleEditor from '@/components/articles/ArticleEditor.vue'

const store = useArticlesStore()

const editorVisible = ref(false)
const editingArticle = ref(null)

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${mi}`
}

async function loadArticles() {
  await store.fetchArticles({
    status: store.filterStatus || undefined,
    category: store.filterCategory || undefined,
    keyword: store.filterKeyword || undefined,
  })
}

function handleFilterChange() {
  loadArticles()
}

async function handleLoadMore() {
  await store.fetchArticles({
    status: store.filterStatus || undefined,
    category: store.filterCategory || undefined,
    keyword: store.filterKeyword || undefined,
    cursor: store.nextCursor,
  })
}

function showCreateDialog() {
  editingArticle.value = null
  editorVisible.value = true
}

function handleEdit(row) {
  editingArticle.value = { ...row }
  editorVisible.value = true
}

async function handlePublish(row) {
  try {
    await ElMessageBox.confirm(
      `确定要发布文章《${row.title}》吗？`,
      '发布确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'info' }
    )
    await store.publishArticle(row.articleId)
    await loadArticles()
  } catch {
    // Cancelled or error handled in store
  }
}

async function handleUnpublish(row) {
  try {
    await ElMessageBox.confirm(
      `确定要下架文章《${row.title}》吗？下架后文章将不在前端展示。`,
      '下架确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await store.unpublishArticle(row.articleId)
    await loadArticles()
  } catch {
    // Cancelled or error handled in store
  }
}

function handleSaved() {
  editorVisible.value = false
  editingArticle.value = null
  loadArticles()
}

onMounted(() => {
  loadArticles()
})
</script>

<style scoped>
.articles-page {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.article-title-link {
  color: #409EFF;
  cursor: pointer;
}

.article-title-link:hover {
  text-decoration: underline;
}

.load-more {
  text-align: center;
  margin-top: 16px;
}
</style>
