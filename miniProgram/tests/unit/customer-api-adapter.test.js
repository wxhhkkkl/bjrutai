const test = require('node:test')
const assert = require('node:assert/strict')
const { adaptCustomerList, filterCustomers, sortCustomers } = require('../../models/customer-list')
const { adaptCustomerDetail } = require('../../models/customer-detail')
const { adaptCustomerEditResponse } = require('../../models/customer-edit')
const { adaptCustomerAnalysis } = require('../../models/customer-analysis')

test('customer list maps backend statuses, masks and cursor metadata', () => {
  const result = adaptCustomerList({
    items: [{
      id: 'c1', name: '王女士', phoneMasked: '138****1028', bindingStatus: 'bound',
      note: '备注', updatedAt: '2026-08-08T00:00:00Z'
    }],
    nextCursor: '1', hasMore: true
  })
  assert.equal(result.items[0].status, '已绑定')
  assert.equal(result.items[0].tone, 'blue')
  assert.equal(result.items[0].avatar, '/assets/images/customer-avatar-blue.png')
  assert.equal(result.nextCursor, '1')
  assert.equal(result.hasMore, true)
})

test('customer detail maps cents and keeps masked unsupported identity fields', () => {
  const result = adaptCustomerDetail({
    id: 'c1', name: '王女士', phoneMasked: '138****1028', idCardMasked: '110***********1234',
    bindingStatus: 'pending', version: 3, monthlyConsumptionCent: 188000,
    totalConsumptionCent: 320000, serviceCount: 4, followupCount: 1,
    boundAt: '2026-08-08T00:00:00Z'
  })
  assert.equal(result.status, '待匹配')
  assert.equal(result.monthlyContribution, '1,880.00')
  assert.equal(result.totalContribution, '3,200.00')
  assert.equal(result.idCard, '110***********1234')
  assert.equal(result.version, 3)
})

test('edit response only exposes fields supported by PATCH', () => {
  assert.deepEqual(adaptCustomerEditResponse({
    id: 'c1', name: '王女士', phone: '138****1028', note: '备注', familyPhone: '139****0000',
    version: 4, reviewRequired: true
  }), {
    id: 'c1', name: '王女士', phone: '138****1028', note: '备注',
    familyPhone: '139****0000', version: 4, reviewRequired: true
  })
})

test('analysis maps empty trends and source distribution without inventing values', () => {
  const result = adaptCustomerAnalysis({
    period: '30d',
    overview: { totalCustomers: 2, boundCustomers: 1, pendingCustomers: 1, unboundCustomers: 0, followupCustomers: 1, newCustomers: 1 },
    trend: [{ month: '2026-08', newCustomers: 1 }],
    sourceDistribution: [{ source: 'manual', count: 2 }]
  })
  assert.deepEqual(result.overview, { total: 2, bound: 1, matching: 1, unbound: 0, followup: 1 })
  assert.deepEqual(result.trend.values, [1])
  assert.equal(result.sources[0].label, '人工录入')
})

test('existing customer filters continue to work with adapted list items', () => {
  const list = adaptCustomerList({ items: [{ id: '1', name: '李先生', phoneMasked: '186****3681', bindingStatus: 'pending' }] }).items
  assert.equal(filterCustomers(list, 'matching', '186').length, 1)
  assert.equal(sortCustomers(list, 'name')[0].id, '1')
})

test('followup filter keeps the customer binding status and uses the backend reminder flag', () => {
  const list = adaptCustomerList({
    items: [{
      id: '2', name: '王女士', phoneMasked: '138****1028', bindingStatus: 'bound',
      hasPendingFollowup: true
    }]
  }).items

  assert.equal(list[0].status, '已绑定')
  assert.equal(filterCustomers(list, 'followup', '王').length, 1)
})
