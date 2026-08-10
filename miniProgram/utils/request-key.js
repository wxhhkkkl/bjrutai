function defaultKeyFactory() {
  const random = Math.random().toString(36).slice(2)
  return `${Date.now().toString(36)}-${random}`
}

function createRequestKeyManager(keyFactory = defaultKeyFactory) {
  const entries = new Map()

  function begin(flowId) {
    const current = entries.get(flowId)
    if (current && (current.state === 'submitting' || current.state === 'unknown')) {
      return current.key
    }

    const key = keyFactory()
    entries.set(flowId, { key, state: 'submitting' })
    return key
  }

  function setState(flowId, state) {
    const current = entries.get(flowId)
    if (current) current.state = state
  }

  return {
    begin,
    markUnknown(flowId) { setState(flowId, 'unknown') },
    markSucceeded(flowId) { setState(flowId, 'succeeded') },
    markFailed(flowId) { setState(flowId, 'failed') },
    restart(flowId) { entries.delete(flowId) },
    get(flowId) { return entries.get(flowId) || null }
  }
}

module.exports = {
  createRequestKeyManager
}
