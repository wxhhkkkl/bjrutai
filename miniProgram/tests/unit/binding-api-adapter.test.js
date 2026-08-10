const test = require('node:test')
const assert = require('node:assert/strict')
const { adaptSelectablePromoters } = require('../../models/customer-binding')
const { adaptBindingRecords, adaptBindingSummary } = require('../../models/binding-records')
const { adaptBindingResult } = require('../../models/binding-result')

test('binding adapters map backend promoter and status enums safely', () => {
  assert.deepEqual(adaptSelectablePromoters({ items: [{ promoterId: 'p1', displayName: '张三', orgNodeName: '组织' }] }).items[0], {
    id: 'p1', name: '张三', orgName: '组织', avatar: '', code: '', bindingCount: 0
  })
  const records = adaptBindingRecords({ items: [{ requestId: 'r1', status: 'pending_match', statusLabel: '待匹配', customerInfo: { name: '王', phone: '138****0000' }, submittedAt: '2026-08-08T00:00:00Z' }] })
  assert.equal(records.items[0].status, 'matching')
  assert.equal(records.items[0].name, '王')
  assert.equal(records.items[0].phone, '138****0000')
})

test('summary and immediate submit result normalize empty and unknown values', () => {
  assert.deepEqual(adaptBindingSummary({}), { total: 0, bound: 0, pending: 0, rejected: 0, expired: 0 })
  assert.equal(adaptBindingResult({ requestId: 'r1', status: 'future_status' }).state, 'matching')
})
