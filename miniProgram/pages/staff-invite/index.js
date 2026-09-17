const staffInviteService = require('../../services/staff-invite-service')
const { getCurrentSession } = require('../../services/session-service')
const { hasCapability } = require('../../models/collaborator')

Page({
  data: { state: 'loading', stateMessage: '', invite: {}, saving: false, qrState: 'loading', qrRetryCount: 0 },
  onLoad() {
    if (!hasCapability(getCurrentSession(), 'staffInvite')) {
      this.setData({ state: 'forbidden', stateMessage: '只有组织管理员可以发展客户顾问' })
      return
    }
    this.loadInvite()
  },
  async loadInvite() {
    try { this.setData({ state: 'loading', qrState: 'loading', qrRetryCount: 0 }); const invite = await staffInviteService.getMyInviteCode(); this.setData({ state: 'success', invite, qrState: 'loading' }) }
    catch (error) { this.setData({ state: error.kind === 'FORBIDDEN' ? 'forbidden' : 'error', stateMessage: error.message || '加入码加载失败' }) }
  },
  async refreshInvite(options = {}) { if (this.data.saving) return; const silent = options.silent === true; this.setData({ saving: true, qrState: 'loading', ...(silent ? {} : { qrRetryCount: 0 }) }); try { const invite = await staffInviteService.refreshMyInviteCode(); this.setData({ invite, state: 'success', qrState: 'loading' }); if (!silent) wx.showToast({ title: '加入码已刷新', icon: 'success' }) } catch (error) { this.setData({ qrState: 'error', stateMessage: error.message || '加入码刷新失败' }); if (!silent) wx.showToast({ title: error.message || '刷新失败', icon: 'none' }) } finally { this.setData({ saving: false }) } },
  handleQrLoad() { this.setData({ qrState: 'ready' }) },
  handleQrError() { if (this.data.saving) return; if (this.data.qrRetryCount < 1) { this.setData({ qrRetryCount: 1 }); this.refreshInvite({ silent: true }); return } this.setData({ qrState: 'error', stateMessage: '加入码图片加载失败，请点击下方按钮重新生成' }) },
  async revokeInvite() { const modal = await new Promise((resolve) => wx.showModal({ title: '停用加入码', content: '停用后已分享的二维码将无法继续使用。', confirmText: '确认停用', success: resolve })); if (!modal.confirm) return; try { await staffInviteService.revokeMyInviteCode(); this.setData({ state: 'revoked' }); wx.showToast({ title: '已停用', icon: 'success' }) } catch (error) { wx.showToast({ title: error.message || '停用失败', icon: 'none' }) } },
  handleBack() { wx.navigateBack({ delta: 1 }) },
  onShareAppMessage() { return { title: `${this.data.invite.inviterName || '组织管理员'}邀请你加入${this.data.invite.organizationName || '儒泰医联'}`, path: this.data.invite.sharePath, imageUrl: this.data.invite.qrImageUrl } }
})
