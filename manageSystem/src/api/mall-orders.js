import http from './http'

const root = '/admin/mall/orders'
const unwrap = (response) => response.data?.data ?? response.data
const headers = (key) => ({ headers: { 'Idempotency-Key': key } })
export const listOrders = (params) => http.get(root, { params }).then(unwrap)
export const getOrder = (id) => http.get(`${root}/${id}`).then(unwrap)
export const saveNote = ({ id, ...body }, key) =>
  http.patch(`${root}/${id}/note`, body, headers(key)).then(unwrap)
export const cancelOrder = ({ id, ...body }, key) =>
  http.post(`${root}/${id}/cancel`, body, headers(key)).then(unwrap)
export const registerShipment = ({ id, ...body }, key) =>
  http.post(`${root}/${id}/ship`, body, headers(key)).then(unwrap)
export const releaseFulfillment = ({ id, ...body }, key) =>
  http
    .post(`${root}/${id}/fulfillment-release`, body, headers(key))
    .then(unwrap)
export const correctTracking = ({ shipmentId, ...body }, key) =>
  http.patch(`/admin/mall/shipments/${shipmentId}`, body, headers(key)).then(unwrap)
export const recordPlatformShipmentReport = ({ shipmentId, ...body }, key) =>
  http
    .post(`/admin/mall/shipments/${shipmentId}/platform-report`, body, headers(key))
    .then(unwrap)
export const getCommand = (id) =>
  http.get(`/admin/mall/commands/${id}`).then(unwrap)
