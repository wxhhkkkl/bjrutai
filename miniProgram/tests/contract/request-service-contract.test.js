const test = require('node:test')
const assert = require('node:assert/strict')

const { createRequestClient } = require('../../services/request-service')

function successAdapter(response, calls) {
  return (options) => {
    calls.push(options)
    options.success(response)
    return { abort() {} }
  }
}

test('builds a versioned request with bearer, idempotency and unified data', async () => {
  const calls = []
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test/',
    getAccessToken: () => 'access-token',
    requestAdapter: successAdapter({
      statusCode: 200,
      data: {
        code: 0,
        message: 'success',
        data: { id: '1' },
        requestId: 'req-1',
        serverTime: '2026-08-08T00:00:00Z'
      }
    }, calls)
  })

  const data = await client.request('/api/v1/customers', {
    method: 'POST',
    data: { name: '测试客户' },
    idempotencyKey: 'idem-1'
  })

  assert.deepEqual(data, { id: '1' })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, 'https://api.example.test/api/v1/customers')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].header.Authorization, 'Bearer access-token')
  assert.equal(calls[0].header['Idempotency-Key'], 'idem-1')
  assert.equal(calls[0].timeout, 10000)
})

test('supports public requests without an authorization header', async () => {
  const calls = []
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test',
    getAccessToken: () => 'access-token',
    requestAdapter: successAdapter({
      statusCode: 200,
      data: { code: 0, message: 'success', data: null, requestId: 'r', serverTime: 't' }
    }, calls)
  })

  await client.request('/api/v1/auth/wechat-login', { auth: false })
  assert.equal(Object.hasOwn(calls[0].header, 'Authorization'), false)
})

test('rejects absolute URLs and paths outside api v1', async () => {
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test',
    requestAdapter() {
      throw new Error('must not run')
    }
  })

  await assert.rejects(client.request('https://evil.test/api/v1/data'), /\/api\/v1/)
  await assert.rejects(client.request('/customers'), /\/api\/v1/)
})
