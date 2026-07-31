import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useContributionsStore = defineStore('contributions', () => {
  // State
  const overview = ref(null)
  const trend = ref(null)
  const composition = ref(null)
  const items = ref([])
  const nextCursor = ref(null)
  const hasMore = ref(false)
  const detail = ref(null)
  const teamSummary = ref(null)
  const drillDownData = ref(null)
  const loading = ref(false)
  const filters = ref({
    month: '',
    status: '',
    category: '',
    pageSize: 20,
  })

  // Category labels
  const categoryLabels = {
    binding: '绑定贡献',
    service: '服务贡献',
    followup: '跟进贡献',
    bill: '消费贡献',
    adjustment: '调整贡献',
  }

  const statusLabels = {
    pending: '待确认',
    confirmed: '已确认',
    settled: '已结算',
    reversed: '已冲正',
    cancelled: '已取消',
  }

  const statusTypes = {
    pending: 'warning',
    confirmed: 'info',
    settled: 'success',
    reversed: 'danger',
    cancelled: 'info',
  }

  // Actions
  async function fetchOverview(month) {
    loading.value = true
    try {
      const res = await http.get('/contributions/overview', { params: { month } })
      overview.value = res.data.data
      return overview.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取贡献概览失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchTrend(period = '6m') {
    loading.value = true
    try {
      const res = await http.get('/contributions/trend', { params: { period } })
      trend.value = res.data.data
      return trend.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取趋势数据失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchComposition(month) {
    loading.value = true
    try {
      const res = await http.get('/contributions/composition', { params: { month } })
      composition.value = res.data.data
      return composition.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取构成分析失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchList(params = {}) {
    loading.value = true
    try {
      const query = { ...filters.value, ...params }
      const res = await http.get('/contributions', { params: query })
      const data = res.data.data
      items.value = data.items || []
      nextCursor.value = data.nextCursor
      hasMore.value = data.hasMore
      return data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取贡献列表失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value) return
    try {
      const query = { ...filters.value, cursor: nextCursor.value }
      const res = await http.get('/contributions', { params: query })
      const data = res.data.data
      items.value = [...items.value, ...(data.items || [])]
      nextCursor.value = data.nextCursor
      hasMore.value = data.hasMore
      return data
    } catch (e) {
      ElMessage.error(e.userMessage || '加载更多失败')
      throw e
    }
  }

  async function fetchDetail(id) {
    loading.value = true
    try {
      const res = await http.get(`/contributions/${id}`)
      detail.value = res.data.data
      return detail.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取贡献详情失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchTeamSummary(month) {
    loading.value = true
    try {
      const res = await http.get('/team/contributions', { params: { month } })
      teamSummary.value = res.data.data
      return teamSummary.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取团队贡献失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function drillDown(promoterId, month) {
    loading.value = true
    try {
      const res = await http.get(`/team/contributions/${promoterId}`, { params: { month } })
      drillDownData.value = res.data.data
      return drillDownData.value
    } catch (e) {
      if (e.response?.status === 403) {
        ElMessage.error('无权查看该推广员的团队数据')
      } else {
        ElMessage.error(e.userMessage || '下钻失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function settleMonth(month) {
    loading.value = true
    try {
      const res = await http.post('/admin/contributions/settle', { month })
      ElMessage.success(`月份 ${month} 结算完成，共处理 ${res.data.data?.settledCount || 0} 条记录`)
      return res.data.data
    } catch (e) {
      ElMessage.error(e.userMessage || '结算失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  function getCategoryLabel(cat) {
    return categoryLabels[cat] || cat
  }

  function getStatusLabel(status) {
    return statusLabels[status] || status
  }

  function getStatusType(status) {
    return statusTypes[status] || 'info'
  }

  function setFilters(newFilters) {
    filters.value = { ...filters.value, ...newFilters }
  }

  return {
    // State
    overview,
    trend,
    composition,
    items,
    nextCursor,
    hasMore,
    detail,
    teamSummary,
    drillDownData,
    loading,
    filters,
    // Labels
    categoryLabels,
    statusLabels,
    statusTypes,
    // Actions
    fetchOverview,
    fetchTrend,
    fetchComposition,
    fetchList,
    loadMore,
    fetchDetail,
    fetchTeamSummary,
    drillDown,
    settleMonth,
    // Helpers
    getCategoryLabel,
    getStatusLabel,
    getStatusType,
    setFilters,
  }
})
