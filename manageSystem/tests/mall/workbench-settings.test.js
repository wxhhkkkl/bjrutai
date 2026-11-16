import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import Workbench from '@/pages/mall/workbench/index.vue'
import DeliverySettings from '@/pages/mall/settings/delivery.vue'
import TradeSettings from '@/pages/mall/settings/trade.vue'
import FreightSettings from '@/pages/mall/settings/freight.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-settings'
import { capturedToasts } from './toast'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, ElMessage: vi.fn() }
})

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerMocks.push }),
}))

vi.mock('@/api/mall-settings', () => ({
  getMallWorkbench: vi.fn(),
  getMallSettings: vi.fn(),
  getMallCheckoutSettings: vi.fn(),
  saveMallSettings: vi.fn(),
}))

const settings = {
  version: 4,
  enabled: true,
  purchaseEnabled: false,
  freightMode: 'fixed',
  freightCent: 1500,
  defaultBlockedRegionCodes: ['110101'],
  paymentMinutes: 30,
  autoReceiveDays: 7,
  aftersaleDays: 7,
  contactText: '工作日 9:00-17:00',
  policyVersion: 'mall-policy-v3',
  dispatchAddressMasked: '已配置',
  returnAddressMasked: '已配置',
  returnInstructions: '请保持商品包装完整',
}

function page(Component, permissions = []) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Component, { global: { plugins: [pinia, ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getMallWorkbench.mockResolvedValue({
    pendingShipment: 3,
    pendingAftersale: 1,
    pendingReturnReceipt: 0,
    paymentUnknown: 2,
    refundAbnormal: 0,
    unassigned: 0,
    pendingAdjustment: 0,
    pendingInvoice: 4,
    pendingRedInvoice: 0,
    lowStock: 5,
    paidTodayCent: 12500,
    refundedTodayCent: 2500,
  })
  api.getMallSettings.mockResolvedValue(structuredClone(settings))
  api.getMallCheckoutSettings.mockResolvedValue({ purchasingAvailable: false })
  api.saveMallSettings.mockImplementation(async (body) => ({
    ...body.settings,
    version: settings.version + 1,
  }))
})

it('shows only actionable, permission-scoped workbench items and routes to existing screens', async () => {
  const wrapper = page(Workbench, [
    'mall.orders.read',
    'mall.payments.read',
    'mall.invoices.read',
  ])
  await flushPromises()

  expect(
    wrapper.get('[data-test="work-item-pendingShipment"]').text()
  ).toContain('3')
  expect(
    wrapper.get('[data-test="work-item-paymentUnknown"]').text()
  ).toContain('2')
  expect(
    wrapper.find('[data-test="work-item-pendingAftersale"]').exists()
  ).toBe(false)
  expect(wrapper.find('[data-test="work-item-unassigned"]').exists()).toBe(
    false
  )
  await wrapper.get('[data-test="work-link-paymentUnknown"]').trigger('click')
  expect(routerMocks.push).toHaveBeenCalledWith('/mall/payments')
  wrapper.unmount()
})

it('keeps failed workbench reads explicit instead of displaying zero counts', async () => {
  api.getMallWorkbench.mockRejectedValueOnce(new Error('工作台暂不可用'))
  const wrapper = page(Workbench, ['mall.orders.read'])
  await flushPromises()

  expect(capturedToasts()).toContain('工作台暂不可用')
  expect(wrapper.find('[data-test="workbench-reload"]').exists()).toBe(true)
  expect(wrapper.find('[data-test="workbench-summary"]').exists()).toBe(false)
  await wrapper.get('[data-test="workbench-reload"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-test="workbench-summary"]').exists()).toBe(true)
  expect(
    wrapper.get('[data-test="work-item-pendingShipment"]').text()
  ).toContain('3')
  wrapper.unmount()
})

it('saves versioned trade settings and hides writes from read-only staff', async () => {
  const wrapper = page(TradeSettings, [
    'mall.settings.read',
    'mall.settings.write',
  ])
  await flushPromises()

  await wrapper.get('[data-test="purchase-enabled"]').trigger('click')
  await wrapper.get('[data-test="settings-reason"]').setValue('首期开放前调整')
  await wrapper.get('[data-test="save-trade-settings"]').trigger('click')
  await flushPromises()

  expect(api.saveMallSettings).toHaveBeenCalledTimes(1)
  const [body, key] = api.saveMallSettings.mock.calls[0]
  expect(body).toMatchObject({
    expectedVersion: 4,
    reason: '首期开放前调整',
    settings: { version: 4, purchaseEnabled: true, freightCent: 1500 },
  })
  expect(key).toHaveLength(36)
  wrapper.unmount()

  const reader = page(TradeSettings, ['mall.settings.read'])
  await flushPromises()
  expect(reader.find('[data-test="save-trade-settings"]').exists()).toBe(false)
  expect(reader.find('[data-test="purchase-enabled"]').classes()).toContain(
    'is-disabled'
  )
  reader.unmount()
})

it('retries the original settings body and idempotency key after an unknown save result', async () => {
  api.saveMallSettings
    .mockRejectedValueOnce(new Error('连接中断'))
    .mockResolvedValueOnce({ ...settings, version: 5, purchaseEnabled: true })
  const wrapper = page(TradeSettings, [
    'mall.settings.read',
    'mall.settings.write',
  ])
  await flushPromises()
  await wrapper.get('[data-test="purchase-enabled"]').trigger('click')
  await wrapper.get('[data-test="settings-reason"]').setValue('重试一致性检查')

  await wrapper.get('[data-test="save-trade-settings"]').trigger('click')
  await flushPromises()
  const original = api.saveMallSettings.mock.calls[0]
  expect(wrapper.get('[data-test="retry-settings"]').exists()).toBe(true)

  await wrapper.get('[data-test="settings-reason"]').setValue('重试时修改原因')
  await wrapper.get('[data-test="retry-settings"]').trigger('click')
  await flushPromises()

  expect(api.saveMallSettings.mock.calls[1]).toEqual(original)
  expect(original[0].settings.freightCent).toBe(1500)
  wrapper.unmount()
})

it('does not resend read-only warehouse address details from the freight settings form', async () => {
  api.getMallSettings.mockResolvedValue({
    ...structuredClone(settings),
    dispatchAddress: {
      contactName: '仓库联系人',
      phone: '13800000001',
      regionCodes: ['110000', '110100', '110101'],
      regionNames: ['北京市', '北京市', '昌平区'],
      addressLine: '仓库完整地址',
    },
    returnAddress: {
      contactName: '退货联系人',
      phone: '13800000002',
      regionCodes: ['110000', '110100', '110101'],
      regionNames: ['北京市', '北京市', '昌平区'],
      addressLine: '退货完整地址',
    },
  })
  const pinia = createPinia()
  useAuthStore(pinia).permissions = ['mall.settings.read', 'mall.settings.write']
  const wrapper = mount(FreightSettings, {
    global: { plugins: [pinia, ElementPlus], stubs: { teleport: true } },
  })
  await flushPromises()

  const edit = wrapper
    .findAll('button')
    .find((button) => button.text().includes('编辑'))
  await edit.trigger('click')
  await flushPromises()
  await wrapper.get('form').trigger('submit')
  await flushPromises()

  expect(api.saveMallSettings).toHaveBeenCalledTimes(1)
  const [body] = api.saveMallSettings.mock.calls[0]
  expect(body.settings).not.toHaveProperty('dispatchAddress')
  expect(body.settings).not.toHaveProperty('returnAddress')
  expect(body).not.toHaveProperty('dispatchAddress')
  expect(body).not.toHaveProperty('returnAddress')
  wrapper.unmount()
})

it('requires an explicit address replacement and never resends the untouched masked address', async () => {
  const wrapper = page(DeliverySettings, [
    'mall.settings.read',
    'mall.settings.write',
  ])
  await flushPromises()

  expect(wrapper.text()).toContain('已配置')
  expect(wrapper.text()).not.toContain('13800138000')
  expect(wrapper.text()).not.toContain('北京市东城区真实路段')
  expect(wrapper.find('[data-test="dispatch-name"]').exists()).toBe(false)

  await wrapper.get('[data-test="edit-dispatch-address"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="dispatch-name"]').setValue('仓库联系人')
  await wrapper.get('[data-test="dispatch-phone"]').setValue('13800138000')
  await wrapper
    .get('[data-test="dispatch-address-line"]')
    .setValue('东城区示例路 1 号')
  await wrapper.get('[data-test="dispatch-region-0"]').setValue('110000')
  await wrapper.get('[data-test="dispatch-region-1"]').setValue('110100')
  await wrapper.get('[data-test="dispatch-region-2"]').setValue('110101')
  await wrapper.get('[data-test="save-dispatch-address"]').trigger('click')
  await flushPromises()

  const [body] = api.saveMallSettings.mock.calls[0]
  expect(body.dispatchAddress).toMatchObject({
    contactName: '仓库联系人',
    phone: '13800138000',
    regionCodes: ['110000', '110100', '110101'],
    addressLine: '东城区示例路 1 号',
  })
  expect(body).not.toHaveProperty('returnAddress')
  expect(body.settings.returnAddressMasked).toBe('已配置')
  wrapper.unmount()
})

it('does not expose address or trade mutation controls without settings.write', async () => {
  const wrapper = page(DeliverySettings, ['mall.settings.read'])
  await flushPromises()
  expect(wrapper.find('[data-test="replace-dispatch"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="save-delivery-settings"]').exists()).toBe(
    false
  )
  expect(wrapper.text()).toContain('仅可查看')
  wrapper.unmount()
})
