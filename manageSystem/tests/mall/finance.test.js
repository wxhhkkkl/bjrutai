import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import PaymentsPage from '@/pages/mall/payments/index.vue'
import RefundsPage from '@/pages/mall/refunds/index.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-finance'

vi.mock('@/api/mall-finance', () => ({
  listAdminMallPayments: vi.fn(),
  queryAdminMallPayment: vi.fn(),
  exportAdminMallPayments: vi.fn(),
  getAdminMallFinanceExport: vi.fn(),
  getAdminMallFinanceExportFile: vi.fn(),
  listAdminMallRefunds: vi.fn(),
  queryAdminMallRefund: vi.fn(),
  exportAdminMallRefunds: vi.fn(),
  getAdminMallFileAccess: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))

const payment = {
  id: '71',
  orderId: '9',
  orderNo: 'LT202611070009',
  buyer: { id: '31', displayName: '鲁泰客户' },
  outTradeNo: 'LT-PAY-71',
  amountCent: 12000,
  currency: 'CNY',
  refundSucceededCent: 3000,
  netReceivedCent: null,
  status: 'unknown',
  createdAt: '2026-11-07T01:00:00Z',
  confirmedAt: null,
  lastQueryAt: null,
  lastErrorCode: 'QUERY_TIMEOUT',
  version: 2,
}

const refund = {
  id: '81',
  orderId: '9',
  aftersaleId: '11',
  paymentId: '71',
  outRefundNo: 'LT-REFUND-81',
  channelRefundId: null,
  goodsRefundCent: 2500,
  freightRefundCent: 500,
  totalCent: 3000,
  status: 'processing',
  confirmedAt: null,
  lastErrorCode: null,
  version: 1,
}

function page(Component, permissions) {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.permissions = permissions
  auth.user = { userId: '31', account: 'finance-tester' }
  return mount(Component, {
    global: { plugins: [pinia, ElementPlus] },
  })
}

beforeEach(() => {
  sessionStorage.clear()
  vi.clearAllMocks()
  api.listAdminMallPayments.mockResolvedValue({
    items: [structuredClone(payment)],
    total: 1,
    nextCursor: null,
  })
  api.listAdminMallRefunds.mockResolvedValue({
    items: [structuredClone(refund)],
    total: 1,
    nextCursor: null,
  })
  api.exportAdminMallPayments.mockResolvedValue({
    requestId: '601',
    fileId: '602',
    jobId: '603',
    status: 'pending',
    version: 1,
  })
  api.exportAdminMallRefunds.mockResolvedValue({
    requestId: '611',
    fileId: '612',
    jobId: '613',
    status: 'pending',
    version: 1,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('keeps the payment ledger separate and shows unknown money as unconfirmed', async () => {
  const wrapper = page(PaymentsPage, ['mall.payments.read'])
  await flushPromises()

  expect(wrapper.text()).toContain('LT202611070009')
  expect(wrapper.text()).toContain('¥120.00')
  expect(wrapper.text()).toContain('¥30.00')
  expect(wrapper.text()).toContain('—')
  expect(wrapper.text()).toContain('结果待核实')
  expect(api.listAdminMallPayments).toHaveBeenCalledOnce()
  expect(api.listAdminMallRefunds).not.toHaveBeenCalled()
  expect(wrapper.text()).not.toContain('openid')
  expect(wrapper.text()).not.toContain('prepay')
  wrapper.unmount()
})

it('applies payment filters to the ledger and requests a bounded filtered export', async () => {
  const wrapper = page(PaymentsPage, [
    'mall.payments.read',
    'mall.finance.export',
  ])
  await flushPromises()
  wrapper.vm.filters.status = 'unknown'
  wrapper.vm.filters.orderNo = 'LT202611070009'
  wrapper.vm.filters.range = [
    new Date('2026-11-06T16:00:00Z'),
    new Date('2026-11-07T16:00:00Z'),
  ]

  await wrapper.vm.search()
  expect(api.listAdminMallPayments).toHaveBeenLastCalledWith({
    pageSize: 20,
    status: 'unknown',
    orderNo: 'LT202611070009',
    fromAt: '2026-11-06T16:00:00.000Z',
    toAt: '2026-11-07T16:00:00.000Z',
  })

  await wrapper.vm.exportFiltered()
  expect(api.exportAdminMallPayments).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('请清空订单号筛选后再导出')
  wrapper.vm.filters.orderNo = ''
  await wrapper.vm.search()

  wrapper.vm.exportFormat = 'xlsx'
  await wrapper.vm.exportFiltered()
  expect(api.exportAdminMallPayments).toHaveBeenCalledWith(
    {
      from: '2026-11-06T16:00:00.000Z',
      to: '2026-11-07T16:00:00.000Z',
      status: 'unknown',
      format: 'xlsx',
    },
    expect.any(String)
  )
  wrapper.unmount()
})

it('keeps refund amounts split and does not merge refunds into payment totals', async () => {
  const wrapper = page(RefundsPage, ['mall.refunds.read'])
  await flushPromises()

  expect(wrapper.text()).toContain('LT-REFUND-81')
  expect(wrapper.text()).toContain('¥25.00')
  expect(wrapper.text()).toContain('¥5.00')
  expect(wrapper.text()).toContain('¥30.00')
  expect(wrapper.text()).toContain('退款处理中')
  expect(api.listAdminMallRefunds).toHaveBeenCalledOnce()
  expect(api.listAdminMallPayments).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('keeps the same export intent when an async export fails and is reclaimed', async () => {
  const wrapper = page(PaymentsPage, [
    'mall.payments.read',
    'mall.finance.export',
  ])
  await flushPromises()
  wrapper.vm.filters.range = [
    new Date('2026-11-06T16:00:00Z'),
    new Date('2026-11-07T16:00:00Z'),
  ]
  await wrapper.vm.search()
  await wrapper.vm.exportFiltered()
  api.getAdminMallFinanceExport.mockResolvedValueOnce({
    requestId: '601',
    fileId: '602',
    status: 'failed',
    errorCode: 'generation_failed',
    version: 1,
  })

  await wrapper.vm.refreshExport()
  expect(wrapper.text()).toContain('导出失败')
  expect(wrapper.find('[data-test="retry-export"]').exists()).toBe(true)
  await wrapper.find('[data-test="retry-export"]').trigger('click')

  const first = api.exportAdminMallPayments.mock.calls[0]
  const second = api.exportAdminMallPayments.mock.calls[1]
  expect(second[0]).toEqual(first[0])
  expect(second[1]).toBe(first[1])
  expect(wrapper.text()).toContain('导出已重新领取')
  wrapper.unmount()
})
