import http from './http'

const root = '/admin/mall'
const unwrap = (response) => response.data?.data ?? response.data
const headers = (key) => ({ headers: { 'Idempotency-Key': key } })
export const listCategories = (params) =>
  http.get(`${root}/categories`, { params }).then(unwrap)
export const listProducts = (params) =>
  http.get(`${root}/products`, { params }).then(unwrap)
export const getProduct = (id) =>
  http.get(`${root}/products/${id}`).then(unwrap)
export function saveCategory({ id, expectedVersion, category }, key) {
  return (
    id
      ? http.patch(
          `${root}/categories/${id}`,
          { expectedVersion, category },
          headers(key)
        )
      : http.post(`${root}/categories`, category, headers(key))
  ).then(unwrap)
}
export function saveProduct({ id, expectedVersion, product }, key) {
  return (
    id
      ? http.patch(
          `${root}/products/${id}`,
          { expectedVersion, product },
          headers(key)
        )
      : http.post(`${root}/products`, product, headers(key))
  ).then(unwrap)
}
export const setProductStatus = ({ id, ...body }, key) =>
  http.post(`${root}/products/${id}/status`, body, headers(key)).then(unwrap)
export const adjustStock = ({ id, ...body }, key) =>
  http
    .post(`${root}/skus/${id}/stock-adjustments`, body, headers(key))
    .then(unwrap)
export const listStockMovements = (id, params) =>
  http.get(`${root}/skus/${id}/stock-movements`, { params }).then(unwrap)

export async function uploadProductImage(state) {
  const file = state.file
  if (
    !['image/jpeg', 'image/png'].includes(file.type) ||
    file.size < 1 ||
    file.size > 5242880
  ) {
    throw new Error('请选择不超过 5 MB 的 JPG 或 PNG 图片')
  }
  if (state.result) return state.result
  const form = new FormData()
  form.append('file', file, file.name)
  state.result = await http
    .post(`${root}/products/images`, form, {
      headers: { 'Content-Type': undefined },
    })
    .then(unwrap)
  return state.result
}

export const listFreightTemplateOptions = () =>
  http.get(`${root}/freight-template-options`).then(unwrap)
