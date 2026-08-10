const test = require('node:test')
const assert = require('node:assert/strict')

const { createRequestClient } = require('../../services/request-service')

function authFailure(options) {
  options.success({
    statusCode: 401,
    data: { code: 40100, message: 'expired', requestId: 'expired' }
  })
}

test('concurrent 401 responses share one refresh and retry once with the new token', async () => {
  let token = 'old'
  let refreshCount = 0
  const attempts = {}
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test',
    getAccessToken: () => token,
    refreshAccessToken: async () => {
      refreshCount += 1
      await new Promise((resolve) => setTimeout(resolve, 5))
      token = 'new'
    },
    requestAdapter(options) {
      attempts[options.url] = (attempts[options.url] || 0) + 1
      if (options.header.Authorization === 'Bearer old') {
        authFailure(options)
      } else {
        options.success({
          statusCode: 200,
          data: { code: 0, message: 'success', data: options.url, requestId: 'ok', serverTime: 't' }
        })
      }
      return { abort() {} }
    }
  })

  const result = await Promise.all([
    client.request('/api/v1/workbench'),
    client.request('/api/v1/me/account-summary')
  ])

  assert.equal(refreshCount, 1)
  assert.equal(result.length, 2)
  assert.equal(attempts['https://api.example.test/api/v1/workbench'], 2)
})

test('refresh failure rejects all requests and notifies auth expiry once', async () => {
  let refreshCount = 0
  let expiredCount = 0
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test',
    getAccessToken: () => 'old',
    refreshAccessToken: async () => {
      refreshCount += 1
      await new Promise((resolve) => setTimeout(resolve, 5))
      throw new Error('refresh rejected')
    },
    onAuthExpired: () => {
      expiredCount += 1
    },
    requestAdapter(options) {
      authFailure(options)
      return { abort() {} }
    }
  })

  const results = await Promise.allSettled([
    client.request('/api/v1/workbench'),
    client.request('/api/v1/customers')
  ])

  assert.equal(refreshCount, 1)
  assert.equal(expiredCount, 1)
  assert.equal(results.every((item) => item.status === 'rejected'), true)
})

test('a retried request does not enter another refresh loop', async () => {
  let refreshCount = 0
  const client = createRequestClient({
    getApiBase: () => 'https://api.example.test',
    getAccessToken: () => 'token',
    refreshAccessToken: async () => { refreshCount += 1 },
    requestAdapter(options) {
      authFailure(options)
      return { abort() {} }
    }
  })

  await assert.rejects(client.request('/api/v1/workbench'))
  assert.equal(refreshCount, 1)
})
