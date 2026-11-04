const sessionService = require('./session-service')
const bindingCodeService = require('./customer-binding-code-service')

const STORAGE_KEY = 'lutai_pending_customer_binding'
const MAX_AGE = 7 * 24 * 60 * 60 * 1000
let resuming = null
let retryAfter = 0
let scanVersion = 0

function clearPendingBinding(expected) {
  if (!expected) {
    scanVersion += 1
    retryAfter = 0
  }
  if (typeof wx === 'undefined' || !wx.removeStorageSync) return
  try {
    const current = wx.getStorageSync(STORAGE_KEY)
    if (expected && (!current || current.refToken !== expected.refToken || current.savedAt !== expected.savedAt)) return
    wx.removeStorageSync(STORAGE_KEY)
  } catch (error) { /* Storage failure must not interrupt login. */ }
}

function getPendingBinding() {
  if (typeof wx === 'undefined' || !wx.getStorageSync) return null
  try {
    const value = wx.getStorageSync(STORAGE_KEY)
    if (!value) return null
    const age = Date.now() - value.savedAt
    if (typeof value.refToken !== 'string' || !value.refToken || typeof value.savedAt !== 'number' || !Number.isFinite(age) || age < 0 || age >= MAX_AGE) {
      clearPendingBinding(value)
      return null
    }
    return value
  } catch (error) { return null }
}

function savePendingBinding(refToken) {
  if (!refToken || typeof wx === 'undefined' || !wx.setStorageSync) return
  try {
    wx.setStorageSync(STORAGE_KEY, { refToken, savedAt: Date.now() })
    retryAfter = 0
  } catch (error) { /* Direct scan binding remains available without storage. */ }
}

async function loadScannedCode(refToken) {
  const version = ++scanVersion
  const info = await bindingCodeService.getCodeInfo(refToken)
  if (version === scanVersion) savePendingBinding(refToken)
  return info
}

function isCurrent(pending, userId) {
  const current = getPendingBinding()
  return current && current.refToken === pending.refToken && current.savedAt === pending.savedAt
    && sessionService.getCurrentSession().userId === userId && sessionService.getAccessToken()
}

async function confirmAndClaim(pending, userId) {
  try {
    const info = await bindingCodeService.getCodeInfo(pending.refToken)
    if (!isCurrent(pending, userId)) return
    const confirmed = await new Promise((resolve, reject) => {
      wx.showModal({
        title: '确认客户归属',
        content: `您曾打开${info.distributorName || '客户顾问'}的客户绑定码。是否授权使用登录手机号，绑定至该客户顾问，由其为您提供服务？`,
        confirmText: '确认绑定',
        cancelText: '暂不绑定',
        success: (result) => resolve(result.confirm === true),
        fail: reject
      })
    })
    if (!isCurrent(pending, userId)) return
    if (!confirmed) {
      clearPendingBinding(pending)
      return
    }
    await bindingCodeService.claimWithSession(pending.refToken)
    clearPendingBinding(pending)
    if (sessionService.getCurrentSession().userId === userId) {
      wx.showToast({ title: '绑定成功', icon: 'success' })
    }
  } catch (error) {
    if (!isCurrent(pending, userId)) return
    const terminal = ['NOT_FOUND', 'VALIDATION', 'FORBIDDEN'].includes(error.kind)
      || [40023, 40024].includes(Number(error.code))
    if (terminal) clearPendingBinding(pending)
    wx.showToast({
      title: terminal ? (error.message || '当前无法绑定，请重新扫码') : '绑定暂未完成，请稍后返回首页重试',
      icon: 'none'
    })
  }
}

function resumePendingBinding() {
  if (resuming) return resuming
  const pending = getPendingBinding()
  if (!pending) return Promise.resolve()
  const session = sessionService.getCurrentSession()
  if (!pending || !session.userId || !sessionService.getAccessToken()) return Promise.resolve()
  if (session.hasBusinessMembership || session.distributorId) {
    clearPendingBinding(pending)
    return Promise.resolve()
  }
  if (Date.now() < retryAfter) return Promise.resolve()
  retryAfter = Date.now() + 60000
  resuming = confirmAndClaim(pending, session.userId).finally(() => { resuming = null })
  return resuming
}

module.exports = { loadScannedCode, savePendingBinding, getPendingBinding, clearPendingBinding, resumePendingBinding }
