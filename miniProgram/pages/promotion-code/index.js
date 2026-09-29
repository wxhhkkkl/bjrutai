const promotionService = require('../../services/promotion-service')
const { PROMOTION_STEPS, createPromotionShare } = require('../../models/promotion-code')
const { getCurrentSession } = require('../../services/session-service')

function getApiDomain() {
  try {
    const apiBase = getApp().globalData.apiBase || ''
    const match = /^(https?:\/\/[^/]+)/i.exec(String(apiBase))
    return match ? match[1] : ''
  } catch (error) {
    return ''
  }
}

function isAlbumPermissionError(error) {
  const message = String(error && (error.errMsg || error.message) || error || '')
  return /auth\s*den(y|ied)|authorize\s*fail|scope\.writePhotosAlbum|permission denied/i.test(message)
}

function isDownloadDomainError(error) {
  const message = String(error && (error.errMsg || error.message) || error || '')
  return /url not in domain list|domain.{0,30}(not configured|not in|missing)/i.test(message)
}

Page({
  data: { state: 'loading', stateMessage: '', profile: {}, statistics: {}, steps: PROMOTION_STEPS, saving: false, qrState: 'loading', qrRetryCount: 0 },
  onLoad() { this.loadPromotion() },
  async loadPromotion(options = {}) { const silent = options.silent === true; try { this.setData({ state: 'loading', stateMessage: '', qrState: 'loading', ...(silent ? {} : { qrRetryCount: 0 }) }); const code = await promotionService.getPromotionCode(); const [statistics, poster] = await Promise.all([promotionService.getStatistics('30d'), promotionService.getPoster()]); const session = getCurrentSession(); const value = promotionService.normalizePromotion({ ...code, ...(poster || {}) }); Object.assign(value, { id: code.promotionCodeId, name: code.name || session.name || '', roleLabel: session.orgRole === 'admin' ? '客户顾问（组织管理员）' : '客户顾问', statusLabel: code.statusLabel || '客户绑定码可用', sourceCity: '北京', qrImage: value.posterUrl || value.qrImageUrl || '' }); this.setData({ state: 'success', profile: value, statistics: statistics || {}, qrState: 'loading' }) } catch (error) { this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error', stateMessage: error.message || '客户绑定码暂不可用', qrState: 'error' }); } },
  retry() { this.loadPromotion() },
  async refreshPromotionCode(options = {}) { if (this.data.saving) return; const silent = options.silent === true; this.setData({ saving: true, qrState: 'loading', ...(silent ? {} : { qrRetryCount: 0 }) }); try { await promotionService.refreshPromotionCode(); if (!silent) wx.showToast({ title: '推广码已刷新', icon: 'success' }); await this.loadPromotion({ silent }) } catch (error) { this.setData({ qrState: 'error', stateMessage: error.message || '推广码刷新失败' }); if (!silent) wx.showToast({ title: error.message || '推广码刷新失败', icon: 'none' }) } finally { this.setData({ saving: false }) } },
  handleQrLoad() { this.setData({ qrState: 'ready' }) },
  handleQrError() { if (this.data.saving) return; if (this.data.qrRetryCount < 1) { this.setData({ qrRetryCount: 1 }); this.refreshPromotionCode({ silent: true }); return } this.setData({ qrState: 'error', stateMessage: '客户绑定码图片加载失败，请点击下方按钮重新生成' }) },
  handleBack() { if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 }); else wx.switchTab({ url: '/pages/profile/index' }) },
  async savePromotionCode() {
    const url = this.data.profile.qrImage
    if (!url) {
      wx.showToast({ title: '客户绑定码暂未生成', icon: 'none' })
      return
    }

    this.setData({ saving: true })
    let stage = 'download'
    try {
      const file = await new Promise((resolve, reject) => wx.downloadFile({
        url,
        success: resolve,
        fail: reject
      }))
      const statusCode = Number(file && file.statusCode) || 0
      if (statusCode < 200 || statusCode >= 300 || !file.tempFilePath) {
        throw new Error(`图片下载失败（HTTP ${statusCode || '未知'}）`)
      }

      stage = 'album'
      await new Promise((resolve, reject) => wx.saveImageToPhotosAlbum({
        filePath: file.tempFilePath,
        success: resolve,
        fail: reject
      }))
      wx.showToast({ title: '已保存到相册', icon: 'success' })
    } catch (error) {
      if (stage === 'download' && isDownloadDomainError(error)) {
        const domain = getApiDomain()
        const domainHint = domain ? `（${domain}）` : ''
        wx.showModal({
          title: '图片下载域名未配置',
          content: `请联系小程序管理员在微信公众平台「开发管理-开发设置-服务器域名」中，将图片接口域名${domainHint}加入 downloadFile 合法域名后重试。`,
          showCancel: false,
          confirmText: '知道了'
        })
      } else if (stage === 'album' && isAlbumPermissionError(error)) {
        wx.showModal({
          title: '需要相册权限',
          content: '请在设置中允许保存图片到相册后重试',
          confirmText: '去设置',
          success: (result) => { if (result.confirm) wx.openSetting({}) }
        })
      } else {
        wx.showToast({
          title: stage === 'download' ? '二维码下载失败，请检查网络后重试' : '保存到相册失败，请检查相册权限',
          icon: 'none'
        })
      }
    } finally {
      this.setData({ saving: false })
    }
  },
  onShareAppMessage() { return createPromotionShare(this.data.profile) },
  onShareTimeline() { const share = createPromotionShare(this.data.profile); return { query: share.path.split('?')[1] || '', imageUrl: share.imageUrl } }
})
