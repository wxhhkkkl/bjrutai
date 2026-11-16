import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import Contributions from '@/pages/contributions/index.vue'
import Settlement from '@/pages/performance/settlement.vue'

vi.mock('@/api/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

const month = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`

const mallSource = {
  id: 'mall_order:301',
  source: 'mall_order',
  sourceType: 'mall_order',
  title: 'M-202610-301',
  amountCent: 10000,
  status: 'paid',
  occurredAt: '2026-10-18T02:00:00Z',
  customerName: '测试客户',
  personName: '测试人员',
  orgName: '测试组织',
}

const adminMallSource = {
  id: '301',
  sourceType: 'mall',
  sourceRecordId: '301',
  businessPeriod: '2026-10',
  occurredAt: '2026-10-18T02:00:00Z',
  originalAmountCent: 12000,
  refundAmountCent: 2000,
  performanceBaseCent: 10000,
  status: 'assigned',
  sourceVersion: 2,
  orderId: '301',
}

const estimate = {
  orgId: '10',
  period: month,
  intraOrg: [
    {
      distributorId: '20',
      name: '测试人员',
      ruleType: 'intra_org',
      baseCent: 200000,
      ratio: 0.04,
      commissionCent: 8000,
      normalCommissionCent: 8000,
      confirmedAdjustmentCent: -2000,
      appliedDebtCent: 2000,
      redeemableCent: 6000,
      pendingDebtCent: 1500,
      pointsBalance: 60,
      pointsRedeemed: false,
    },
  ],
  orgManagement: [],
  unconfigured: [],
}

let dashboardRows = [mallSource]
let mallSourceRows = [adminMallSource]
let estimateResponse = estimate

function envelope(data) {
  return { data: { data } }
}

function page(Component, permissions = ['contributions.read', 'performance.settle']) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Component, { global: { plugins: [pinia, ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  dashboardRows = [mallSource]
  mallSourceRows = [adminMallSource]
  estimateResponse = estimate
  http.get.mockImplementation(async (url, options = {}) => {
    if (url === '/admin/orgs') {
      return envelope({
        tree: [{ orgId: '10', name: '测试组织', level: 1, children: [] }],
      })
    }
    if (url === '/admin/performance/settleable-periods') {
      return envelope({ periods: [] })
    }
    if (url === '/admin/performance/settlements') {
      return envelope({
        items: [{ period: options.params?.period || month, status: 'reviewed' }],
      })
    }
    if (url === '/admin/performance/estimates') return envelope(estimateResponse)
    if (url === '/admin/performance/adjustments') {
      return envelope({
        items: [
          {
            id: '401',
            originPeriod: '2026-08',
            originEvidenceId: '501',
            originResultId: null,
            originResultPresence: 'not_generated',
            beneficiaryId: '20',
            ruleType: 'intra_org',
            status: 'manual_required',
            deltaCent: -2000,
            remainingCent: -2000,
            evidenceStatus: 'manual_required',
            reason: '原期证据待核实',
            version: 2,
          },
        ],
        nextCursor: null,
        total: 1,
      })
    }
    if (url === '/admin/mall/consumptions') {
      return envelope({ items: mallSourceRows, nextCursor: null, total: mallSourceRows.length })
    }
    if (url === '/admin/contributions/dashboard') {
      return envelope({
        stats: {
          monthlyAmountCent: 12000,
          totalAmountCent: 50000,
          personCount: 1,
          boundUserCount: 1,
        },
        trend: [],
        latest: dashboardRows,
      })
    }
    if (url.startsWith('/admin/contributions/rankings/')) {
      return envelope({ items: [], total: 0 })
    }
    throw new Error(`Unexpected GET ${url}`)
  })
})

afterEach(() => {
  dashboardRows = [mallSource]
  mallSourceRows = [adminMallSource]
  estimateResponse = estimate
  vi.restoreAllMocks()
})

it('labels mall consumption distinctly while keeping its business period and performance base', async () => {
  const wrapper = page(Contributions)
  await flushPromises()

  const mallSourceRequest = http.get.mock.calls.find(
    ([url]) => url === '/admin/mall/consumptions'
  )
  expect(mallSourceRequest?.[1]).toEqual({ params: { pageSize: 20 } })
  expect(wrapper.text()).toContain('商城')
  expect(wrapper.text()).toContain('M-202610-301')
  expect(wrapper.text()).toContain('¥100.00')
  expect(wrapper.text()).toContain('2026-10')
  expect(wrapper.text()).toContain('¥120.00')
  expect(wrapper.text()).toContain('¥20.00')
  expect(wrapper.text()).toContain('已归属')
  wrapper.unmount()
})

it('keeps commissionCent as normal performance and presents adjustment, debt and redeemable values separately', async () => {
  const wrapper = page(Settlement)
  await flushPromises()

  expect(wrapper.text()).toContain('测试人员')
  expect(wrapper.text()).toContain('¥2000.00')
  expect(wrapper.text()).toContain('¥80.00')
  expect(wrapper.text()).toContain('正常绩效')
  expect(wrapper.text()).toContain('调整')
  expect(wrapper.text()).toContain('¥20.00')
  expect(wrapper.text()).toContain('待抵扣')
  expect(wrapper.text()).toContain('¥15.00')
  expect(wrapper.text()).toContain('可兑现')
  expect(wrapper.text()).toContain('¥60.00')
  expect(wrapper.text()).toContain('待人工核实')
  expect(wrapper.text()).toContain('原期证据待核实')
  wrapper.unmount()
})

it('loads the original-period adjustment and frozen net-entitlement endpoints', async () => {
  http.get.mockResolvedValueOnce(
    envelope({
      items: [
        {
          id: '401',
          originPeriod: '2026-08',
          originEvidenceId: '501',
          originResultId: null,
          originResultPresence: 'not_generated',
          status: 'manual_required',
          deltaCent: -2000,
          remainingCent: 0,
          evidenceStatus: 'manual_required',
          evidenceFileIds: [],
          reason: '原期证据待核实',
          version: 2,
        },
      ],
      nextCursor: null,
      total: 1,
    })
  )
  http.get.mockResolvedValueOnce(
    envelope({
      resultId: '601',
      period: '2026-10',
      normalCommissionCent: 8000,
      confirmedAdjustmentCent: -2000,
      appliedDebtCent: 2000,
      redeemableCent: 6000,
      pendingDebtCent: 1500,
      version: 3,
    })
  )

  const { performanceApi } = await import('@/api/performance')
  expect(typeof performanceApi.listAdjustments).toBe('function')
  expect(typeof performanceApi.netEntitlement).toBe('function')

  const adjustments = await performanceApi.listAdjustments({ cursor: 'cursor-1', pageSize: 20 })
  const net = await performanceApi.netEntitlement('601')

  expect(adjustments.items[0].originResultId).toBeNull()
  expect(adjustments.items[0].originEvidenceId).toBe('501')
  expect(adjustments.items[0].originResultPresence).toBe('not_generated')
  expect(net.normalCommissionCent).toBe(8000)
  expect(net.redeemableCent).toBe(6000)
  expect(http.get).toHaveBeenNthCalledWith(1, '/admin/performance/adjustments', {
    params: { cursor: 'cursor-1', pageSize: 20 },
  })
  expect(http.get).toHaveBeenNthCalledWith(
    2,
    '/admin/performance/results/601/net-entitlement'
  )
})

it('keeps legacy consumption and commission rows readable with no mall data', async () => {
  dashboardRows = [
    {
      id: 'legacy:701',
      source: 'manual',
      sourceType: 'legacy_bill',
      title: 'LEGACY-701',
      amountCent: 5000,
      status: 'paid',
      occurredAt: '2026-10-10T02:00:00Z',
      customerName: '旧客户',
      personName: '旧人员',
      orgName: '旧组织',
    },
  ]
  mallSourceRows = []
  estimateResponse = {
    ...estimate,
    intraOrg: [
      {
        distributorId: '20',
        name: '旧人员',
        baseCent: 200000,
        ratio: 0.04,
        commissionCent: 8000,
        pointsBalance: 80,
        pointsRedeemed: false,
      },
    ],
  }

  const contributions = page(Contributions)
  const performance = page(Settlement)
  await flushPromises()

  expect(contributions.text()).toContain('人工录入')
  expect(contributions.text()).toContain('LEGACY-701')
  expect(contributions.text()).toContain('暂无商城来源记录')
  expect(performance.text()).toContain('正常绩效（原提成金额）')
  expect(performance.text()).toContain('¥80.00')
  expect(performance.text()).toContain('¥0.00')
  contributions.unmount()
  performance.unmount()
})
