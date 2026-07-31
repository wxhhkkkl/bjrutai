import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useBindingStore = defineStore('binding', () => {
  // State
  const bindings = ref([])
  const currentBinding = ref(null)
  const loading = ref(false)
  const nextCursor = ref(null)
  const hasMore = ref(false)
  const totalCount = ref(0)
  const summary = ref({
    totalBindings: 0,
    activeBindings: 0,
    pendingRequests: 0,
    rejectedRequests: 0,
    expiredRequests: 0,
    lastBindingAt: null,
  })
  const selectablePromoters = ref([])

  // Filter state
  const filterStatus = ref('')
  const filterKeyword = ref('')

  // Getters
  const boundCount = computed(() => bindings.value.filter(b => b.status === 'bound').length)
  const abnormalCount = computed(() => bindings.value.filter(b => b.status === 'abnormal' || b.status === 'no_consume').length)

  // Status labels
  function getStatusLabel(status) {
    const labels = {
      pending_match: '等待匹配',
      matching: '匹配中',
      bound: '已绑定',
      no_consume: '无消费记录',
      retrying: '重试中',
      manual_review: '人工审核',
      abnormal: '异常',
      unbound: '已解绑',
      transferred: '已转移',
    }
    return labels[status] || status
  }

  function getStatusType(status) {
    const types = {
      pending_match: 'info',
      matching: 'warning',
      bound: 'success',
      no_consume: 'info',
      retrying: 'warning',
      manual_review: 'warning',
      abnormal: 'danger',
      unbound: 'info',
      transferred: 'info',
    }
    return types[status] || 'info'
  }

  // Actions -- Fetch bindings
  async function fetchBindings({ status, keyword, cursor, limit } = {}) {
    loading.value = true
    try {
      const params = {}
      if (status) params.status = status
      if (keyword) params.keyword = keyword
      if (cursor) params.cursor = cursor
      if (limit) params.limit = limit

      const res = await http.get('/binding-requests', { params })
      const data = res.data

      if (cursor) {
        bindings.value = [...bindings.value, ...data.items]
      } else {
        bindings.value = data.items
      }

      nextCursor.value = data.nextCursor
      hasMore.value = data.hasMore
      totalCount.value = data.totalCount || bindings.value.length
    } catch (e) {
      ElMessage.error(e.userMessage || '获取绑定列表失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Fetch detail
  async function fetchBindingDetail(requestId) {
    loading.value = true
    try {
      const res = await http.get(`/binding-requests/${requestId}`)
      currentBinding.value = res.data
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取绑定详情失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Fetch summary
  async function fetchBindingSummary() {
    try {
      const res = await http.get('/binding-summary')
      summary.value = res.data
    } catch (e) {
      // Swallow — summary is non-critical
    }
  }

  // Fetch selectable promoters
  async function fetchSelectablePromoters({ keyword, cursor, limit } = {}) {
    try {
      const params = {}
      if (keyword) params.keyword = keyword
      if (cursor) params.cursor = cursor
      if (limit) params.limit = limit

      const res = await http.get('/promoters/selectable', { params })
      selectablePromoters.value = res.data.items || []
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取推广员列表失败')
      throw e
    }
  }

  // Submit binding request
  async function submitBinding(data) {
    loading.value = true
    try {
      const idempotencyKey = `br_${Date.now()}_${Math.random().toString(36).slice(2)}`
      const res = await http.post('/binding-requests', data, {
        headers: { 'Idempotency-Key': idempotencyKey },
      })
      ElMessage.success('绑定请求已提交')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '提交绑定请求失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Retry binding request
  async function retryBinding(requestId) {
    loading.value = true
    try {
      const idempotencyKey = `retry_${Date.now()}_${Math.random().toString(36).slice(2)}`
      const res = await http.post(`/binding-requests/${requestId}/retry`, {}, {
        headers: { 'Idempotency-Key': idempotencyKey },
      })
      ElMessage.success('重试请求已提交')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '重试失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Update customer info
  async function updateCustomerInfo(requestId, data) {
    loading.value = true
    try {
      const idempotencyKey = `update_${Date.now()}_${Math.random().toString(36).slice(2)}`
      const res = await http.put(`/binding-requests/${requestId}/customer-info`, data, {
        headers: { 'Idempotency-Key': idempotencyKey },
      })
      ElMessage.success('客户信息已更新')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '更新失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Admin unbind
  async function unbindCustomer(requestId, reason) {
    loading.value = true
    try {
      const res = await http.post(`/admin/bindings/${requestId}/unbind`, { reason })
      ElMessage.success('已成功解绑')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '解绑失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Admin transfer
  async function transferCustomer(requestId, newPromoterId, reason) {
    loading.value = true
    try {
      const res = await http.post(`/admin/bindings/${requestId}/transfer`, {
        newPromoterId,
        reason,
      })
      ElMessage.success('已成功转移')
      return res.data
    } catch (e) {
      ElMessage.error(e.userMessage || '转移失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Reset state
  function resetState() {
    bindings.value = []
    currentBinding.value = null
    nextCursor.value = null
    hasMore.value = false
    totalCount.value = 0
    selectablePromoters.value = []
    filterStatus.value = ''
    filterKeyword.value = ''
  }

  return {
    // State
    bindings,
    currentBinding,
    loading,
    nextCursor,
    hasMore,
    totalCount,
    summary,
    selectablePromoters,
    filterStatus,
    filterKeyword,
    // Getters
    boundCount,
    abnormalCount,
    getStatusLabel,
    getStatusType,
    // Actions
    fetchBindings,
    fetchBindingDetail,
    fetchBindingSummary,
    fetchSelectablePromoters,
    submitBinding,
    retryBinding,
    updateCustomerInfo,
    unbindCustomer,
    transferCustomer,
    resetState,
  }
})
