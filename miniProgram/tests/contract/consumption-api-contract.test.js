const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function load() {
  const servicePath = path.resolve(__dirname, '../../services/consumption-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const original = require.cache[requestPath]; const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = { id: requestPath, filename: requestPath, loaded: true, exports: { request(pathname, options = {}) { calls.push({ pathname, options }); return Promise.resolve({}) } } }
  return { service: require(servicePath), calls, restore() { delete require.cache[servicePath]; if (original) require.cache[requestPath] = original; else delete require.cache[requestPath] } }
}

test('consumption service calls overview, trend and cursor bill list with exact query', async () => {
  const f = load()
  try {
    await f.service.getOverview('2026-08'); await f.service.getTrend('6m'); await f.service.listBills({ month: '2026-08', status: 'paid', cursor: '10', pageSize: 20 })
    assert.deepEqual(f.calls.map(({ pathname, options }) => [pathname, options.data]), [
      ['/api/v1/contributions/overview', { month: '2026-08' }], ['/api/v1/contributions/trend', { period: '6m' }], ['/api/v1/contributions', { month: '2026-08', status: 'paid', cursor: '10', pageSize: 20 }]
    ])
  } finally { f.restore() }
})

test('consumption service does not expose a single-bill detail request', async () => {
  const f = load()
  try {
    assert.equal(f.service.getBillDetail, undefined)
    assert.equal(f.calls.length, 0)
  } finally { f.restore() }
})
