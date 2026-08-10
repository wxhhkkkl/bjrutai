const test = require('node:test')
const assert = require('node:assert/strict')
const {
  adaptWorkbench,
  adaptNotices,
  adaptRecentBindings,
  adaptAccountSummary,
  buildHomeViewModel,
  buildProfileViewModel
} = require('../../models/workbench')

test('adapts promoter metrics and formats integer cents for existing page view models', () => {
  const workbench = adaptWorkbench({
    role: 'doctor',
    metrics: {
      myCustomers: 12,
      myBindings: 3,
      myMonthlyConsumption: 126800,
      pendingFollowups: 2
    },
    ignoredBackendField: 'safe to ignore'
  })

  assert.deepEqual(workbench.metrics, {
    myCustomers: 12,
    myBindings: 3,
    myMonthlyConsumptionCent: 126800,
    pendingFollowups: 2
  })
  assert.equal(buildHomeViewModel(workbench).monthlyConsumption, '¥1,268.00')
  assert.deepEqual(buildProfileViewModel(workbench), [
    { label: '客户', value: '12' },
    { label: '本月消费', value: '¥1,268.00' },
    { label: '本月绑定', value: '3' }
  ])
})

test('normalizes admin and unknown role variants without borrowing promoter fields', () => {
  assert.deepEqual(adaptWorkbench({
    role: 'admin',
    metrics: { totalPromoters: 8, totalCustomers: 30, abnormalBindings: 4 }
  }).metrics, {
    totalPromoters: 8,
    totalCustomers: 30,
    abnormalBindings: 4,
    pendingQualifications: 0
  })
  assert.equal(adaptWorkbench({ role: 'future-role', metrics: {} }).role, 'unknown')
})

test('empty lists and unknown binding fields produce safe display models', () => {
  assert.deepEqual(adaptNotices({}), [])
  assert.deepEqual(adaptNotices({ notices: [
    { type: 'binding', title: '绑定请求: bound', time: '2026-08-10T01:26:09Z' },
    { type: 'binding', title: '绑定请求: pending_match', time: '2026-08-10T01:26:09Z' },
    { type: 'system', title: '系统维护通知', time: '2026-08-10T01:26:09Z' }
  ] }).map((item) => item.title), [
    '绑定请求：已绑定',
    '绑定请求：待匹配',
    '系统维护通知'
  ])
  assert.deepEqual(adaptRecentBindings({ items: null }), [])
  assert.deepEqual(adaptRecentBindings({ items: [{
    id: 'b1', customerName: '王女士', status: 'NEW_STATUS', createdAt: '2026-08-08T00:00:00Z'
  }] })[0], {
    id: 'b1',
    name: '王女士',
    phone: '',
    status: '处理中',
    statusCode: 'NEW_STATUS',
    time: '2026年8月8日 08:00'
  })
})

test('account summary supplies safe fallbacks and unread count', () => {
  assert.deepEqual(adaptAccountSummary({
    userId: 'u1', name: null, avatar: null, role: 'promoter', unreadNotifications: 2
  }), {
    userId: 'u1',
    name: '',
    avatar: '',
    role: 'promoter',
    qualificationStatus: 'unknown',
    unreadNotifications: 2
  })
})

test('rejects non-integer monetary values instead of using floating point business amounts', () => {
  assert.throws(() => adaptWorkbench({
    role: 'promoter', metrics: { myMonthlyConsumption: 12.8 }
  }), /整数分/)
})
