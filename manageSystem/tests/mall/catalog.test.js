import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import Categories from '@/pages/mall/categories/index.vue'
import Products from '@/pages/mall/products/index.vue'
import ProductEditor from '@/pages/mall/products/ProductEditor.vue'
import SkuEditor from '@/pages/mall/products/SkuEditor.vue'
import StockPanel from '@/pages/mall/products/StockPanel.vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { toCent, productPayload, productForm } from '@/pages/mall/product-form'

vi.mock('@/api/mall-catalog', () => ({
  listCategories: vi.fn(),
  saveCategory: vi.fn(),
  listProducts: vi.fn(),
  getProduct: vi.fn(),
  saveProduct: vi.fn(),
  setProductStatus: vi.fn(),
  copyProduct: vi.fn(),
  adjustStock: vi.fn(),
  listStockMovements: vi.fn(),
  uploadProductImage: vi.fn(),
}))
const category = {
  id: '1',
  name: '食品',
  parentId: null,
  status: 'enabled',
  sort: 0,
  version: 2,
}
const product = {
  id: '8',
  name: '燕麦',
  status: 'draft',
  version: 3,
  skus: [],
  galleryFileIds: [],
}
function page(
  Component,
  permissions = ['mall.products.read', 'mall.products.write']
) {
  const pinia = createPinia()
  useAuthStore(pinia).permissions = permissions
  return mount(Component, { global: { plugins: [pinia, ElementPlus] } })
}
beforeEach(() => {
  vi.clearAllMocks()
  api.listCategories.mockResolvedValue({ items: [category], nextCursor: null })
  api.listProducts.mockResolvedValue({ items: [product], nextCursor: null })
  api.getProduct.mockResolvedValue(product)
})
describe('catalog administration', () => {
  it('renders real categories and hides mutations from read-only staff', async () => {
    const wrapper = page(Categories, ['mall.products.read'])
    await flushPromises()
    expect(wrapper.text()).toContain('食品')
    expect(wrapper.find('[data-test="new-category"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows a failed read and retries without sample rows', async () => {
    api.listProducts.mockRejectedValueOnce(new Error('暂不可用'))
    const wrapper = page(Products)
    await flushPromises()
    expect(wrapper.text()).toContain('暂不可用')
    await wrapper.get('[data-test="reload"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('燕麦')
    wrapper.unmount()
  })
  it('submits edited category with the loaded version', async () => {
    const wrapper = page(Categories)
    await flushPromises()
    wrapper.vm.edit(category)
    await wrapper.vm.$nextTick()
    wrapper.vm.form.name = '健康食品'
    api.saveCategory.mockResolvedValue({ ...category, version: 3 })
    await wrapper.vm.save()
    expect(api.saveCategory.mock.calls[0][0]).toMatchObject({
      id: '1',
      expectedVersion: 2,
      category: { name: '健康食品' },
    })
    expect(api.saveCategory.mock.calls[0][1].length).toBeGreaterThanOrEqual(16)
    wrapper.unmount()
  })
  it('preserves the command body and key after an unknown network outcome', async () => {
    const command = useMallCommand()
    const send = vi
      .fn()
      .mockRejectedValueOnce(new Error('断网'))
      .mockResolvedValueOnce({ id: '9' })
    const input = { name: '原名称' }
    expect(await command.run(send, input)).toBeNull()
    input.name = '修改名称'
    expect(command.pending.value).toBe(true)
    await command.retry()
    expect(send.mock.calls[1]).toEqual(send.mock.calls[0])
    expect(send.mock.calls[1][0]).toEqual({ name: '原名称' })
    expect(command.pending.value).toBe(false)
  })
  it('blocks double click, but allows correcting a definitive validation failure', async () => {
    const command = useMallCommand()
    let finish
    const send = vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    const first = command.run(send, { name: 'a' })
    await command.run(send, { name: 'b' })
    expect(send).toHaveBeenCalledTimes(1)
    finish({ id: '1' })
    await first
    await command.run(
      vi
        .fn()
        .mockRejectedValue({
          response: { status: 422 },
          userMessage: '正价必填',
        }),
      {}
    )
    expect(command.pending.value).toBe(false)
    expect(command.error.value).toContain('正价必填')
  })
  it('converts exact cents and never resets existing stock while editing price', () => {
    expect(toCent('19.99')).toBe(1999)
    expect(() => toCent('1.005')).toThrow()
    expect(() => toCent('0')).toThrow()
    const body = productPayload({
      name: '商品',
      skus: [
        {
          id: '1',
          skuCode: 'A',
          price: '19.99',
          initialStock: 999,
          options: [],
          warningQuantity: 2,
        },
      ],
    })
    expect(body.skus[0].priceCent).toBe(1999)
    expect(body.skus[0]).not.toHaveProperty('initialStock')
    expect(productPayload({ name: '仅名称草稿', skus: [] })).not.toHaveProperty(
      'skus'
    )
    const draft = productForm({ name: '默认单规格' })
    expect(draft.skus).toHaveLength(1)
    expect(productPayload(draft)).not.toHaveProperty('skus')
  })
  it('retains editable product images, order and SKU warning when saving', async () => {
    const wrapper = page(ProductEditor)
    wrapper.vm.open({
      ...product,
      coverFileId: '7',
      galleryFileIds: ['6'],
      sort: 9,
      skus: [
        {
          id: '1',
          skuCode: 'OAT',
          priceCent: 1999,
          warningQuantity: 8,
          availableQuantity: 3,
          reservedQuantity: 2,
          options: [],
        },
      ],
    })
    await flushPromises()
    const sku = wrapper.findComponent(SkuEditor).props('skus')[0]
    sku.price = '29.99'
    api.saveProduct.mockResolvedValue(product)
    const save = wrapper
      .findAllComponents({ name: 'ElButton' })
      .find((b) => b.text().includes('保存草稿'))
    await save.trigger('click')
    await flushPromises()
    expect(api.saveProduct.mock.calls[0][0]).toMatchObject({
      id: '8',
      expectedVersion: 3,
      product: {
        coverFileId: '7',
        galleryFileIds: ['6'],
        sort: 9,
        skus: [{ id: '1', priceCent: 2999, warningQuantity: 8 }],
      },
    })
    expect(api.saveProduct.mock.calls[0][0].product.skus[0]).not.toHaveProperty(
      'initialStock'
    )
    wrapper.unmount()
  })
  it('adjusts only available stock with version/reason and reloads authoritative quantities', async () => {
    api.listStockMovements.mockResolvedValue({
      items: [{ id: '3', reason: '期初', availableDelta: 3 }],
      nextCursor: null,
    })
    const wrapper = page(StockPanel, [
      'mall.products.read',
      'mall.stock.read',
      'mall.stock.write',
    ])
    const sku = {
      id: '2',
      skuCode: 'A',
      version: 4,
      availableQuantity: 3,
      reservedQuantity: 2,
    }
    await wrapper.vm.open(product, sku)
    await flushPromises()
    wrapper
      .findComponent({ name: 'ElInputNumber' })
      .vm.$emit('update:modelValue', -1)
    wrapper
      .findAllComponents({ name: 'ElInput' })
      .at(-1)
      .vm.$emit('update:modelValue', '盘点修正')
    api.adjustStock.mockResolvedValue({ id: '19' })
    api.getProduct.mockResolvedValue({
      ...product,
      skus: [{ ...sku, availableQuantity: 2, version: 5 }],
    })
    await wrapper
      .findAllComponents({ name: 'ElButton' })
      .find((b) => b.text() === '确认调整')
      .trigger('click')
    await flushPromises()
    expect(api.adjustStock.mock.calls[0][0]).toEqual({
      id: '2',
      expectedVersion: 4,
      deltaAvailableQuantity: -1,
      reason: '盘点修正',
    })
    expect(wrapper.text()).toContain('可售 2 / 待付占用 2')
    wrapper.unmount()
  })
})
