const { request } = require('./request-service')
function getPromotionCode() { return request('/api/v1/promotion-code') }
function refreshPromotionCode() { return request('/api/v1/promotion-code/refresh', { method: 'POST' }) }
function getStatistics(period = '30d') { return request('/api/v1/promotion-code/statistics', { data: { period } }) }
function getPoster() { return request('/api/v1/promotion-code/poster') }
module.exports = { getPromotionCode, refreshPromotionCode, getStatistics, getPoster }
