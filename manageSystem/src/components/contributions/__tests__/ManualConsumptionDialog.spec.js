import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import ManualConsumptionDialog from '../ManualConsumptionDialog.vue'
import { contributionDashboardApi } from '@/api/contributions'

vi.mock('@/api/contributions', () => ({
  contributionDashboardApi: {
    searchCustomers: vi.fn(),
    createManual: vi.fn(),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn() },
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})

const customer = {
  customerId: '42',
  customerVersion: 3,
  name: '张三',
  phoneMasked: '138****1234',
  idCardMasked: '110***********1234',
  distributorId: '8',
  personName: '李明',
  orgId: '2',
  orgName: '测试机构',
}

function mountDialog() {
  return mount(ManualConsumptionDialog, {
    props: { modelValue: true },
    global: { plugins: [ElementPlus] },
  })
}

describe('ManualConsumptionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contributionDashboardApi.searchCustomers.mockResolvedValue({ items: [customer] })
    contributionDashboardApi.createManual.mockResolvedValue({ id: '901' })
  })

  it('searches eligible customers and exposes only read-only attribution', async () => {
    const wrapper = mountDialog()
    await wrapper.vm.searchCustomers('138001')
    await wrapper.vm.selectCustomer('42')

    expect(contributionDashboardApi.searchCustomers).toHaveBeenCalledWith({
      keyword: '138001',
      pageSize: 20,
    })
    expect(wrapper.text()).toContain('138****1234')
    expect(wrapper.find('[data-testid="person-name"]').element.value).toBe('李明')
    expect(wrapper.find('[data-testid="org-name"]').element.value).toBe('测试机构')
    expect(wrapper.text()).not.toContain('13800138000')
    expect(wrapper.find('[data-testid="person-name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="org-name"]').attributes('disabled')).toBeDefined()
  })

  it('shows a clear message when no eligible person matches', async () => {
    contributionDashboardApi.searchCustomers.mockResolvedValue({ items: [] })
    const wrapper = mountDialog()

    await wrapper.vm.searchCustomers('不存在的人员')

    const customerSelect = wrapper.findComponent({ name: 'ElSelect' })
    expect(customerSelect.props('noDataText')).toBe('未匹配到有效人员')
    expect(wrapper.vm.customerOptions).toEqual([])
  })

  it('converts yuan to cents, locks duplicate submission, and emits success', async () => {
    let resolveRequest
    contributionDashboardApi.createManual.mockReturnValue(
      new Promise((resolve) => { resolveRequest = resolve })
    )
    const wrapper = mountDialog()
    wrapper.vm.customerOptions = [customer]
    await wrapper.vm.selectCustomer('42')
    wrapper.vm.form.amountYuan = '128.80'
    wrapper.vm.form.consumedAt = new Date(Date.now() - 60_000)
    wrapper.vm.form.note = '线下收款补录'

    const first = wrapper.vm.submit()
    const second = wrapper.vm.submit()
    await vi.waitFor(() => {
      expect(contributionDashboardApi.createManual).toHaveBeenCalledTimes(1)
    })
    const [body, key] = contributionDashboardApi.createManual.mock.calls[0]
    expect(body.amountCent).toBe(12880)
    expect(body.customerId).toBe('42')
    expect(body.customerVersion).toBe(3)
    expect(body.consumedAt).toMatch(/Z$/)
    expect(key).toBeTruthy()

    resolveRequest({ id: '901' })
    await Promise.all([first, second])
    expect(wrapper.emitted('success')).toBeTruthy()
  })

  it('keeps form values when submission fails', async () => {
    contributionDashboardApi.createManual.mockRejectedValue({ userMessage: '网络连接失败' })
    const wrapper = mountDialog()
    wrapper.vm.customerOptions = [customer]
    await wrapper.vm.selectCustomer('42')
    wrapper.vm.form.amountYuan = '88.00'
    wrapper.vm.form.consumedAt = new Date(Date.now() - 60_000)

    await wrapper.vm.submit()

    expect(wrapper.vm.form.amountYuan).toBe('88.00')
    expect(wrapper.vm.selectedCustomer.customerId).toBe('42')
  })
})
