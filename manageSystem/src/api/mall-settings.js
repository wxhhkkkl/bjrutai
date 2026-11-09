import http from './http'

const unwrap = (response) => response.data?.data ?? response.data

export const getMallWorkbench = () =>
  http.get('/admin/mall/workbench').then(unwrap)

export const getMallSettings = () =>
  http.get('/admin/mall/settings').then(unwrap)

export const getMallCheckoutSettings = () =>
  http.get('/mall/checkout/settings').then(unwrap)

export const saveMallSettings = (body, key) =>
  http
    .patch('/admin/mall/settings', body, {
      headers: { 'Idempotency-Key': key },
    })
    .then(unwrap)
