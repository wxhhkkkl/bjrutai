import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const usePromotionStore = defineStore('promotion', () => {
  // State
  const promotionCode = ref(null)
  const statistics = ref(null)
  const poster = ref(null)
  const loading = ref(false)

  // Status helpers
  function getStatusLabel(status) {
    const labels = {
      available: '可用',
      disabled: '已禁用',
      expired: '已过期',
    }
    return labels[status] || status
  }

  function getStatusType(status) {
    const types = {
      available: 'success',
      disabled: 'warning',
      expired: 'info',
    }
    return types[status] || 'info'
  }

  // Actions
  async function fetchPromotionCode() {
    loading.value = true
    try {
      const res = await http.get('/promotion-code')
      promotionCode.value = res.data.data
      return promotionCode.value
    } catch (e) {
      if (e.response?.status === 403) {
        ElMessage.warning('请先完成资质认证后再获取推广码')
      } else {
        ElMessage.error(e.userMessage || '获取推广码失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function refreshCode() {
    loading.value = true
    try {
      const res = await http.post('/promotion-code/refresh')
      const result = res.data.data
      promotionCode.value = result
      ElMessage.success('推广码已刷新')
      return result
    } catch (e) {
      if (e.response?.status === 403) {
        ElMessage.warning('请先完成资质认证后再刷新推广码')
      } else {
        ElMessage.error(e.userMessage || '刷新推广码失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchStatistics(period = '30d') {
    loading.value = true
    try {
      const res = await http.get('/promotion-code/statistics', {
        params: { period },
      })
      statistics.value = res.data.data
      return statistics.value
    } catch (e) {
      if (e.response?.status === 403) {
        ElMessage.warning('请先完成资质认证后再查看统计数据')
      } else {
        ElMessage.error(e.userMessage || '获取统计数据失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchPoster() {
    loading.value = true
    try {
      const res = await http.get('/promotion-code/poster')
      poster.value = res.data.data
      return poster.value
    } catch (e) {
      if (e.response?.status === 403) {
        ElMessage.warning('请先完成资质认证后再获取海报')
      } else {
        ElMessage.error(e.userMessage || '获取海报失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  // Computed-like getters
  function getConversionRate() {
    if (!statistics.value) return 0
    const scan = statistics.value.scanCount || 0
    const bind = statistics.value.bindCount || 0
    return scan > 0 ? ((bind / scan) * 100).toFixed(1) + '%' : '0%'
  }

  function hasActiveCode() {
    return promotionCode.value && promotionCode.value.status === 'available'
  }

  return {
    // State
    promotionCode,
    statistics,
    poster,
    loading,
    // Status helpers
    getStatusLabel,
    getStatusType,
    // Actions
    fetchPromotionCode,
    refreshCode,
    fetchStatistics,
    fetchPoster,
    // Computed
    getConversionRate,
    hasActiveCode,
  }
})
