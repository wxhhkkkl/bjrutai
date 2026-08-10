const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadService() {
  const servicePath = path.resolve(__dirname, '../../services/workbench-service.js')
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
        return Promise.resolve({ endpoint: apiPath })
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

test('workbench service calls all five current-user endpoints with exact methods and query', async () => {
  const fixture = loadService()
  try {
    await fixture.service.getWorkbench('user-1')
    await fixture.service.getNotices('user-1')
    await fixture.service.getRecentBindings('user-1')
    await fixture.service.getContributionSummary('2026-08', 'user-1')
    await fixture.service.getAccountSummary('user-1')

    assert.deepEqual(fixture.calls.map(({ path, options }) => [
      path,
      options.method || 'GET',
      options.data
    ]), [
      ['/api/v1/workbench', 'GET', undefined],
      ['/api/v1/workbench/notices', 'GET', undefined],
      ['/api/v1/workbench/recent-bindings', 'GET', undefined],
      ['/api/v1/workbench/contribution-summary', 'GET', { month: '2026-08' }],
      ['/api/v1/me/account-summary', 'GET', undefined]
    ])
  } finally {
    fixture.restore()
  }
})

test('only identical in-flight workbench requests are shared and account switch clears them', async () => {
  const fixture = loadService()
  try {
    const first = fixture.service.getWorkbench('user-1')
    const second = fixture.service.getWorkbench('user-1')
    assert.strictEqual(first, second)
    await first

    await fixture.service.getWorkbench('user-1')
    await fixture.service.getWorkbench('user-2')
    assert.equal(fixture.calls.filter((item) => item.path === '/api/v1/workbench').length, 3)
  } finally {
    fixture.restore()
  }
})
