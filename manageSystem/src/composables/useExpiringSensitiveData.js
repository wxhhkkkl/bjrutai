import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export function useExpiringSensitiveData(selectFields) {
  const value = ref(null)
  const deadline = ref(0)
  const now = ref(Date.now())
  let countdownTimer = null
  let expiryTimer = null
  let generation = 0

  const secondsRemaining = computed(() =>
    deadline.value > now.value
      ? Math.ceil((deadline.value - now.value) / 1000)
      : 0
  )

  function clear() {
    generation += 1
    if (countdownTimer) clearInterval(countdownTimer)
    if (expiryTimer) clearTimeout(expiryTimer)
    countdownTimer = null
    expiryTimer = null
    value.value = null
    deadline.value = 0
    now.value = Date.now()
  }

  function beginRequest() {
    clear()
    return generation
  }

  function isCurrent(requestGeneration) {
    return requestGeneration === generation
  }

  function show(payload, requestGeneration) {
    if (!isCurrent(requestGeneration)) return false
    const expiresAt = Date.parse(payload?.expiresAt)
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return false

    value.value = selectFields(payload)
    deadline.value = expiresAt
    now.value = Date.now()
    countdownTimer = setInterval(() => {
      now.value = Date.now()
    }, 1000)
    expiryTimer = setTimeout(clear, Math.max(0, expiresAt - Date.now()))
    return true
  }

  function clearWhenHidden() {
    if (document.visibilityState === 'hidden') clear()
  }

  onMounted(() => document.addEventListener('visibilitychange', clearWhenHidden))
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', clearWhenHidden)
    clear()
  })

  return { value, secondsRemaining, beginRequest, isCurrent, show, clear }
}
