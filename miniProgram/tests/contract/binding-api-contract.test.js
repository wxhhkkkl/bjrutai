const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function fixture() {
  const servicePath = path.resolve(__dirname, '../../services/binding-service.js')
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const original = require.cache[requestPath]
  const calls = []
  delete require.cache[servicePath]
  require.cache[requestPath] = { id: requestPath, filename: requestPath, loaded: true, exports: {
    request(apiPath, options = {}) { calls.push({ apiPath, options }); return Promise.resolve({}) }
  } }
  return { service: require(servicePath), calls, restore() { delete require.cache[servicePath]; if (original) require.cache[requestPath] = original; else delete require.cache[requestPath] } }
}

test('binding service uses selectable, consent, submit, list and summary contracts', async () => {
  const f = fixture()
  try {
    await f.service.getSelectablePromoters({ keyword: '张', cursor: '2', limit: 10 })
    await f.service.recordConsent({ agreementId: 7, scene: 'binding' })
    await f.service.submitBinding({ promoterId: 'p1', customerInfo: { name: '王', phone: '13800000000' }, consentRecordId: 8 }, 'key-1')
    await f.service.listBindingRequests({ status: 'pending_match', submittedByMe: true, keyword: '王' })
    await f.service.getBindingSummary()
    assert.deepEqual(f.calls.map(({ apiPath, options }) => [apiPath, options.method || 'GET', options.data, options.idempotencyKey]), [
      ['/api/v1/promoters/selectable', 'GET', { keyword: '张', cursor: '2', limit: 10 }, undefined],
      ['/api/v1/consents', 'POST', { agreementId: 7, scene: 'binding', confirmed: true, subjectType: 'user' }, undefined],
      ['/api/v1/binding-requests', 'POST', { promoterId: 'p1', customerInfo: { name: '王', phone: '13800000000' }, consentRecordId: 8, sourceType: 'manual' }, 'key-1'],
      ['/api/v1/binding-requests', 'GET', { status: 'pending_match', role: 'initiator', submittedByMe: true, keyword: '王', sortBy: 'created_at', sortOrder: 'desc' }, undefined],
      ['/api/v1/binding-summary', 'GET', undefined, undefined]
    ])
  } finally { f.restore() }
})

test('blocked binding detail/retry/update operations are not exposed', () => {
  const f = fixture()
  try {
    assert.equal(typeof f.service.getBindingDetail, 'undefined')
    assert.equal(typeof f.service.retryBinding, 'undefined')
    assert.equal(typeof f.service.updateCustomerInfo, 'undefined')
  } finally { f.restore() }
})
