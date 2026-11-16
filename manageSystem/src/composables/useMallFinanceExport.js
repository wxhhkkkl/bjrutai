import { computed, onScopeDispose, ref } from 'vue'
import { useMallToast } from '@/composables/useMallToast'
import {
  getAdminMallFinanceExport,
  getAdminMallFinanceExportFile,
} from '@/api/mall-finance'

const EXPORTS_KEY = 'mall_finance_exports_v1'

function readSavedExports() {
  try {
    return JSON.parse(sessionStorage.getItem(EXPORTS_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveExport(kind, value) {
  try {
    const saved = readSavedExports()
    saved[kind] = value
    sessionStorage.setItem(EXPORTS_KEY, JSON.stringify(saved))
  } catch {
    // The export remains usable for the current page even when storage is blocked.
  }
}

const statusLabels = {
  pending: '导出排队中',
  running: '正在生成导出',
  failed: '导出失败',
  completed: '导出文件已就绪',
  manual: '导出需要人工处理',
}

const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 60

export function useMallFinanceExport(kind, submit, actorId) {
  const storageScope = `${String(actorId || 'unknown')}:${kind}`
  const exportIntent = ref(null)
  const exportResult = ref(null)
  const exportBusy = ref(false)
  const exportError = ref('')
  const exportNotice = ref('')
  let pollTimer = null
  let pollAttempts = 0
  useMallToast(exportError)
  useMallToast(exportNotice, 'success')
  const exportStatusLabel = computed(
    () => statusLabels[exportResult.value?.status] || ''
  )

  function persist() {
    if (!exportIntent.value) return
    saveExport(storageScope, {
      intent: exportIntent.value,
      result: exportResult.value,
    })
  }

  function stopPolling() {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = null
  }

  function schedulePoll() {
    const requestId = exportResult.value?.requestId
    if (!requestId || pollAttempts >= POLL_MAX_ATTEMPTS) return
    pollTimer = setTimeout(async () => {
      pollTimer = null
      if (exportResult.value?.requestId !== requestId) return
      pollAttempts += 1
      const result = await refreshExport()
      if (result?.status === 'completed') {
        await downloadExport()
        return
      }
      if (!result && exportError.value) return
      if (result?.status === 'failed' || result?.status === 'manual') return
      schedulePoll()
    }, POLL_INTERVAL_MS)
  }

  function startPolling() {
    stopPolling()
    pollAttempts = 0
    schedulePoll()
  }

  async function submitIntent(reclaimed = false) {
    if (!exportIntent.value || exportBusy.value) return null
    stopPolling()
    exportBusy.value = true
    exportError.value = ''
    exportNotice.value = ''
    try {
      exportResult.value = await submit(
        exportIntent.value.payload,
        exportIntent.value.idempotencyKey
      )
      persist()
      if (reclaimed) exportNotice.value = '导出已重新领取'
      if (exportResult.value?.status === 'completed') {
        await downloadExport()
      } else if (exportResult.value?.status !== 'failed') {
        startPolling()
      }
      return exportResult.value
    } catch (failure) {
      exportError.value =
        failure.userMessage || failure.message || '资金导出请求失败'
      return null
    } finally {
      exportBusy.value = false
    }
  }

  async function exportFiltered(payload) {
    exportIntent.value = {
      payload: structuredClone(payload),
      idempotencyKey: crypto.randomUUID(),
    }
    exportResult.value = null
    persist()
    return submitIntent()
  }

  async function refreshExport() {
    const requestId = exportResult.value?.requestId
    if (!requestId || exportBusy.value) return null
    exportBusy.value = true
    exportError.value = ''
    try {
      exportResult.value = await getAdminMallFinanceExport(requestId)
      persist()
      return exportResult.value
    } catch (failure) {
      exportError.value =
        failure.userMessage || failure.message || '导出状态读取失败'
      return null
    } finally {
      exportBusy.value = false
    }
  }

  async function retryExport() {
    if (exportResult.value?.status !== 'failed') return null
    return submitIntent(true)
  }

  function dismissExport() {
    stopPolling()
    exportIntent.value = null
    exportResult.value = null
    try {
      const saved = readSavedExports()
      delete saved[storageScope]
      sessionStorage.setItem(EXPORTS_KEY, JSON.stringify(saved))
    } catch {
      // The export state is still cleared for the current page.
    }
  }

  async function downloadExport() {
    stopPolling()
    const fileId = exportResult.value?.fileId
    if (exportResult.value?.status !== 'completed' || !fileId) return
    exportError.value = ''
    try {
      const result = await getAdminMallFinanceExportFile(fileId)
      const target = new URL(result.accessUrl)
      if (target.protocol !== 'https:') throw new Error('导出文件访问地址不安全')
      const link = document.createElement('a')
      link.href = target.href
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      document.body.appendChild(link)
      link.click()
      link.remove()
      dismissExport()
    } catch (failure) {
      exportError.value =
        failure.userMessage || failure.message || '导出文件暂不可访问'
    }
  }

  async function restoreExport() {
    const saved = readSavedExports()[storageScope]
    if (!saved?.intent?.idempotencyKey || !saved?.result?.requestId) return
    exportIntent.value = saved.intent
    exportResult.value = saved.result
    await refreshExport()
  }

  onScopeDispose(stopPolling)

  return {
    exportIntent,
    exportResult,
    exportBusy,
    exportError,
    exportNotice,
    exportStatusLabel,
    exportFiltered,
    refreshExport,
    retryExport,
    downloadExport,
    restoreExport,
  }
}
