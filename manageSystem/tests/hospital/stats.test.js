import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import Stats from '@/pages/hospital/stats.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/hospital-stats'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } }
})
vi.mock('@/api/hospital-stats', () => ({
  getHospitalStats: vi.fn(),
  exportHospitalStats: vi.fn(),
}))

const payload = {
  range: { from: '2026-10-26', to: '2026-11-24' },
  summary: {
    entryTapCount: 12,
    entryTapUsers: 8,
    qrLongpressCount: 6,
    qrLongpressUsers: 5,
    anonymousCount: 1,
    longpressRate: 0.625,
  },
  users: {
    items: [
      {
        userId: '7',
        name: '张力',
        phone: '13800001234',
        userType: 'personal',
        organization: '',
        entryTapCount: 3,
        qrLongpressCount: 2,
        firstAt: '2026-11-24T01:00:00Z',
        lastAt: '2026-11-24T02:00:00Z',
      },
    ],
    total: 1,
    page: 1,
    pageSize: 20,
  },
  daily: [
    {
      date: '2026-11-24',
      entryTapCount: 12,
      entryTapUsers: 8,
      qrLongpressCount: 6,
      qrLongpressUsers: 5,
    },
  ],
}

function page(permissions = ['hospital.stats.read']) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Stats, { global: { plugins: [pinia, ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getHospitalStats.mockResolvedValue(structuredClone(payload))
})

it('renders the metric caveat, summary and unmasked user rows', async () => {
  const wrapper = page()
  await flushPromises()

  expect(api.getHospitalStats).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toMatch(/尝试识别|无法确认/)
  expect(wrapper.text()).toContain('12')
  expect(wrapper.text()).toContain('63%')
  expect(wrapper.text()).toContain('张力')
  expect(wrapper.text()).toContain('13800001234')
  expect(wrapper.text()).toContain('个人用户')
  expect(wrapper.text()).toContain('2026-11-24')
  wrapper.unmount()
})

it('reloads with the applied range and resets to the first page', async () => {
  const wrapper = page()
  await flushPromises()

  wrapper.vm.range = ['2026-11-01', '2026-11-10']
  await wrapper.vm.search()

  expect(api.getHospitalStats.mock.calls[1][0]).toMatchObject({
    from: '2026-11-01',
    to: '2026-11-10',
    page: 1,
    pageSize: 20,
  })
  wrapper.unmount()
})

it('exports the filtered user rows as a CSV download', async () => {
  const wrapper = page()
  await flushPromises()

  api.exportHospitalStats.mockResolvedValue({
    data: new Blob(['序号,用户\n1,张力'], { type: 'text/csv' }),
  })
  const createObjectURL = vi.fn(() => 'blob:mock')
  const revokeObjectURL = vi.fn()
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(() => {})
  const originalCreate = URL.createObjectURL
  const originalRevoke = URL.revokeObjectURL
  URL.createObjectURL = createObjectURL
  URL.revokeObjectURL = revokeObjectURL

  try {
    wrapper.vm.range = ['2026-11-01', '2026-11-10']
    await wrapper.vm.exportUsers()

    expect(api.exportHospitalStats).toHaveBeenCalledWith({
      from: '2026-11-01',
      to: '2026-11-10',
    })
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock')
    expect(click).toHaveBeenCalledTimes(1)
  } finally {
    URL.createObjectURL = originalCreate
    URL.revokeObjectURL = originalRevoke
    click.mockRestore()
    wrapper.unmount()
  }
})
