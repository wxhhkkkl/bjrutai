import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useSyncStore = defineStore('sync', () => {
  // State
  const status = ref({
    last_success: null,
    failure_count: 0,
    pending_retries: 0,
    is_polling: false,
    circuit_breaker_open: false,
    last_bind_user_poll: null,
    last_bill_sync: null,
  })
  const loading = ref(false)
  const retryingBindUser = ref(false)
  const retryingBill = ref(false)

  // Getters
  const lastPollTime = computed(() => {
    if (status.value.last_bind_user_poll) {
      return new Date(status.value.last_bind_user_poll).toLocaleString('zh-CN')
    }
    return '--'
  })

  const lastBillSyncTime = computed(() => {
    if (status.value.last_bill_sync) {
      return new Date(status.value.last_bill_sync).toLocaleString('zh-CN')
    }
    return '--'
  })

  const healthStatus = computed(() => {
    if (status.value.circuit_breaker_open) {
      return { type: 'danger', label: '异常' }
    }
    if (status.value.failure_count >= 3) {
      return { type: 'warning', label: '警告' }
    }
    if (status.value.is_polling) {
      return { type: 'success', label: '运行中' }
    }
    return { type: 'info', label: '待机' }
  })

  function formatTime(isoString) {
    if (!isoString) return '--'
    return new Date(isoString).toLocaleString('zh-CN')
  }

  // Actions
  async function fetchStatus() {
    loading.value = true
    try {
      const response = await http.get('/admin/sync/status')
      if (response.data && response.data.code === 0) {
        status.value = response.data.data
      }
    } catch (error) {
      ElMessage.error(error.userMessage || '获取同步状态失败')
    } finally {
      loading.value = false
    }
  }

  async function retryBindUser() {
    retryingBindUser.value = true
    try {
      const response = await http.post('/admin/sync/retry-binduser')
      if (response.data && response.data.code === 0) {
        ElMessage.success('绑定用户同步已触发')
        await fetchStatus()
      }
    } catch (error) {
      ElMessage.error(error.userMessage || '重试同步失败')
    } finally {
      retryingBindUser.value = false
    }
  }

  async function retryBill(userId) {
    retryingBill.value = true
    try {
      const response = await http.post(`/admin/sync/retry-bill/${userId}`)
      if (response.data && response.data.code === 0) {
        ElMessage.success(`用户 ${userId} 账单同步已触发`)
        await fetchStatus()
      }
    } catch (error) {
      ElMessage.error(error.userMessage || '重试账单同步失败')
    } finally {
      retryingBill.value = false
    }
  }

  return {
    status,
    loading,
    retryingBindUser,
    retryingBill,
    lastPollTime,
    lastBillSyncTime,
    healthStatus,
    formatTime,
    fetchStatus,
    retryBindUser,
    retryBill,
  }
})
