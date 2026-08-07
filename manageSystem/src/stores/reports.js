import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

export const useReportsStore = defineStore('reports', () => {
  // State
  const reports = ref([])
  const currentReport = ref(null)
  const loading = ref(false)
  const generating = ref(false)

  // Dimension labels
  const dimensionLabels = {
    binding: '绑定汇总',
    revenue: '收入汇总',
    discount: '优惠汇总',
    allocation: '分配明细',
    performance: '绩效核算',
  }

  // Actions
  async function generateReport(startDate, endDate, dimensions) {
    generating.value = true
    try {
      const res = await http.post('/reports/generate', {
        startDate,
        endDate,
        dimensions,
      })
      ElMessage.success('报表生成成功')
      await fetchReports()
      return res.data.data
    } catch (e) {
      ElMessage.error(e.userMessage || '生成报表失败')
      throw e
    } finally {
      generating.value = false
    }
  }

  async function fetchReports() {
    loading.value = true
    try {
      const res = await http.get('/reports')
      reports.value = res.data.data?.items || []
      return reports.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取报表列表失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchReportDetail(reportId) {
    loading.value = true
    try {
      const res = await http.get(`/reports/${reportId}`)
      currentReport.value = res.data.data
      return currentReport.value
    } catch (e) {
      ElMessage.error(e.userMessage || '获取报表详情失败')
      throw e
    } finally {
      loading.value = false
    }
  }

  async function exportReport(reportId) {
    try {
      const response = await http.get(`/reports/${reportId}/export`, {
        responseType: 'blob',
      })
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `report-${reportId}.xlsx`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      ElMessage.success('报表下载成功')
    } catch (e) {
      ElMessage.error(e.userMessage || '导出报表失败')
      throw e
    }
  }

  function getDimensionLabel(dim) {
    return dimensionLabels[dim] || dim
  }

  return {
    // State
    reports,
    currentReport,
    loading,
    generating,
    // Labels
    dimensionLabels,
    // Actions
    generateReport,
    fetchReports,
    fetchReportDetail,
    exportReport,
    // Helpers
    getDimensionLabel,
  }
})
