import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useSharingStore = defineStore('sharing', () => {
  // State
  const rules = ref([])
  const coefficient = ref(null)
  const loading = ref(false)

  // Labels
  const ruleTypeLabels = {
    fixed_ratio: '固定比例',
    fixed_amount: '固定金额',
    tiered: '阶梯分成',
  }

  const baseLabels = {
    paid_amount: '已付金额',
    total_amount: '订单总金额',
  }

  const statusLabels = {
    active: '生效中',
    inactive: '已停用',
    expired: '已过期',
  }

  // Actions
  async function fetchRules(filters = {}) {
    loading.value = true
    try {
      const params = {}
      if (filters.level) params.level = filters.level
      if (filters.status) params.status = filters.status
      const res = await http.get('/admin/sharing-rules', { params })
      rules.value = res.data.data?.items || res.data.data || []
      return rules.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取分成规则失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function createRule(data) {
    loading.value = true
    try {
      const res = await http.post('/admin/sharing-rules', data)
      ElMessage.success('分成规则创建成功')
      await fetchRules()
      return res.data.data
    } catch (e) {
      ElMessage.error(e.userMessage || '创建分成规则失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateRule(id, data) {
    loading.value = true
    try {
      const res = await http.put(`/admin/sharing-rules/${id}`, data)
      ElMessage.success('分成规则更新成功')
      await fetchRules()
      return res.data.data
    } catch (e) {
      if (e.response?.status === 409) {
        ElMessage.error('版本冲突：规则已被他人修改，请刷新后重试')
      } else {
        ElMessage.error(e.userMessage || '更新分成规则失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deactivateRule(id) {
    loading.value = true
    try {
      const res = await http.post(`/admin/sharing-rules/${id}/deactivate`)
      ElMessage.success('分成规则已停用')
      await fetchRules()
      return res.data.data
    } catch (e) {
      ElMessage.error(e.userMessage || '停用分成规则失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchCoefficient() {
    try {
      const res = await http.get('/admin/sharing-rules/coefficient')
      coefficient.value = res.data.data?.value ?? res.data.data
      return coefficient.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取分成系数失败')
      throw e
    }
  }

  async function updateCoefficient(value) {
    loading.value = true
    try {
      const res = await http.put('/admin/sharing-rules/coefficient', { value })
      coefficient.value = res.data.data?.value ?? res.data.data
      ElMessage.success('分成系数更新成功')
      return coefficient.value
    } catch (e) {
      ElMessage.error(e.userMessage || '更新分成系数失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  function getRuleTypeLabel(type) {
    return ruleTypeLabels[type] || type
  }

  function getBaseLabel(base) {
    return baseLabels[base] || base
  }

  function getStatusLabel(status) {
    return statusLabels[status] || status
  }

  function getStatusType(status) {
    const types = { active: 'success', inactive: 'warning', expired: 'info' }
    return types[status] || 'info'
  }

  return {
    // State
    rules,
    coefficient,
    loading,
    // Labels
    ruleTypeLabels,
    baseLabels,
    statusLabels,
    // Actions
    fetchRules,
    createRule,
    updateRule,
    deactivateRule,
    fetchCoefficient,
    updateCoefficient,
    // Helpers
    getRuleTypeLabel,
    getBaseLabel,
    getStatusLabel,
    getStatusType,
  }
})
