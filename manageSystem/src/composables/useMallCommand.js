import { computed, ref } from 'vue'
import { useMallToast } from '@/composables/useMallToast'

export function commandKey() {
  return crypto.randomUUID()
}

// An unknown result must replay the original intent, never a changed form.
export function useMallCommand() {
  const busy = ref(false)
  const error = ref('')
  useMallToast(error)
  const intent = ref(null)
  const pending = computed(() => intent.value !== null)
  async function execute() {
    if (busy.value || !intent.value) return null
    busy.value = true
    error.value = ''
    try {
      const result = await intent.value.send(
        intent.value.body,
        intent.value.key
      )
      intent.value = null
      return result
    } catch (failure) {
      const status = failure.response?.status
      const message = failure.userMessage || failure.message || '操作失败'
      const definite =
        status >= 400 &&
        status < 500 &&
        status !== 408 &&
        !String(message).includes('处理中')
      if (definite) intent.value = null
      error.value = `${message}${status === 409 ? '；请重新加载最新数据。' : ''}`
      if (!definite) error.value += '；结果未确认，请重试原操作。'
      return null
    } finally {
      busy.value = false
    }
  }
  async function run(send, body) {
    if (intent.value) return null
    intent.value = {
      send,
      body: JSON.parse(JSON.stringify(body)),
      key: commandKey(),
    }
    return execute()
  }
  return { busy, error, pending, run, retry: execute }
}
