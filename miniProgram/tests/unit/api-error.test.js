const test = require('node:test')
const assert = require('node:assert/strict')

const {
  ApiError,
  normalizeApiError
} = require('../../models/api-error')

test('normalizes business authentication and authorization errors', () => {
  const auth = normalizeApiError({
    httpStatus: 401,
    body: { code: 40100, message: '登录已过期', requestId: 'req-auth' }
  })
  const forbidden = normalizeApiError({
    httpStatus: 403,
    body: { code: 40300, message: '无权访问', requestId: 'req-denied' }
  })

  assert.ok(auth instanceof ApiError)
  assert.equal(auth.kind, 'AUTH')
  assert.equal(auth.code, 40100)
  assert.equal(auth.requestId, 'req-auth')
  assert.equal(auth.retryable, false)
  assert.equal(forbidden.kind, 'FORBIDDEN')
})

test('normalizes timeout network conflict validation and server errors', () => {
  assert.equal(normalizeApiError({ errMsg: 'request:fail timeout' }).kind, 'TIMEOUT')
  assert.equal(normalizeApiError({ errMsg: 'request:fail network' }).kind, 'NETWORK')
  assert.equal(normalizeApiError({ httpStatus: 409 }).kind, 'CONFLICT')
  assert.equal(normalizeApiError({ httpStatus: 422 }).kind, 'VALIDATION')
  assert.equal(normalizeApiError({ httpStatus: 503 }).kind, 'SERVER')
  assert.equal(normalizeApiError({ httpStatus: 404 }).kind, 'NOT_FOUND')
})

test('marks malformed responses without retaining sensitive payloads', () => {
  const error = normalizeApiError({
    malformed: true,
    body: {
      phone: '13812345678',
      accessToken: 'secret-token'
    }
  })

  assert.equal(error.kind, 'MALFORMED')
  assert.equal(error.retryable, true)
  assert.equal(Object.hasOwn(error, 'body'), false)
  assert.doesNotMatch(JSON.stringify(error), /13812345678|secret-token/)
})

test('keeps an existing ApiError unchanged', () => {
  const original = new ApiError({ kind: 'NETWORK', message: '网络异常' })
  assert.equal(normalizeApiError(original), original)
})

test('localizes known English backend messages for end users', () => {
  const error = normalizeApiError({
    httpStatus: 409,
    body: { code: 40022, message: 'You are already bound to this promoter', requestId: 'req-bound' }
  })
  assert.equal(error.message, '该拓展人已有绑定客户，不能重复绑定')
})
