const test = require('node:test')
const assert = require('node:assert/strict')

const { createRequestClient } = require('../../services/request-service')

function clientForResponse(response) {
  return createRequestClient({
    getApiBase: () => 'https://api.example.test',
    requestAdapter(options) {
      options.success(response)
      return { abort() {} }
    }
  })
}

test('rejects non-zero business codes with safe ApiError metadata', async () => {
  const client = clientForResponse({
    statusCode: 200,
    data: { code: 40901, message: '数据冲突', data: null, requestId: 'req-c' }
  })

  await assert.rejects(
    client.request('/api/v1/customers/1'),
    (error) => error.code === 40901 && error.requestId === 'req-c'
  )
})

test('rejects HTTP, timeout, network and malformed responses', async () => {
  const forbidden = clientForResponse({
    statusCode: 403,
    data: { code: 40300, message: '禁止访问', requestId: 'req-f' }
  })
  await assert.rejects(
    forbidden.request('/api/v1/customers/1'),
    (error) => error.kind === 'FORBIDDEN'
  )

  const malformed = clientForResponse({ statusCode: 200, data: { customer: 1 } })
  await assert.rejects(
    malformed.request('/api/v1/customers/1'),
    (error) => error.kind === 'MALFORMED'
  )

  for (const errMsg of ['request:fail timeout', 'request:fail network']) {
    const client = createRequestClient({
      getApiBase: () => 'https://api.example.test',
      requestAdapter(options) {
        options.fail({ errMsg, accessToken: 'must-not-leak' })
        return { abort() {} }
      }
    })
    await assert.rejects(
      client.request('/api/v1/customers'),
      (error) => !JSON.stringify(error).includes('must-not-leak')
    )
  }
})
