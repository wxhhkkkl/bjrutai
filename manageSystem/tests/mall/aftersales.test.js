import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import Aftersales from '@/pages/mall/aftersales/index.vue'
import Detail from '@/pages/mall/aftersales/detail.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-aftersales'
import { capturedToasts } from './toast'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, ElMessage: vi.fn() }
})
vi.mock('@/api/mall-aftersales', () => ({
  listAdminAftersales: vi.fn(),
  getAdminAftersale: vi.fn(),
  getAdminMallRefund: vi.fn(),
  getAdminReturnLogistics: vi.fn(),
  decideAftersale: vi.fn(),
  receiveAftersaleReturn: vi.fn(),
  executeAftersaleRefund: vi.fn(),
  getAftersaleProofAccess: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))

const record = {
  id: '8',
  orderId: '9',
  aftersaleNo: 'A-TEST-8',
  method: 'return_refund',
  status: 'submitted',
  reason: '商品有损坏',
  proofFileIds: [],
  goodsRefundCent: 5000,
  freightRefundCent: 0,
  refundId: null,
  auditReason: null,
  receiptResult: null,
  returnTrackingNo: null,
  items: [
    {
      id: '80',
      orderItemId: '90',
      quantity: 2,
      goodsRefundCent: 5000,
      sellableReceivedQuantity: 0,
    },
  ],
  version: 3,
}

function page(Component, permissions = ['mall.aftersales.read']) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Component, {
    props: Component === Detail ? { id: '8' } : {},
    global: { plugins: [pinia, ElementPlus] },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listAdminAftersales.mockResolvedValue({
    items: [structuredClone(record)],
    total: 1,
    nextCursor: null,
  })
  api.getAdminAftersale.mockResolvedValue(structuredClone(record))
  api.getAdminMallRefund.mockResolvedValue(null)
  api.getAdminReturnLogistics.mockResolvedValue({
    aftersaleId: '8',
    orderId: '9',
    aftersaleVersion: 3,
    provider: 'kuaidi100',
    source: null,
    courierCode: 'yuantong',
    trackingNo: 'YT202611130001',
    queryStatus: 'pending',
    stateCode: null,
    stateName: null,
    events: [],
    updatedAt: null,
    nextQueryAt: null,
    mapAvailable: false,
    mapUrl: null,
    errorCode: null,
  })
})

it('filters the server page by an applied status and drops stale rows on failure', async () => {
  const wrapper = page(Aftersales)
  await flushPromises()
  wrapper.vm.filters.status = 'awaiting_receipt'
  await wrapper.vm.search()
  expect(api.listAdminAftersales.mock.calls.at(-1)[0]).toEqual({
    status: 'awaiting_receipt',
    pageSize: 20,
  })
  api.listAdminAftersales.mockRejectedValueOnce(new Error('权限已撤销'))
  await wrapper.vm.search()
  expect(capturedToasts()).toContain('权限已撤销')
  expect(wrapper.text()).not.toContain('A-TEST-8')
  wrapper.unmount()
})

it('shows no review or finance controls to an aftersale reader', async () => {
  const wrapper = page(Detail, ['mall.aftersales.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('待审核')
  expect(wrapper.find('[data-test="approve"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="reject"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="execute-refund"]').exists()).toBe(false)
  wrapper.unmount()
})

it('shows the return courier company and its return logistics card', async () => {
  api.getAdminAftersale.mockResolvedValueOnce({
    ...structuredClone(record),
    status: 'awaiting_receipt',
    returnCompany: 'yuantong',
    returnTrackingNo: 'YT202611130001',
  })
  const wrapper = page(Detail, ['mall.aftersales.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('退货快递公司')
  expect(wrapper.text()).toContain('圆通速递')
  expect(wrapper.text()).toContain('退货物流轨迹')
  expect(wrapper.text()).toContain('YT202611130001')
  expect(api.getAdminReturnLogistics).toHaveBeenCalledWith('8')
  wrapper.unmount()
})

it('retries an uncertain review with the same body and idempotency key', async () => {
  api.decideAftersale
    .mockRejectedValueOnce(new Error('连接超时'))
    .mockResolvedValueOnce({ id: '8', status: 'awaiting_return' })
  const wrapper = page(Detail, [
    'mall.aftersales.read',
    'mall.aftersales.review',
  ])
  await flushPromises()
  wrapper.vm.reviewReason = '核实后同意退回'
  await wrapper.vm.decide('approve')
  const original = api.decideAftersale.mock.calls[0]
  expect(original[0]).toEqual({
    id: '8',
    expectedVersion: 3,
    decision: 'approve',
    reason: '核实后同意退回',
  })
  expect(capturedToasts().join('')).toContain('结果未确认，请重试原操作')
  await wrapper.vm.retry()
  expect(api.decideAftersale.mock.calls[1]).toEqual(original)
  expect(capturedToasts().join('')).toContain('审核结果已保存')
  wrapper.unmount()
})

it('sends only positively inspected quantities for a partial return receipt', async () => {
  api.getAdminAftersale.mockResolvedValueOnce({
    ...structuredClone(record),
    status: 'awaiting_receipt',
  })
  api.receiveAftersaleReturn.mockResolvedValue({
    id: '8',
    status: 'awaiting_refund',
  })
  const wrapper = page(Detail, ['mall.aftersales.read', 'mall.returns.receive'])
  await flushPromises()
  wrapper.vm.receiptForm.result = 'partially_accepted'
  wrapper.vm.receiptForm.reason = '一件可售，一件损坏'
  wrapper.vm.sellable['80'] = 1
  await wrapper.vm.receiveReturn()
  expect(api.receiveAftersaleReturn.mock.calls[0][0]).toEqual({
    id: '8',
    expectedVersion: 3,
    result: 'partially_accepted',
    sellableItems: [{ aftersaleItemId: '80', quantity: 1 }],
    reason: '一件可售，一件损坏',
  })
  expect(capturedToasts().join('')).toContain('库存只按可售数量回补')
  wrapper.unmount()
})

it('labels refund execution as queued and never as money received', async () => {
  api.getAdminAftersale.mockResolvedValueOnce({
    ...structuredClone(record),
    status: 'awaiting_refund',
    method: 'refund_only',
  })
  api.executeAftersaleRefund.mockResolvedValue({ status: 'prepared' })
  const wrapper = page(Detail, ['mall.aftersales.read', 'mall.refunds.execute'])
  await flushPromises()
  await wrapper.vm.executeRefund()
  expect(api.executeAftersaleRefund.mock.calls[0][0]).toEqual({
    id: '8',
    expectedVersion: 3,
  })
  expect(capturedToasts().join('')).toContain('已发起退款，正在等待支付渠道处理')
  expect(wrapper.text()).not.toContain('退款到账成功')
  wrapper.unmount()
})

it('previews an attached proof only through a short-lived permissioned access URL', async () => {
  api.getAdminAftersale.mockResolvedValueOnce({
    ...structuredClone(record),
    proofFileIds: ['12'],
  })
  api.getAftersaleProofAccess.mockResolvedValue({
    accessUrl: 'https://storage.invalid/short-lived',
  })
  const wrapper = page(Detail, ['mall.aftersales.read', 'mall.files.read'])
  await flushPromises()
  await wrapper.vm.openProof('12')
  expect(api.getAftersaleProofAccess).toHaveBeenCalledWith('12')
  expect(wrapper.vm.proofDialogVisible).toBe(true)
  expect(wrapper.vm.proofDialogUrl).toBe('https://storage.invalid/short-lived')
  wrapper.unmount()
})

it('labels an unknown channel refund as unconfirmed with no recovery controls', async () => {
  api.getAdminAftersale.mockResolvedValue({
    ...structuredClone(record),
    status: 'refunding',
    refundId: '15',
  })
  api.getAdminMallRefund.mockResolvedValue({
    id: '15',
    status: 'unknown',
    version: 4,
  })
  const wrapper = page(Detail, [
    'mall.aftersales.read',
    'mall.refunds.read',
    'mall.refunds.query',
    'mall.refunds.execute',
  ])
  await flushPromises()
  expect(wrapper.text()).toContain('退款结果暂时无法确认，请联系管理员核对后再处理。')
  expect(wrapper.find('[data-test="query-refund"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="retry-refund"]').exists()).toBe(false)
  wrapper.unmount()
})

it('keeps abnormal refunds in manual review and hides automatic retry', async () => {
  api.getAdminAftersale.mockResolvedValue({
    ...structuredClone(record),
    status: 'disputed',
    refundId: '16',
  })
  api.getAdminMallRefund.mockResolvedValue({
    id: '16',
    status: 'abnormal',
    version: 2,
  })
  const wrapper = page(Detail, [
    'mall.aftersales.read',
    'mall.refunds.read',
    'mall.refunds.query',
    'mall.refunds.execute',
  ])
  await flushPromises()
  expect(wrapper.text()).toContain('退款处理遇到异常，请联系管理员核实。')
  expect(wrapper.find('[data-test="retry-refund"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="query-refund"]').exists()).toBe(false)
  wrapper.unmount()
})

it('ignores an older refund read after selecting another aftersale', async () => {
  let finishOld
  api.getAdminAftersale
    .mockResolvedValueOnce({ ...structuredClone(record), refundId: '15' })
    .mockResolvedValueOnce({
      ...structuredClone(record),
      id: '10',
      refundId: '16',
      status: 'refunding',
    })
  api.getAdminMallRefund
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve
        })
    )
    .mockResolvedValueOnce({ id: '16', status: 'unknown', version: 2 })
  const wrapper = page(Detail, ['mall.aftersales.read', 'mall.refunds.read'])
  await flushPromises()
  await wrapper.setProps({ id: '10' })
  await flushPromises()
  expect(wrapper.text()).toContain('退款结果暂时无法确认')
  finishOld({ id: '15', status: 'prepared', version: 1 })
  await flushPromises()
  expect(wrapper.text()).toContain('退款结果暂时无法确认')
  expect(wrapper.text()).not.toContain('待处理')
  wrapper.unmount()
})
