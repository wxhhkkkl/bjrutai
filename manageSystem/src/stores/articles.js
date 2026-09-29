import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useArticlesStore = defineStore('articles', () => {
  // State
  const articles = ref([])
  const currentArticle = ref(null)
  const loading = ref(false)
  const currentPage = ref(1)
  const pageSize = ref(20)
  const totalCount = ref(0)

  // Filter state
  const filterStatus = ref('')
  const filterCategory = ref('')
  const filterKeyword = ref('')

  // Actions
  async function fetchArticles({ status, category, keyword, page = currentPage.value, limit = pageSize.value } = {}) {
    loading.value = true
    try {
      const params = {}
      if (status) params.status = status
      if (category) params.category = category
      if (keyword) params.keyword = keyword
      params.page = page
      params.limit = limit

      const res = await http.get('/admin/articles', { params })
      const data = res.data.data || res.data

      articles.value = data.items || []
      currentPage.value = data.page || page
      pageSize.value = data.pageSize || limit
      totalCount.value = Number.isFinite(Number(data.totalCount))
        ? Number(data.totalCount)
        : articles.value.length
    } catch (e) {
      ElMessage.error(e.userMessage || '获取文章列表失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchArticle(articleId) {
    loading.value = true
    try {
      // Use admin listing to find the article (admin detail not yet exposed in a separate GET endpoint)
      // We fetch via admin list with keyword search for now
      const res = await http.get('/admin/articles', {
        params: { keyword: articleId, limit: 1 }
      })
      // For fetching by ID, we query the admin list and find by articleId
      // A dedicated admin GET /admin/articles/{id} endpoint would be ideal,
      // but we use a workaround: store it as current when loading list
      currentArticle.value = res.data?.items?.[0] || null
    } catch (e) {
      ElMessage.error(e.userMessage || '获取文章详情失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function createArticle(data) {
    loading.value = true
    try {
      const res = await http.post('/admin/articles', data)
      ElMessage.success('文章创建成功')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '创建文章失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateArticle(articleId, data) {
    loading.value = true
    try {
      const res = await http.put(`/admin/articles/${articleId}`, data)
      ElMessage.success('文章更新成功')
      // Refresh current article
      currentArticle.value = { ...currentArticle.value, ...res.data, version: (currentArticle.value?.version || 0) + 1 }
      return res.data
    } catch (e) {
      if (e.response?.status === 409) {
        ElMessage.error('版本冲突：文章已被其他用户修改，请刷新后重试')
      } else {
        ElMessage.error(e.userMessage || '更新文章失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function publishArticle(articleId) {
    loading.value = true
    try {
      const res = await http.post(`/admin/articles/${articleId}/publish`)
      ElMessage.success('文章已发布')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '发布文章失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function unpublishArticle(articleId) {
    loading.value = true
    try {
      const res = await http.post(`/admin/articles/${articleId}/unpublish`)
      ElMessage.success('文章已下架')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '下架文章失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteArticle(articleId) {
    loading.value = true
    try {
      const res = await http.delete(`/admin/articles/${articleId}`)
      ElMessage.success('文章及其评论已删除')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '删除文章失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Helper to get status label
  function getStatusLabel(status) {
    const labels = {
      draft: '草稿',
      published: '已发布',
      unpublished: '已下架',
    }
    return labels[status] || status
  }

  // Helper to get status type (for Element Plus tag)
  function getStatusType(status) {
    const types = {
      draft: 'info',
      published: 'success',
      unpublished: 'warning',
    }
    return types[status] || 'info'
  }

  return {
    // State
    articles,
    currentArticle,
    loading,
    currentPage,
    pageSize,
    totalCount,
    filterStatus,
    filterCategory,
    filterKeyword,
    // Actions
    fetchArticles,
    fetchArticle,
    createArticle,
    updateArticle,
    publishArticle,
    unpublishArticle,
    deleteArticle,
    // Helpers
    getStatusLabel,
    getStatusType,
  }
})
