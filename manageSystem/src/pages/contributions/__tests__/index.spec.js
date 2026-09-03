import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

import ContributionsPage from '../index.vue'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/org', () => ({
  orgApi: { getTree: vi.fn().mockResolvedValue({ tree: [] }) },
}))

vi.mock('@/api/contributions', () => ({
  contributionDashboardApi: {
    dashboard: vi.fn().mockResolvedValue({
      stats: { monthlyAmountCent: 12880, totalAmountCent: 12880, personCount: 1, boundUserCount: 1 },
      trend: [{ month: '2026-09', amountCent: 12880 }],
      latest: [{
        id: '901',
        customerName: '消费客户',
        phoneMasked: '138****1234',
        personName: '李明',
        orgName: '测试机构',
        title: 'MANUAL-20260902-A1B2C3D4',
        amountCent: 12880,
        status: 'paid',
        source: 'manual',
        occurredAt: '2026-09-02T08:30:00Z',
      }],
    }),
    orgsRanking: vi.fn().mockResolvedValue({ items: [] }),
    personsRanking: vi.fn().mockResolvedValue({ items: [] }),
    bindingsRanking: vi.fn().mockResolvedValue({ items: [] }),
    searchCustomers: vi.fn().mockResolvedValue({ items: [] }),
    createManual: vi.fn(),
  },
}))

function mountPage(permissions = ['contributions.read', 'contributions.write']) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.permissions = permissions
  return mount(ContributionsPage, {
    global: { plugins: [pinia, ElementPlus] },
  })
}

describe('contributions page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows customer and Chinese source label in latest details', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('消费客户')
    expect(wrapper.text()).toContain('人工录入')
    expect(wrapper.text()).toContain('¥128.80')
  })

  it('shows entry button only with contributions.write permission', async () => {
    const writable = mountPage()
    await flushPromises()
    expect(writable.text()).toContain('录入消费')

    const readonly = mountPage(['contributions.read'])
    await flushPromises()
    expect(readonly.text()).not.toContain('录入消费')
  })
})
