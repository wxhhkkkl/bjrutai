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
export const copyProduct = ({ id, expectedVersion }, key) =>
  http
    .post(`${root}/products/${id}/copy`, { expectedVersion }, headers(key))
    .then(unwrap)
export const adjustStock = ({ id, ...body }, key) =>
  http
    .post(`${root}/skus/${id}/stock-adjustments`, body, headers(key))
    .then(unwrap)
export const listStockMovements = (id, params) =>
  http.get(`${root}/skus/${id}/stock-movements`, { params }).then(unwrap)

// Keep this state in the component until completion. Retrying verify never
// reuploads staging bytes or requests another ticket after a lost response.
export async function uploadProductImage(state) {
  const file = state.file
  if (
    !['image/jpeg', 'image/png'].includes(file.type) ||
    file.size < 1 ||
    file.size > 5242880
  ) {
    throw new Error('请选择不超过 5 MB 的 JPG 或 PNG 图片')
  }
  if (!state.ticket) {
    const digest = await crypto.subtle.digest(
      'SHA-256',
      await file.arrayBuffer()
    )
    const sha256 = Array.from(new Uint8Array(digest), (b) =>
      b.toString(16).padStart(2, '0')
    ).join('')
    state.ticket = await http
      .post(
        `${root}/files/upload-ticket`,
        {
          purpose: 'product_image',
          fileName: file.name,
          contentType: file.type,
          fileSize: file.size,
          sha256,
        },
        headers(state.ticketKey)
      )
      .then(unwrap)
  }
  if (!state.uploaded) {
    const url = new URL(state.ticket.uploadUrl)
    if (url.protocol !== 'https:') throw new Error('上传地址不合法')
    const response = await fetch(url.href, {
      method: 'PUT',
      credentials: 'omit',
      redirect: 'error',
      headers: { 'Content-Type': file.type },
      body: file,
    })
    if (!response.ok)
      throw new Error('图片上传失败，请重试；凭证过期时重新选择图片')
    state.uploaded = true
  }
  return http
    .post(
      `${root}/files/${state.ticket.fileId}/verify`,
      null,
      headers(state.verifyKey)
    )
    .then(unwrap)
}
