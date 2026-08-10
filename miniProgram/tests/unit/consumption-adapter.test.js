const test = require('node:test')
const assert = require('node:assert/strict')
const { adaptContributionOverview, adaptContributionTrend, adaptBillList } = require('../../models/contribution-detail')

test('consumption adapters format cents and growth without floating business arithmetic', () => {
  assert.deepEqual(adaptContributionOverview({ monthlyAmountCent: 126800, totalAmountCent: 320000, growthRate: 18.5 }), { amount: '¥1,268.00', growth: '+18.5%', total: '¥3,200.00' })
})

test('bill adapter maps paid/refund/cancelled states and unknown values safely', () => {
  const result = adaptBillList({ items: [
    { id: 1, title: 'B1', amountCent: 120000, status: 'paid', customerName: '王', occurredAt: '2026-08-08T00:00:00Z' },
    { id: 2, title: 'B2', amountCent: 0, status: 'future', customerName: null }
  ] })
  assert.equal(result.items[0].value, '¥1,200.00'); assert.equal(result.items[0].statusLabel, '已支付')
  assert.equal(result.items[1].statusLabel, '处理中'); assert.equal(result.items[1].customer, '未知客户')
})

test('trend adapter preserves empty arrays and integer cents', () => {
  assert.deepEqual(adaptContributionTrend({ categories: [], values: [] }), { categories: [], values: [], max: 10, interval: 1 })
})
