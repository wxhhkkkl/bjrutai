import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import Orders from '@/pages/mall/orders/index.vue'
import Detail from '@/pages/mall/orders/detail.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-orders'
import { capturedToasts } from './toast'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, ElMessage: vi.fn() }
})
vi.mock('@/api/mall-orders', () => ({
  listOrders: vi.fn(),
  getOrder: vi.fn(),
  saveNote: vi.fn(),
  cancelOrder: vi.fn(),
  registerShipment: vi.fn(),
  correctTracking: vi.fn(),
  getCommand: vi.fn(),
}))
const guards = vi.hoisted(() => ({ leave: vi.fn(), update: vi.fn() }))
const routerMocks = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerMocks.push }),
  onBeforeRouteLeave: guards.leave,
  onBeforeRouteUpdate: guards.update,
}))
const order = {
  id: '9',
  orderNo: 'M-TEST-9',
  status: 'pending_payment',
  paymentStatus: 'creating',
  payableAmountCent: 21000,
  paidAmountCent: 0,
  freightAmountCent: 1000,
  goodsAmountCent: 20000,
  netReceivedCent: 0,
  refundedGoodsCent: 0,
  refundedFreightCent: 0,
  refundReservedCent: 0,
  version: 3,
  internalNote: '库房核实',
  buyerNote: '周末收货',
  buyer: { id: '7', displayName: '测试买家' },
  address: {
    recipientName: '测试收件人',
    phoneMasked: '138****1234',
    regionCodes: ['110000', '110100', '110101'],
    addressMasked: '详细地址已保存',
  },
  items: [
    {
      id: '1',
      productName: '谷物',
      quantity: 2,
      unitPriceCent: 10000,
      lineAmountCent: 20000,
    },
  ],
  shipment: null,
  timeline: [],
  createdAt: '2026-11-06T01:00:00Z',
  paidAt: null,
  expiresAt: '2026-11-06T01:30:00Z',
  invoiceRequestId: null,
  paymentId: '11',
  aftersaleIds: [],
  fulfillmentCheck: {
    businessReady: false,
    blockingReasons: [
      { code: 'payment_unconfirmed', message: '尚未核实成功收款' },
    ],
  },
  availableActions: ['noteMallOrder', 'cancelAdminMallOrder'],
}
function page(
  Component,
  permissions = ['mall.orders.read', 'mall.orders.write']
) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Component, {
    props: Component === Detail ? { id: '9' } : {},
    global: { plugins: [pinia, ElementPlus] },
  })
}
beforeEach(() => {
  vi.clearAllMocks()
  api.getOrder.mockResolvedValue(structuredClone(order))
  api.listOrders.mockResolvedValue({
    items: [structuredClone(order)],
    total: 1,
    nextCursor: null,
  })
})

it('shows real readiness and masks, with no write or raw-release buttons for readers', async () => {
  const wrapper = page(Detail, ['mall.orders.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('尚未核实成功收款')
  expect(wrapper.text()).toContain('138****1234')
  expect(wrapper.find('[data-test="save-note"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="cancel-order"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="ship-order"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('13800001234')
  wrapper.unmount()
})

it('shows full recipient details in fulfillment when the API returns them', async () => {
  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    address: {
      ...structuredClone(order.address),
      phone: '13800001234',
      regionNames: ['北京市', '北京市', '东城区'],
      addressLine: '测试路1号',
    },
  })
  const wrapper = page(Detail, [
    'mall.orders.read',
    'mall.fulfillment.release',
  ])
  await flushPromises()
  const summary = wrapper.find('[data-test="order-recipient-summary"]')
  expect(summary.exists()).toBe(true)
  expect(summary.text()).toContain('13800001234')
  expect(summary.text()).toContain('北京市北京市东城区测试路1号')
  const full = wrapper.find('[data-test="fulfillment-address-full"]')
  expect(full.exists()).toBe(true)
  expect(full.text()).toContain('13800001234')
  expect(full.text()).toContain('北京市北京市东城区测试路1号')
  wrapper.unmount()
})

it('labels a shipped order as 已发货 instead of needing review', async () => {
  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    status: 'pending_receipt',
    shipment: { id: '30', courierCode: 'zhongtong', trackingNo: 'ZT2026', version: 1 },
  })
  const wrapper = page(Detail, ['mall.orders.read'])
  await flushPromises()
  expect(wrapper.text()).toContain('已发货')
  expect(wrapper.text()).not.toContain('需要核对')
  wrapper.unmount()
})

it('opens invoice processing from the order only for invoice readers', async () => {
  routerMocks.push.mockClear()
  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    invoiceRequestId: '88',
  })
  const reader = page(Detail, ['mall.orders.read', 'mall.invoices.read'])
  await flushPromises()
  const openInvoice = reader.find('[data-test="open-invoice-request"]')
  expect(openInvoice.exists()).toBe(true)
  await openInvoice.trigger('click')
  expect(routerMocks.push).toHaveBeenCalledWith('/mall/invoices/88')
  reader.unmount()

  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    invoiceRequestId: '88',
  })
  const orderOnly = page(Detail, ['mall.orders.read'])
  await flushPromises()
  expect(orderOnly.find('[data-test="open-invoice-request"]').exists()).toBe(false)
  orderOnly.unmount()
})

it('saves the loaded order version and preserves the exact body/key for unknown retries', async () => {
  api.saveNote
    .mockRejectedValueOnce(new Error('断网'))
    .mockResolvedValueOnce({ id: '9', version: 4 })
  const wrapper = page(Detail)
  await flushPromises()
  wrapper.vm.noteText = '请核实包装'
  await wrapper.vm.save()
  expect(api.saveNote.mock.calls[0][0]).toEqual({
    id: '9',
    expectedVersion: 3,
    internalNote: '请核实包装',
  })
  wrapper.vm.noteText = '不能换内容重发'
  await wrapper.vm.retry()
  expect(api.saveNote.mock.calls[1]).toEqual(api.saveNote.mock.calls[0])
  expect(wrapper.text()).not.toContain('结果未确认')
  wrapper.unmount()
})

it('labels accepted cancellation as pending and queries its original command', async () => {
  api.cancelOrder.mockResolvedValue({
    commandId: '77',
    entityId: '9',
    status: 'pending',
  })
  api.getCommand.mockResolvedValue({
    commandId: '77',
    entityId: '9',
    status: 'manual',
  })
  const wrapper = page(Detail)
  await flushPromises()
  wrapper.vm.cancelReason = '买家申请'
  await wrapper.vm.cancel()
  expect(api.cancelOrder.mock.calls[0][0]).toEqual({
    id: '9',
    expectedVersion: 3,
    reason: '买家申请',
  })
  expect(wrapper.text()).toContain('关闭确认中')
  await wrapper.vm.checkProgress()
  expect(api.getCommand).toHaveBeenCalledWith('77')
  expect(wrapper.text()).toContain('需人工处理')
  wrapper.unmount()
})

it('clears private details on a failed reload and lets staff retry the read', async () => {
  const wrapper = page(Detail)
  await flushPromises()
  api.getOrder.mockRejectedValueOnce(new Error('权限已撤销'))
  await wrapper.vm.load()
  expect(capturedToasts()).toContain('权限已撤销')
  expect(wrapper.text()).not.toContain('库房核实')
  await wrapper.vm.load()
  expect(wrapper.text()).toContain('库房核实')
  wrapper.unmount()
})

it('shows local dispatch only to shipment staff and submits an idempotent snapshot', async () => {
  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    status: 'pending_shipment',
    availableActions: ['shipMallOrder'],
    fulfillmentCheck: { businessReady: true, blockingReasons: [] },
  })
  api.registerShipment
    .mockRejectedValueOnce(new Error('连接超时'))
    .mockResolvedValueOnce({ id: '30', version: 1 })
  const wrapper = page(Detail, ['mall.orders.read', 'mall.shipments.write'])
  await flushPromises()
  expect(wrapper.find('[data-test="ship-order"]').exists()).toBe(true)
  wrapper.vm.shipmentForm = { courierCode: ' YUANTONG ', trackingNo: ' YT2026 ' }
  await wrapper.vm.registerShipment()
  expect(api.registerShipment.mock.calls[0][0]).toEqual({
    id: '9',
    expectedVersion: 3,
    courierCode: 'yuantong',
    trackingNo: 'YT2026',
  })
  expect(api.registerShipment.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/)
  const originalRequest = api.registerShipment.mock.calls[0]
  expect(capturedToasts().join('')).toContain('结果未确认，请重试原操作')
  await wrapper.vm.retry()
  expect(api.registerShipment.mock.calls[1]).toEqual(originalRequest)
  expect(capturedToasts().join('')).toContain('本地发货事实已登记')
  wrapper.unmount()
})

it('submits tracking correction with both current versions and the reason', async () => {
  api.getOrder.mockResolvedValueOnce({
    ...structuredClone(order),
    status: 'pending_receipt',
    shipment: { id: '30', courierCode: 'yuantong', trackingNo: 'YT2026', version: 4 },
    availableActions: ['correctMallTracking'],
  })
  api.correctTracking.mockResolvedValue({ id: '30', version: 5 })
  const wrapper = page(Detail, ['mall.orders.read', 'mall.shipments.write'])
  await flushPromises()
  wrapper.vm.trackingForm = {
    courierCode: 'shunfeng',
    trackingNo: 'SF2026',
    reason: '录错了承运商',
  }
  await wrapper.vm.correctTracking()
  expect(api.correctTracking.mock.calls[0][0]).toEqual({
    shipmentId: '30',
    expectedVersion: 3,
    shipmentVersion: 4,
    courierCode: 'shunfeng',
    trackingNo: 'SF2026',
    reason: '录错了承运商',
  })
  expect(api.correctTracking.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/)
  expect(capturedToasts().join('')).toContain('历史出库未重复执行')
  wrapper.unmount()
})

it('binds pagination to applied filters and drops stale rows after failure', async () => {
  api.listOrders.mockResolvedValueOnce({
    items: [order],
    total: 2,
    nextCursor: 'next-token',
  })
  const wrapper = page(Orders)
  await flushPromises()
  wrapper.vm.filters.orderNo = '未提交的筛选'
  await wrapper.vm.changePage(2)
  expect(api.listOrders.mock.calls[1][0].cursor).toBe('next-token')
  expect(api.listOrders.mock.calls[1][0].orderNo).toBeUndefined()
  api.listOrders.mockRejectedValueOnce(new Error('暂不可用'))
  await wrapper.vm.search()
  expect(capturedToasts()).toContain('暂不可用')
  expect(wrapper.text()).not.toContain('M-TEST-9')
  wrapper.unmount()
})

it('reloads the selected order when route props change and blocks losing an unknown write', async () => {
  const wrapper = page(Detail)
  await flushPromises()
  api.getOrder.mockResolvedValue({
    ...order,
    id: '10',
    orderNo: 'M-TEST-10',
    version: 8,
  })
  await wrapper.setProps({ id: '10' })
  await flushPromises()
  expect(api.getOrder).toHaveBeenLastCalledWith('10')
  expect(wrapper.text()).toContain('M-TEST-10')
  api.saveNote.mockRejectedValueOnce(new Error('结果未知'))
  wrapper.vm.noteText = '待核实'
  await wrapper.vm.save()
  expect(guards.leave.mock.calls.at(-1)[0]()).toBe(false)
  expect(guards.update.mock.calls.at(-1)[0]()).toBe(false)
  wrapper.unmount()
})

it('ignores an older detail response that arrives after selecting another order', async () => {
  let finishOld
  api.getOrder.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve }))
    .mockResolvedValueOnce({ ...order, id: '10', orderNo: 'M-TEST-10' })
  const wrapper = page(Detail)
  await wrapper.setProps({ id: '10' })
  await flushPromises()
  expect(wrapper.text()).toContain('M-TEST-10')
  finishOld(order)
  await flushPromises()
  expect(wrapper.text()).toContain('M-TEST-10')
  expect(wrapper.text()).not.toContain('M-TEST-9')
  wrapper.unmount()
})
