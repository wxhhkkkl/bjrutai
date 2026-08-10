const { ApiError, normalizeApiError } = require('../models/api-error')

const DEFAULT_TIMEOUT = 10000

function cleanBase(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function validatePath(path) {
  if (!/^\/api\/v1(?:\/|$)/.test(String(path || ''))) {
    throw new ApiError({
      kind: 'VALIDATION',
      message: '请求路径必须位于 /api/v1'
    })
  }
}

function businessHttpStatus(code, fallback) {
  const numeric = Number(code)
  if (numeric >= 40000 && numeric <= 59999) return Math.floor(numeric / 100)
  return fallback
}

function isEnvelope(body) {
  return body
    && typeof body === 'object'
    && typeof body.code === 'number'
    && typeof body.message === 'string'
    && Object.hasOwn(body, 'data')
    && typeof body.requestId === 'string'
    && typeof body.serverTime === 'string'
}

function createRequestClient(options = {}) {
  const getApiBase = options.getApiBase || (() => '')
  const getAccessToken = options.getAccessToken || (() => '')
  const requestAdapter = options.requestAdapter || ((requestOptions) => wx.request(requestOptions))
  const defaultTimeout = options.timeoutMs || DEFAULT_TIMEOUT
  const refreshAccessToken = options.refreshAccessToken
  const onAuthExpired = options.onAuthExpired
  let refreshPromise = null
  let authExpiredNotified = false

  function notifyAuthExpired() {
    if (authExpiredNotified) return
    authExpiredNotified = true
    if (typeof onAuthExpired === 'function') onAuthExpired()
  }

  function runRefresh() {
    if (refreshPromise) return refreshPromise
    if (typeof refreshAccessToken !== 'function') {
      notifyAuthExpired()
      return Promise.reject(new ApiError({ kind: 'AUTH' }))
    }

    refreshPromise = Promise.resolve()
      .then(() => refreshAccessToken())
      .then((result) => {
        authExpiredNotified = false
        return result
      })
      .catch((error) => {
        notifyAuthExpired()
        throw normalizeApiError(error)
      })
      .finally(() => {
        refreshPromise = null
      })

    return refreshPromise
  }

  function send(path, requestOptions, canRefresh) {
    let apiBase
    try {
      validatePath(path)
      apiBase = cleanBase(getApiBase())
      if (!apiBase) {
        throw new ApiError({
          kind: 'SERVER',
          message: 'API 地址未配置',
          retryable: false
        })
      }
    } catch (error) {
      return Promise.reject(normalizeApiError(error))
    }

    const auth = requestOptions.auth !== false
    const token = auth ? getAccessToken() : ''
    const header = Object.assign({}, requestOptions.header)
    if (token) header.Authorization = `Bearer ${token}`
    if (requestOptions.idempotencyKey) {
      header['Idempotency-Key'] = requestOptions.idempotencyKey
    }

    return new Promise((resolve, reject) => {
      const finishWithError = (error) => {
        const normalized = normalizeApiError(error)
        const shouldRefresh = normalized.kind === 'AUTH'
          && auth
          && canRefresh
          && requestOptions.retryAfterRefresh !== false

        if (!shouldRefresh) {
          reject(normalized)
          return
        }

        runRefresh()
          .then(() => send(path, requestOptions, false))
          .then(resolve, reject)
      }

      const adapterOptions = {
        url: `${apiBase}${path}`,
        method: requestOptions.method || 'GET',
        data: requestOptions.data,
        header,
        timeout: requestOptions.timeoutMs || defaultTimeout,
        success(response) {
          const statusCode = Number(response && response.statusCode) || 0
          const body = response && response.data

          const hasBusinessError = body
            && typeof body === 'object'
            && typeof body.code === 'number'
            && body.code !== 0

          if (statusCode < 200 || statusCode >= 300 || hasBusinessError) {
            finishWithError({
              httpStatus: businessHttpStatus(body && body.code, statusCode),
              body
            })
            return
          }

          if (!isEnvelope(body)) {
            finishWithError({
              malformed: true,
              httpStatus: statusCode,
              requestId: body && body.requestId
            })
            return
          }

          resolve(body.data)
        },
        fail(error) {
          finishWithError({ errMsg: error && error.errMsg })
        }
      }

      try {
        requestAdapter(adapterOptions)
      } catch (error) {
        finishWithError({ errMsg: error && error.message })
      }
    })
  }

  function request(path, requestOptions = {}) {
    return send(path, requestOptions, true)
  }

  return { request }
}

let authHandlers = {}

function setAuthHandlers(handlers = {}) {
  authHandlers = handlers
}

const defaultClient = createRequestClient({
  getApiBase() {
    if (typeof getApp === 'undefined') return ''
    const app = getApp()
    return app && app.globalData ? app.globalData.apiBase : ''
  },
  getAccessToken() {
    return require('./session-service').getAccessToken()
  },
  refreshAccessToken() {
    return authHandlers.refreshAccessToken
      ? authHandlers.refreshAccessToken()
      : Promise.reject(new ApiError({ kind: 'AUTH' }))
  },
  onAuthExpired() {
    if (authHandlers.onAuthExpired) authHandlers.onAuthExpired()
  }
})

module.exports = {
  DEFAULT_TIMEOUT,
  createRequestClient,
  request: defaultClient.request,
  setAuthHandlers
}
