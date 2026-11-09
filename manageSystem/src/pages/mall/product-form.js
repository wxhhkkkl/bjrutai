export function toCent(value) {
  const input = String(value).trim()
  if (!/^\d+(\.\d{1,2})?$/.test(input))
    throw new Error('价格须为正数，最多两位小数')
  const [whole, fraction = ''] = input.split('.')
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  if (result < 1n || result > BigInt(Number.MAX_SAFE_INTEGER))
    throw new Error('价格超出范围')
  return Number(result)
}
export function money(cent) {
  const amount = BigInt(cent || 0)
  return `${amount / 100n}.${String(amount % 100n).padStart(2, '0')}`
}
export const blankSku = () => ({
  skuCode: '',
  price: '',
  initialStock: 0,
  warningQuantity: 0,
  options: [],
})
export function productForm(product = {}) {
  return {
    ...product,
    name: product.name || '',
    summary: product.summary || '',
    categoryId: product.categoryId || null,
    coverFileId: product.coverFileId || null,
    galleryFileIds: [...(product.galleryFileIds || [])],
    description: product.description || '',
    instructions: product.instructions || '',
    sort: product.sort || 0,
    skus: (product.skus?.length ? product.skus : [blankSku()]).map((sku) => ({
      ...sku,
      price: sku.priceCent ? money(sku.priceCent) : '',
      options: sku.options.map((o) => ({ ...o })),
    })),
  }
}
export function productPayload(form) {
  if (!form.name?.trim()) throw new Error('请填写商品名称')
  const body = {
    name: form.name.trim(),
    summary: form.summary || '',
    categoryId: form.categoryId || null,
    coverFileId: form.coverFileId || null,
    galleryFileIds: form.galleryFileIds || [],
    description: form.description || '',
    instructions: form.instructions || '',
    sort: form.sort || 0,
  }
  const skus = (form.skus || []).filter(
    (sku) =>
      sku.id ||
      sku.skuCode ||
      sku.price ||
      sku.options.length ||
      sku.initialStock ||
      sku.warningQuantity
  )
  if (skus.length) {
    body.skus = skus.map((sku) => {
      if (!sku.skuCode?.trim()) throw new Error('请填写每个规格的 SKU 编码')
      return {
        ...(sku.id ? { id: sku.id } : { initialStock: sku.initialStock || 0 }),
        skuCode: sku.skuCode.trim(),
        priceCent: toCent(sku.price),
        warningQuantity: sku.warningQuantity || 0,
        options: sku.options.map((o) => ({
          name: o.name.trim(),
          value: o.value.trim(),
        })),
      }
    })
  }
  return body
}
