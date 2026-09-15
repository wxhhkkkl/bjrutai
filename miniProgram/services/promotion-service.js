const { request } = require('./request-service')
const { formatChinaDateTime } = require('../utils/date-time')

function resolveBindingImageUrl(refToken, apiBase) {
  const token = String(refToken || '').trim()
  const base = String(apiBase || '').trim().replace(/\/+$/, '')
  if (!token || !base) return ''
  return `${base}/api/v1/customer-binding-codes/${encodeURIComponent(token)}/image`
}

function extractRefToken(path) {
  const match = /[?&]refToken=([^&]+)/.exec(String(path || ''))
  return match ? decodeURIComponent(match[1]) : ''
}

function formatPromotionExpiry(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const withTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`
  return formatChinaDateTime(withTimezone)
}

function getApiBase() {
  if (typeof getApp === 'undefined') return ''
  const app = getApp()
  return app && app.globalData ? app.globalData.apiBase : ''
}

function normalizePromotion(value) {
  if (!value) return value
  const refToken = value.refToken || extractRefToken(value.sharePath)
  const imageUrl = resolveBindingImageUrl(refToken, getApiBase()) || value.qrImageUrl || value.posterUrl || ''
  return {
    ...value,
    qrImageUrl: imageUrl,
    posterUrl: value.posterUrl ? imageUrl : value.posterUrl,
    expiresAtDisplay: formatPromotionExpiry(value.expiresAt)
  }
}

function getPromotionCode() { return request('/api/v1/promotion-code').then(normalizePromotion) }
function refreshPromotionCode() { return request('/api/v1/promotion-code/refresh', { method: 'POST' }).then(normalizePromotion) }
function getStatistics(period = '30d') { return request('/api/v1/promotion-code/statistics', { data: { period } }) }
function getPoster() { return request('/api/v1/promotion-code/poster').then(normalizePromotion) }
module.exports = { getPromotionCode, refreshPromotionCode, getStatistics, getPoster, resolveBindingImageUrl, formatPromotionExpiry, normalizePromotion }
