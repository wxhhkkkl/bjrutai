import { unref, watch } from 'vue'
import { ElMessage } from 'element-plus'

export function useMallToast(source, type = 'error') {
  return watch(
    source,
    (message) => {
      if (!message) return
      const messageType = typeof type === 'function' ? type() : unref(type)
      ElMessage({
        type: messageType,
        message: String(message),
        duration: messageType === 'warning' ? 6000 : 4000,
        grouping: true,
      })
    },
    { flush: 'sync' }
  )
}
