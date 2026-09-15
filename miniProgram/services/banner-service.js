const { request } = require('./request-service')

function listBanners() {
  return request('/api/v1/banners', { auth: false })
}

module.exports = { listBanners }
