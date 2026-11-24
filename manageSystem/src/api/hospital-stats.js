import http from './http'

const root = '/admin/hospital'
const unwrap = (response) => response.data?.data ?? response.data

export const getHospitalStats = (params) =>
  http.get(`${root}/stats`, { params }).then(unwrap)

export const exportHospitalStats = (params) =>
  http.get(`${root}/stats/export`, { params, responseType: 'blob' })
