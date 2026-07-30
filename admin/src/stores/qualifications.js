import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useQualificationsStore = defineStore('qualifications', () => {
  // State
  const qualifications = ref([])
  const currentQualification = ref(null)
  const reviewList = ref([])
  const loading = ref(false)
  const reviews = ref([])

  // Status helpers
  function getStatusLabel(status) {
    const labels = {
      draft: '草稿',
      reviewing: '待审核',
      approved: '已通过',
      rejected: '已驳回',
      expiring: '即将过期',
      expired: '已过期',
    }
    return labels[status] || status
  }

  function getStatusType(status) {
    const types = {
      draft: 'info',
      reviewing: 'warning',
      approved: 'success',
      rejected: 'danger',
      expiring: 'warning',
      expired: 'info',
    }
    return types[status] || 'info'
  }

  // Actions
  async function fetchUploadToken(fileName, fileType, fileSize) {
    try {
      const res = await http.post('/qualification-files/upload-token', {
        fileName,
        fileType,
        fileSize,
      })
      return res.data.data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取上传凭证失败')
      throw e
    }
  }

  async function fetchCurrent() {
    loading.value = true
    try {
      const res = await http.get('/qualifications/current')
      const data = res.data.data
      qualifications.value = data.items || []
      return data
    } catch (e) {
      ElMessage.error(e.userMessage || '获取资质信息失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function submitQualification(data) {
    loading.value = true
    try {
      const res = await http.post('/qualifications', data)
      const result = res.data.data
      ElMessage.success('资质提交成功，等待审核')
      await fetchCurrent()
      return result
    } catch (e) {
      if (e.response?.status === 409) {
        ElMessage.error('已有待审核或已通过的资质记录')
      } else {
        ElMessage.error(e.userMessage || '提交资质失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateQualification(qualificationId, data) {
    loading.value = true
    try {
      const res = await http.put(`/qualifications/${qualificationId}`, data)
      const result = res.data.data
      ElMessage.success('资质已重新提交')
      await fetchCurrent()
      return result
    } catch (e) {
      if (e.response?.status === 409) {
        ElMessage.error('版本冲突：资质已被他人修改，请刷新后重试')
      } else {
        ElMessage.error(e.userMessage || '更新资质失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function saveDraft(data) {
    loading.value = true
    try {
      const res = await http.post('/qualifications/draft', data)
      const result = res.data.data
      ElMessage.success('草稿已保存')
      return result
    } catch (e) {
      if (e.response?.status === 409) {
        ElMessage.error('已有待审核或已通过的资质记录，无法保存草稿')
      } else {
        ElMessage.error(e.userMessage || '保存草稿失败')
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchReviews(qualificationId) {
    loading.value = true
    try {
      const res = await http.get(`/qualifications/${qualificationId}/reviews`)
      reviews.value = res.data.data.items || []
      return reviews.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取审核记录失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  // Admin actions
  async function fetchReviewList(status) {
    loading.value = true
    try {
      const params = {}
      if (status) params.status = status
      const res = await http.get('/admin/qualifications', { params })
      reviewList.value = res.data.data.items || []
      return reviewList.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取审核列表失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function reviewQualification(qualificationId, action, comment) {
    loading.value = true
    try {
      const res = await http.post(`/admin/qualifications/${qualificationId}/review`, {
        action,
        comment: comment || '',
      })
      const result = res.data.data
      const actionLabel = action === 'approve' ? '通过' : '驳回'
      ElMessage.success(`资质审核${actionLabel}`)
      await fetchReviewList()
      return result
    } catch (e) {
      ElMessage.error(e.userMessage || '审核操作失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    qualifications,
    currentQualification,
    reviewList,
    loading,
    reviews,
    // Status helpers
    getStatusLabel,
    getStatusType,
    // Actions
    fetchUploadToken,
    fetchCurrent,
    submitQualification,
    updateQualification,
    saveDraft,
    fetchReviews,
    fetchReviewList,
    reviewQualification,
  }
})
