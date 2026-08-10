const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadService() {
  const servicePath = path.resolve(__dirname, '../../services/customer-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const originalRequest = require.cache[requestPath]
  const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: {
      request(apiPath, options = {}) {
        calls.push({ path: apiPath, options })
        return Promise.resolve({})
      }
    }
  }
  return {
    service: require(servicePath),
    calls,
    restore() {
      delete require.cache[servicePath]
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

test('customer service uses exact list/detail/analysis routes and PATCH fields', async () => {
  const fixture = loadService()
  try {
    await fixture.service.listCustomers({
      status: 'bound', keyword: '王', cursor: '20', pageSize: 10, userId: 'u1'
    })
    await fixture.service.getCustomer('c1', 'u1')
    await fixture.service.patchCustomer('c1', {
      name: '新姓名', phone: '13800000000', note: '备注', familyPhone: '13900000000',
      changeReason: '客户确认', version: 2
    })
    await fixture.service.getCustomerAnalysis('30d', 'u1')

    assert.deepEqual(fixture.calls.map(({ path, options }) => [
      path, options.method || 'GET', options.data
    ]), [
      ['/api/v1/customers', 'GET', {
        status: 'bound', keyword: '王', cursor: '20', pageSize: 10
      }],
      ['/api/v1/customers/c1', 'GET', undefined],
      ['/api/v1/customers/c1', 'PATCH', {
        name: '新姓名', phone: '13800000000', note: '备注', familyPhone: '13900000000',
        changeReason: '客户确认'
      }],
      ['/api/v1/customer-analysis', 'GET', { period: '30d' }]
    ])
  } finally {
    fixture.restore()
  }
})

test('customer list accepts only current-user scope and does not expose blocked subresources', () => {
  const fixture = loadService()
  try {
    assert.equal(typeof fixture.service.getServiceRecords, 'undefined')
    assert.equal(typeof fixture.service.getFollowups, 'undefined')
  } finally {
    fixture.restore()
  }
})
