const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

function loadServices(responses) {
  const requestPath = path.resolve(__dirname, '../../services/request-service.js')
  const servicePaths = [
    path.resolve(__dirname, '../../services/commission-service.js'),
    path.resolve(__dirname, '../../services/org-performance-service.js'),
    path.resolve(__dirname, '../../services/consumption-service.js')
  ]
  const originalRequest = require.cache[requestPath]
  const originalServices = new Map(servicePaths.map((servicePath) => [servicePath, require.cache[servicePath]]))
  const calls = []

  servicePaths.forEach((servicePath) => delete require.cache[servicePath])
  require.cache[requestPath] = {
    id: requestPath,
    filename: requestPath,
    loaded: true,
    exports: {
      request(pathname, options = {}) {
        calls.push({ pathname, options })
        return Promise.resolve(responses[pathname])
      }
    }
  }

  const commission = require(servicePaths[0])
  const orgPerformance = require(servicePaths[1])
  const consumption = require(servicePaths[2])

  return {
    commission,
    orgPerformance,
    consumption,
    calls,
    restore() {
      servicePaths.forEach((servicePath) => {
        delete require.cache[servicePath]
        const original = originalServices.get(servicePath)
        if (original) require.cache[servicePath] = original
      })
      if (originalRequest) require.cache[requestPath] = originalRequest
      else delete require.cache[requestPath]
    }
  }
}

const normalWithDebt = {
  baseCent: 200000,
  ratio: 0.04,
  commissionCent: 8000,
  normalCommissionCent: 8000,
  confirmedAdjustmentCent: -2000,
  appliedDebtCent: 2000,
  redeemableCent: 6000,
  pendingDebtCent: 1500,
  originKind: 'normal'
}

const mallOrderSource = {
  id: 'mall_order:301',
  source: 'mall_order',
  sourceId: '301',
  title: 'M-202610-301',
  amountCent: 10000,
  status: 'paid',
  customerId: '30',
  customerName: '测试客户',
  phoneMasked: null,
  occurredAt: '2026-10-18T02:00:00Z'
}

const legacyBillSource = {
  id: '41',
  source: 'manual',
  title: 'B-202610-41',
  amountCent: 5000,
  status: 'paid',
  occurredAt: '2026-10-10T02:00:00Z'
}

test('my and org commission services preserve legacy commissionCent and net fields', async () => {
  const f = loadServices({
    '/api/v1/my/performance/commission': {
      currentMonth: {
        month: '2026-10',
        status: 'confirmed',
        intraOrg: { ...normalWithDebt },
        orgManagement: null,
        pointsBalance: 60
      },
      confirmed: []
    },
    '/api/v1/org/performance/commission': {
      orgId: '10',
      currentMonth: {
        month: '2026-10',
        status: 'confirmed',
        summary: {
          commissionCent: 8000,
          normalCommissionCent: 8000,
          confirmedAdjustmentCent: -2000,
          appliedDebtCent: 2000,
          redeemableCent: 6000,
          pendingDebtCent: 1500
        },
        members: [{ distributorId: '20', ...normalWithDebt }]
      },
      confirmed: []
    }
  })

  try {
    const mine = await f.commission.requestMyCommission({ month: '2026-10' })
    const org = await f.commission.requestOrgCommission({ month: '2026-10' })

    assert.equal(mine.currentMonth.intraOrg.commissionCent, 8000)
    assert.equal(mine.currentMonth.isFrozen, true)
    assert.equal(mine.currentMonth.isEstimate, false)
    assert.equal(mine.currentMonth.intraOrg.normalCommissionCent, 8000)
    assert.equal(mine.currentMonth.intraOrg.redeemableCent, 6000)
    assert.equal(mine.currentMonth.intraOrg.pendingDebtCent, 1500)
    assert.equal(org.currentMonth.summary.commissionCent, 8000)
    assert.equal(org.currentMonth.isFrozen, true)
    assert.equal(org.currentMonth.isEstimate, false)
    assert.equal(org.currentMonth.members[0].commissionCent, 8000)
    assert.equal(org.currentMonth.members[0].confirmedAdjustmentCent, -2000)
    assert.equal(org.currentMonth.members[0].appliedDebtCent, 2000)
    assert.equal(org.currentMonth.members[0].redeemableCent, 6000)
    assert.deepEqual(f.calls, [
      {
        pathname: '/api/v1/my/performance/commission',
        options: { data: { month: '2026-10' } }
      },
      {
        pathname: '/api/v1/org/performance/commission',
        options: { data: { month: '2026-10' } }
      }
    ])
  } finally {
    f.restore()
  }
})

test('commission services normalize legacy amounts and keep estimates separate from frozen results', async () => {
  const f = loadServices({
    '/api/v1/my/performance/commission': {
      currentMonth: {
        month: '2026-10',
        status: 'estimate',
        intraOrg: { commissionCent: 1250 },
        orgManagement: {
          commissionCent: 1000,
          confirmedAdjustmentCent: -1500,
          appliedDebtCent: 1500
        }
      },
      confirmed: [{
        month: '2026-09',
        intraOrg: { commissionCent: 700 },
        orgManagement: null
      }]
    },
    '/api/v1/org/performance/commission': {
      orgId: '10',
      currentMonth: {
        month: '2026-10',
        status: 'estimate',
        summary: { commissionCent: 1250 },
        members: [{ distributorId: '20', commissionCent: 1250 }]
      },
      confirmed: []
    }
  })

  try {
    const mine = await f.commission.requestMyCommission({ month: '2026-10' })
    const org = await f.commission.requestOrgCommission({ month: '2026-10' })
    const mineLine = mine.currentMonth.intraOrg
    const orgLine = org.currentMonth.members[0]

    assert.equal(mine.currentMonth.isFrozen, false)
    assert.equal(mine.currentMonth.isEstimate, true)
    assert.equal(mineLine.commissionCent, 1250)
    assert.equal(mineLine.normalCommissionCent, 1250)
    assert.equal(mineLine.confirmedAdjustmentCent, 0)
    assert.equal(mineLine.appliedDebtCent, 0)
    assert.equal(mineLine.redeemableCent, 1250)
    assert.equal(mineLine.pendingDebtCent, 0)
    assert.equal(mine.currentMonth.orgManagement.redeemableCent, 0)
    assert.equal(mine.confirmed[0].isFrozen, true)
    assert.equal(mine.confirmed[0].intraOrg.normalCommissionCent, 700)
    assert.equal(org.currentMonth.isEstimate, true)
    assert.equal(orgLine.commissionCent, 1250)
    assert.equal(orgLine.normalCommissionCent, 1250)
    assert.equal(orgLine.redeemableCent, 1250)
    assert.equal(org.currentMonth.summary.normalCommissionCent, 1250)
  } finally {
    f.restore()
  }
})

test('consumption services preserve organization totals and unified mall-order rows', async () => {
  const f = loadServices({
    '/api/v1/org/performance': {
      orgId: '10',
      period: '2026-10',
      summary: { thisMonth: 10000, cumulative: 50000 },
      members: [{ distributorId: '20', thisMonth: 10000, cumulative: 50000 }]
    },
    '/api/v1/contributions': {
      items: [mallOrderSource, legacyBillSource],
      nextCursor: null,
      total: 2
    }
  })

  try {
    const org = await f.orgPerformance.requestOrgPerformance({ month: '2026-10' })
    const bills = await f.consumption.listBills({ month: '2026-10', pageSize: 20 })

    assert.equal(org.summary.thisMonth, 10000)
    assert.equal(org.members[0].thisMonth, 10000)
    assert.equal(bills.items[0].source, 'mall_order')
    assert.equal(bills.items[0].sourceType, 'mall_order')
    assert.equal(bills.items[0].amountCent, 10000)
    assert.equal(bills.items[1].source, 'manual')
    assert.equal(bills.items[1].sourceType, 'legacy_bill')
    assert.deepEqual(f.calls, [
      {
        pathname: '/api/v1/org/performance',
        options: { data: { month: '2026-10' } }
      },
      {
        pathname: '/api/v1/contributions',
        options: { data: { month: '2026-10', pageSize: 20 } }
      }
    ])
  } finally {
    f.restore()
  }
})
