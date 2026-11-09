import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import App from '@/App.vue'
import router from '@/router'
import { ALL_PERMISSION_KEYS, PERMISSION_MODULES } from '@/constants/permissions'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: { data: { items: [], unreadCount: 0 } },
    }),
    post: vi.fn().mockResolvedValue({ data: { data: {} } }),
  },
}))

const EXPECTED_MALL_PERMISSIONS = [
  'mall.products.read',
  'mall.products.write',
  'mall.stock.read',
  'mall.stock.write',
  'mall.files.read',
  'mall.files.write',
  'mall.orders.read',
  'mall.orders.write',
  'mall.shipments.write',
  'mall.fulfillment.release',
  'mall.invoices.read',
  'mall.invoices.write',
  'mall.billing.release',
  'mall.aftersales.read',
  'mall.aftersales.review',
  'mall.returns.receive',
  'mall.payments.read',
  'mall.payments.query',
  'mall.refunds.read',
  'mall.refunds.query',
  'mall.refunds.execute',
  'mall.finance.export',
  'mall.reconciliations.read',
  'mall.reconciliations.write',
  'mall.settings.read',
  'mall.settings.write',
  'mall.attribution.write',
]

let pinia
let authStore

beforeEach(async () => {
  pinia = createPinia()
  setActivePinia(pinia)
  authStore = useAuthStore()
  authStore.token = 'test-admin-token'
  authStore.user = { username: 'mall-test-admin' }
  authStore.permissions = []
  await router.push('/')
})

function mountApp() {
  return mount(App, { global: { plugins: [pinia, ElementPlus, router] } })
}

it('keeps the mall permission catalog scoped to the independent mall modules', () => {
  const mallPermissions = PERMISSION_MODULES
    .filter((module) => module.module.startsWith('mall_'))
    .flatMap((module) => module.permissions.map((permission) => permission.key))
    .sort()

  expect(mallPermissions).toEqual([...EXPECTED_MALL_PERMISSIONS].sort())
  expect(new Set(ALL_PERMISSION_KEYS).size).toBe(ALL_PERMISSION_KEYS.length)
  expect(ALL_PERMISSION_KEYS).toEqual(expect.arrayContaining(EXPECTED_MALL_PERMISSIONS))
  const fulfillmentPermission = PERMISSION_MODULES
    .find((module) => module.module === 'mall_fulfillment')
    .permissions.find((permission) => permission.key === 'mall.fulfillment.release')
  expect(fulfillmentPermission.label).toContain('G-DATA未生效时仍拒绝')
  expect(PERMISSION_MODULES.some((module) => module.module === 'mall_marketing')).toBe(false)
  expect(PERMISSION_MODULES.some((module) => module.module === 'mall_statistics')).toBe(false)
  expect(PERMISSION_MODULES.some((module) => module.module === 'mall_customer_service')).toBe(false)
})

it('hides mall navigation after revocation and blocks a bookmarked mall route', async () => {
  authStore.permissions = ['mall.orders.read']
  const wrapper = mountApp()
  await flushPromises()

  const sidebar = wrapper.find('.app-sidebar')
  expect(sidebar.text()).toContain('商城管理')
  expect(sidebar.text()).toContain('商城工作台')
  expect(sidebar.text()).toContain('交易订单')
  expect(sidebar.text()).not.toContain('支付订单')
  expect(sidebar.text()).not.toContain('退款订单')

  authStore.permissions = []
  await nextTick()
  expect(sidebar.text()).not.toContain('商城管理')

  await router.push('/mall/orders')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('Dashboard')
  wrapper.unmount()
})

it('protects each current mall screen with a permission gate', () => {
  const mallRoutes = router.getRoutes().filter((route) => route.path.startsWith('/mall/'))
  expect(mallRoutes).toHaveLength(13)
  for (const route of mallRoutes) {
    expect(route.meta.permission || route.meta.permissionAny).toBeTruthy()
  }
})

