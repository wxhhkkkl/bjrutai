export function toCent(value) {
  const input = String(value ?? '').trim()
  if (!input) throw new Error('销售价必填')
  if (!/^\d+(\.\d{1,2})?$/.test(input))
    throw new Error('销售价须为正数，最多两位小数')
  const [whole, fraction = ''] = input.split('.')
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  if (result < 1n || result > BigInt(Number.MAX_SAFE_INTEGER))
    throw new Error('销售价超出范围')
  return Number(result)
}
export function toOptionalCent(value, label = '成本价') {
  const input = String(value ?? '').trim()
  if (!input) return null
  if (!/^\d+(\.\d{1,2})?$/.test(input))
    throw new Error(`${label}须为非负数，最多两位小数`)
  const [whole, fraction = ''] = input.split('.')
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  if (result > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error(`${label}超出范围`)
  return Number(result)
}
export function money(cent) {
  const amount = BigInt(cent || 0)
  return `${amount / 100n}.${String(amount % 100n).padStart(2, '0')}`
}
export const specLabel = (sku) =>
  sku.options?.map((option) => option.value).filter(Boolean).join(' / ') || '默认规格'

function newSpecCode() {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16))
  return 'SPEC-' + Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export const blankSku = () => ({
  skuCode: '',
  barcode: '',
  price: '',
  marketPrice: '',
  costPrice: '',
  initialStock: 0,
  warningQuantity: 0,
  options: [],
})
export function productForm(product = {}) {
  return {
    ...product,
    productType:
      product.productType ||
      (product.deliveryMethod === 'virtual' ? 'virtual' : 'physical'),
    name: product.name || '',
    supportsReturn: product.supportsReturn ?? true,
    returnInstructions: product.returnInstructions || '',
    summary: product.summary || '',
    categoryId: product.categoryId || null,
    coverFileId: product.coverFileId || null,
    galleryFileIds: [...(product.galleryFileIds || [])],
    description: product.description || '',
    instructions: product.instructions || '',
    sort: product.sort || 0,
    skus: (product.skus?.length ? product.skus : [blankSku()]).map((sku) => ({
      ...sku,
      barcode: sku.barcode ?? '',
      price: sku.priceCent ? money(sku.priceCent) : '',
      marketPrice: sku.marketPriceCent == null ? '' : money(sku.marketPriceCent),
      costPrice: sku.costPriceCent == null ? '' : money(sku.costPriceCent),
      options: sku.options.map((o) => ({ ...o })),
    })),
  }
}
export function productPayload(form) {
  if (!form.name?.trim()) throw new Error('请填写商品名称')
  const body = {
    name: form.name.trim(),
    productType: form.productType || 'physical',
    supportsReturn: form.supportsReturn ?? true,
    returnInstructions: (form.returnInstructions || '').trim(),
    summary: form.summary || '',
    categoryId: form.categoryId || null,
    coverFileId: form.coverFileId || null,
    galleryFileIds: form.galleryFileIds || [],
    description: form.description || '',
    instructions: form.instructions || '',
    sort: form.sort || 0,
    ...(form.deliveryMethod ? {
      deliveryMethod: form.deliveryMethod,
      freightTemplateId: form.deliveryMethod === 'express' ? form.freightTemplateId : null,
    } : {}),
  }
  const skus = (form.skus || []).filter(
    (sku) =>
      sku.id ||
      sku.barcode?.trim() ||
      sku.price ||
      sku.marketPrice ||
      sku.costPrice ||
      sku.options.length ||
      sku.initialStock ||
      sku.warningQuantity
  )
  if (skus.length) {
    body.skus = skus.map((sku) => {
      const priceCent = toCent(sku.price)
      const options = sku.options.map((o) => ({
        name: o.name.trim(),
        value: o.value.trim(),
      }))
      if (options.some((option) => !option.value)) throw new Error('请填写规格名称或规格值')
      if (!options.length && skus.length > 1) {
        options.push({ name: '规格', value: '默认规格' })
      }
      if (!sku.skuCode) sku.skuCode = newSpecCode()
      return {
        ...(sku.id ? { id: sku.id } : { initialStock: sku.initialStock || 0 }),
        skuCode: sku.skuCode.trim(),
        barcode: sku.barcode?.trim() || null,
        priceCent,
        marketPriceCent: toOptionalCent(sku.marketPrice, '市场价'),
        costPriceCent: toOptionalCent(sku.costPrice),
        warningQuantity: sku.warningQuantity || 0,
        options,
      }
    })
  }
  return body
}
