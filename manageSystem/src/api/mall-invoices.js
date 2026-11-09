import http from './http'

const requests = '/admin/mall/invoice-requests'
const files = '/admin/mall/files'
const unwrap = (response) => response.data?.data ?? response.data
const headers = (key) => ({ headers: { 'Idempotency-Key': key } })

export const listAdminMallInvoiceRequests = (params) =>
  http.get(requests, { params }).then(unwrap)
export const getAdminMallInvoiceRequest = (id) =>
  http.get(`${requests}/${id}`).then(unwrap)
export const claimMallInvoice = ({ id, ...body }, key) =>
  http.post(`${requests}/${id}/claim`, body, headers(key)).then(unwrap)
export const releaseMallBilling = ({ id, ...body }, key) =>
  http.post(`${requests}/${id}/billing-release`, body, headers(key)).then(unwrap)
export const needMallInvoiceInfo = ({ id, ...body }, key) =>
  http.post(`${requests}/${id}/needs-info`, body, headers(key)).then(unwrap)
export const recordMallInvoice = ({ id, ...body }, key) =>
  http.post(`${requests}/${id}/record`, body, headers(key)).then(unwrap)
export const markMallRedPending = ({ id, ...body }, key) =>
  http
    .post(`/admin/mall/invoices/${id}/red-pending`, body, headers(key))
    .then(unwrap)
export const recordMallRedInvoice = ({ id, ...body }, key) =>
  http
    .post(`/admin/mall/invoices/${id}/red-record`, body, headers(key))
    .then(unwrap)
export const replaceMallInvoiceFile = ({ id, ...body }, key) =>
  http.patch(`/admin/mall/invoices/${id}/file`, body, headers(key)).then(unwrap)
export const getAdminMallInvoiceFileAccess = (fileId) =>
  http.get(`${files}/${fileId}/access`).then(unwrap)

export function createInvoicePdfUploadState(file, orderId) {
  return {
    file,
    orderId: String(orderId),
    ticketKey: crypto.randomUUID(),
    verifyKey: crypto.randomUUID(),
    ticket: null,
    uploaded: false,
    sha256: null,
  }
}

export async function uploadInvoicePdf(state) {
  const { file } = state
  if (
    !file ||
    file.type !== 'application/pdf' ||
    file.size < 1 ||
    file.size > 10 * 1024 * 1024
  ) {
    throw new Error('请选择不超过 10 MB 的 PDF 发票文件')
  }
  if (!state.sha256) {
    const digest = await crypto.subtle.digest(
      'SHA-256',
      await file.arrayBuffer()
    )
    state.sha256 = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, '0')
    ).join('')
  }
  if (!state.ticket) {
    state.ticket = await http
      .post(
        `${files}/upload-ticket`,
        {
          purpose: 'invoice_pdf',
          orderId: state.orderId,
          fileName: file.name,
          contentType: file.type,
          fileSize: file.size,
          sha256: state.sha256,
        },
        headers(state.ticketKey)
      )
      .then(unwrap)
  }
  if (!state.uploaded) {
    const url = new URL(state.ticket.uploadUrl)
    if (url.protocol !== 'https:') throw new Error('上传地址不安全')
    const response = await fetch(url.href, {
      method: 'PUT',
      credentials: 'omit',
      redirect: 'error',
      headers: { 'Content-Type': file.type },
      body: file,
    })
    if (!response.ok) throw new Error('发票文件上传失败，请重试')
    state.uploaded = true
  }
  return http
    .post(
      `${files}/${state.ticket.fileId}/verify`,
      null,
      headers(state.verifyKey)
    )
    .then(unwrap)
}
