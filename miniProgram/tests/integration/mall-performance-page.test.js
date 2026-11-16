const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function flush() {
  return new Promise((resolve) => setImmediate(resolve))
}

function loadPage(relativePath, replacements = {}) {
  const root = path.resolve(__dirname, '../..')
  const pagePath = path.resolve(root, relativePath)
  const originalPage = global.Page
  const originalWx = global.wx
  const savedModules = new Map()
  Object.entries(replacements).forEach(([modulePath, exports]) => {
    const resolved = path.resolve(root, modulePath)
    savedModules.set(resolved, require.cache[resolved])
    require.cache[resolved] = {
      id: resolved,
      filename: resolved,
      loaded: true,
      exports
    }
  })

  let definition
  global.Page = (value) => { definition = value }
  global.wx = {
    navigateTo() {},
    navigateBack() {},
    showToast() {},
    stopPullDownRefresh() {}
  }
  delete require.cache[pagePath]
  require(pagePath)

  return {
    page: Object.assign({}, definition, {
      data: JSON.parse(JSON.stringify(definition.data)),
      setData(values, callback) {
        this.data = Object.assign({}, this.data, values)
        if (callback) callback()
      }
    }),
    markup: fs.readFileSync(pagePath.replace(/\.js$/, '.wxml'), 'utf8'),
    restore() {
      delete require.cache[pagePath]
      savedModules.forEach((value, resolved) => {
        if (value) require.cache[resolved] = value
        else delete require.cache[resolved]
      })
      global.Page = originalPage
      global.wx = originalWx
    }
  }
}

test('personal performance shows frozen or estimated status and keeps normal, adjustment and net amounts separate', async () => {
  const fixture = loadPage('pages/performance/index.js', {
    'services/commission-service.js': {
      requestMyCommission: async () => ({
        currentMonth: {
          month: '2026-10',
          status: 'estimate',
          isFrozen: false,
          isEstimate: true,
          intraOrg: {
            commissionCent: 8000,
            normalCommissionCent: 8000,
            confirmedAdjustmentCent: -2000,
            appliedDebtCent: 2000,
            redeemableCent: 6000,
            pendingDebtCent: 1500,
            baseCent: 200000,
            ratio: 0.04
          },
          orgManagement: null,
          pointsBalance: 60
        },
        confirmed: [{
          month: '2026-09',
          isFrozen: true,
          intraOrg: { commissionCent: 7000, redeemableCent: 6500 },
          orgManagement: null
        }]
      })
    }
  })

  try {
    await fixture.page.load()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.currentMonth.isEstimate, true)
    assert.equal(fixture.page.data.currentMonth.intraOrg.normalCommissionCent, 8000)
    assert.equal(fixture.page.data.currentMonth.intraOrg.redeemableCent, 6000)
    assert.match(fixture.markup, /实时预估/)
    assert.match(fixture.markup, /已冻结/)
    assert.match(fixture.markup, /正常绩效/)
    assert.match(fixture.markup, /已抵债/)
    assert.match(fixture.markup, /可兑现/)
    assert.match(fixture.markup, /待抵扣/)
  } finally { fixture.restore() }
})

test('organization performance displays net commission per member and frozen month summaries', async () => {
  const fixture = loadPage('pages/org-performance/index.js', {
    'services/session-service.js': { getCurrentSession: () => ({ orgRole: 'admin' }) },
    'services/org-performance-service.js': {
      requestOrgPerformance: async () => ({
        orgName: '北京一部',
        period: '2026-10',
        summary: { thisMonth: 200000, cumulative: 800000 },
        subOrgs: [],
        members: []
      })
    },
    'services/commission-service.js': {
      requestOrgCommission: async () => ({
        currentMonth: {
          month: '2026-10',
          status: 'confirmed',
          isFrozen: true,
          isEstimate: false,
          summary: {
            commissionCent: 8000,
            normalCommissionCent: 8000,
            confirmedAdjustmentCent: -2000,
            appliedDebtCent: 2000,
            redeemableCent: 6000,
            pendingDebtCent: 1500
          },
          members: [{
            distributorId: '20',
            name: '成员甲',
            commissionCent: 8000,
            normalCommissionCent: 8000,
            confirmedAdjustmentCent: -2000,
            appliedDebtCent: 2000,
            redeemableCent: 6000,
            pendingDebtCent: 1500
          }]
        },
        confirmed: [{ month: '2026-09', summary: { commissionCent: 7000, redeemableCent: 6500 } }]
      })
    }
  })

  try {
    await fixture.page.load()
    await flush()
    assert.equal(fixture.page.data.state, 'success')
    assert.equal(fixture.page.data.commission.currentMonth.isFrozen, true)
    assert.equal(fixture.page.data.commission.currentMonth.members[0].redeemableCent, 6000)
    assert.match(fixture.markup, /正常绩效/)
    assert.match(fixture.markup, /调整/)
    assert.match(fixture.markup, /已抵债/)
    assert.match(fixture.markup, /可兑现/)
    assert.match(fixture.markup, /待抵扣/)
    assert.match(fixture.markup, /已冻结/)
  } finally { fixture.restore() }
})

test('consumption details identify mall rows and label their amount as performance base without customer data', async () => {
  const fixture = loadPage('pages/contribution/index.js', {
    'services/consumption-service.js': {
      getOverview: async () => ({ monthlyAmountCent: 10000, totalAmountCent: 50000, growthRate: 10 }),
      getTrend: async () => ({ categories: ['2026-10'], values: [10000] }),
      listBills: async () => ({
        items: [{
          id: 'mall_order:301',
          source: 'mall_order',
          sourceType: 'mall_order',
          sourceId: '301',
          title: 'M-202610-301',
          amountCent: 10000,
          status: 'paid',
          customerName: '不可展示客户',
          phoneMasked: '138****1234',
          occurredAt: '2026-10-18T02:00:00Z'
        }],
        nextCursor: null,
        total: 1
      })
    },
    'services/navigation-service.js': { openAction: () => ({ ok: false, message: '不可用' }) },
    'services/session-service.js': { getCurrentSession: () => ({}) }
  })

  try {
    await fixture.page.loadData('month')
    assert.equal(fixture.page.data.state, 'success')
    const detail = fixture.page.data.details[0]
    assert.equal(detail.sourceType, 'mall_order')
    assert.equal(detail.sourceLabel, '商城消费')
    assert.equal(detail.valueLabel, '计入绩效')
    assert.doesNotMatch(detail.meta, /不可展示客户|138\*\*\*\*1234/)
    assert.match(fixture.markup, /item\.sourceLabel/)
    assert.match(fixture.markup, /item\.valueLabel/)
    assert.doesNotMatch(fixture.markup, /综合/)
  } finally { fixture.restore() }
})
