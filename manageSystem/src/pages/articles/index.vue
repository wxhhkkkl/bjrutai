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
      <el-select
        v-model="store.filterCategory"
        placeholder="分类筛选"
        clearable
        filterable
        :loading="categoriesStore.loading"
        style="width: 180px; margin-left: 12px"
        @change="handleFilterChange"
        @clear="handleFilterChange"
      >
        <template #prefix>
          <el-icon><Folder /></el-icon>
        </template>
        <el-option
          v-for="category in categories"
          :key="category.id"
          :label="category.name"
          :value="category.name"
        />
      </el-select>
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
      <el-table-column label="封面" width="100" align="center">
        <template #default="{ row }">
          <el-image
            v-if="row.coverImageUrl"
            :src="row.coverImageUrl"
            fit="cover"
            class="cover-thumb"
            :preview-src-list="[row.coverImageUrl]"
            preview-teleported
          />
          <span v-else class="cover-empty">-</span>
        </template>
      </el-table-column>
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
      <el-table-column label="操作" width="260" fixed="right">
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
          <el-tooltip
            :content="row.status === 'published' ? '上架中的文章不能删除，请先下架' : '删除文章及其评论'"
            placement="top"
          >
            <span class="delete-action-wrap">
              <el-button
                text
                type="danger"
                size="small"
                :disabled="row.status === 'published'"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="store.totalCount > 0" class="pagination-bar">
      <el-pagination
        v-model:current-page="store.currentPage"
        v-model:page-size="store.pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="store.totalCount"
        :disabled="store.loading"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
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
import { computed, ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Search, Folder } from '@element-plus/icons-vue'
import { useArticlesStore } from '@/stores/articles'
import { useCategoriesStore } from '@/stores/categories'
import ArticleEditor from '@/components/articles/ArticleEditor.vue'

const store = useArticlesStore()
const categoriesStore = useCategoriesStore()
const categories = computed(() => categoriesStore.categories)

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

async function loadArticles(page = store.currentPage) {
  await store.fetchArticles({
    status: store.filterStatus || undefined,
    category: store.filterCategory || undefined,
    keyword: store.filterKeyword || undefined,
    page,
    limit: store.pageSize,
  })
}

function handleFilterChange() {
  loadArticles(1)
}

function handlePageChange(page) { loadArticles(page) }
function handlePageSizeChange() { loadArticles(1) }

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
    await loadArticles(1)
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
    await loadArticles(1)
  } catch {
    // Cancelled or error handled in store
  }
}

async function handleDelete(row) {
  if (row.status === 'published') return

  try {
    await ElMessageBox.confirm(
      `删除《${row.title}》后，文章、评论及评论相关记录将永久删除且无法恢复，是否继续？`,
      '删除文章确认',
      {
        type: 'warning',
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        distinguishCancelAndClose: true,
      }
    )
    await store.deleteArticle(row.articleId)
    const remaining = Math.max(0, store.totalCount - 1)
    const lastPage = Math.max(1, Math.ceil(remaining / store.pageSize))
    await loadArticles(Math.min(store.currentPage, lastPage))
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      // Request errors are already reported by the store.
    }
  }
}

function handleSaved() {
  editorVisible.value = false
  editingArticle.value = null
  loadArticles(1)
}

onMounted(() => {
  categoriesStore.fetchCategories()
  loadArticles()
})
</script>

<style scoped>
.articles-page {
  padding: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.cover-thumb {
  width: 72px;
  height: 45px;
  border-radius: 4px;
  display: block;
  cursor: pointer;
}

.cover-empty {
  color: #c0c4cc;
}

.delete-action-wrap {
  display: inline-flex;
}

.article-title-link {
  color: var(--el-color-primary);
  cursor: pointer;
}

.article-title-link:hover {
  text-decoration: underline;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
