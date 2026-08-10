const DEFAULT_MESSAGES = {
  NETWORK: '网络异常，请检查连接后重试',
  TIMEOUT: '请求超时，请稍后重试',
  AUTH: '登录已过期，请重新登录',
  FORBIDDEN: '暂无权限访问',
  NOT_FOUND: '请求的数据不存在',
  CONFLICT: '数据已发生变化，请刷新后重试',
  VALIDATION: '提交内容有误，请检查后重试',
  SERVER: '服务暂时不可用，请稍后重试',
  MALFORMED: '服务响应异常，请稍后重试'
}

class ApiError extends Error {
  constructor(options = {}) {
    const kind = options.kind || 'SERVER'
    super(options.message || DEFAULT_MESSAGES[kind] || DEFAULT_MESSAGES.SERVER)
    this.name = 'ApiError'
    this.kind = kind
    this.code = options.code === undefined ? null : options.code
    this.requestId = options.requestId || ''
    this.retryable = options.retryable === undefined
      ? kind === 'NETWORK' || kind === 'TIMEOUT' || kind === 'SERVER' || kind === 'MALFORMED'
      : options.retryable === true
    this.httpStatus = options.httpStatus || null
  }
}

function kindFromStatus(status) {
  if (status === 401) return 'AUTH'
  if (status === 403) return 'FORBIDDEN'
  if (status === 404) return 'NOT_FOUND'
  if (status === 409) return 'CONFLICT'
  if (status === 400 || status === 422) return 'VALIDATION'
  return 'SERVER'
}

function normalizeApiError(value = {}) {
  if (value instanceof ApiError) return value

  if (value.malformed) {
    return new ApiError({
      kind: 'MALFORMED',
      requestId: value.requestId
    })
  }

  const errMsg = String(value.errMsg || value.message || '')
  if (/timeout/i.test(errMsg)) return new ApiError({ kind: 'TIMEOUT' })
  if (!value.httpStatus && errMsg) return new ApiError({ kind: 'NETWORK' })

  const body = value.body && typeof value.body === 'object' ? value.body : {}
  const httpStatus = Number(value.httpStatus) || null
  const kind = kindFromStatus(httpStatus)

  return new ApiError({
    kind,
    code: body.code,
    message: body.message || DEFAULT_MESSAGES[kind],
    requestId: body.requestId || value.requestId,
    httpStatus
  })
}

module.exports = {
  ApiError,
  normalizeApiError
}
