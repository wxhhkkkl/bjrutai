const {
  getCurrentSession,
  getEntry
} = require('../../services/session-service')
const authService = require('../../services/auth-service')
const workbenchService = require('../../services/workbench-service')
const {
  adaptWorkbench,
  adaptAccountSummary,
  buildProfileViewModel
} = require('../../models/workbench')
const {
  updateTabBar,
  openAction
} = require('../../services/navigation-service')
const {
  getIdentityLabel
} = require('../../models/collaborator')

const SERVICE_ITEMS = [{
  id: 'promote-code',
  title: '我的推广码',
  description: '邀请客户进入儒泰',
  icon: '/assets/images/profile-promo-icon.png'
}, {
  id: 'org-performance',
  title: '组织业绩',
  description: '查看组织消费汇总',
  icon: '/assets/images/profile-contribution-icon.png',
  adminOnly: true
}, {
  id: 'binding-records',
  title: '绑定记录',
  description: '查看客户绑定状态',
  icon: '/assets/images/profile-records-icon.png'
}, {
  id: 'contribution-detail',
  title: '消费明细',
  description: '查看每笔消费来源',
  icon: '/assets/images/profile-contribution-icon.png'
}, {
  id: 'article-list',
  title: '文章资讯',
  description: '阅读最新内容',
  icon: '/assets/images/profile-article-icon.png'
}]

const ACCOUNT_ITEMS = [{
  id: 'profile',
  title: '账号信息',
  icon: '/assets/images/profile-account-icon.png'
}, {
  id: 'notification',
  title: '消息通知',
  icon: '/assets/images/profile-notification-icon.png'
}, {
  id: 'help-feedback',
  title: '帮助与反馈',
  icon: '/assets/images/profile-help-icon.png'
}, {
  id: 'privacy',
  title: '隐私与授权',
  icon: '/assets/images/profile-privacy-icon.png'
}]

function errorState(error) {
  return error && error.kind === 'FORBIDDEN' ? 'forbidden' : 'recoverable-error'
}

Page({
  requestVersion: 0,

  data: {
    state: 'loading',
    stateMessage: '',
    session: {},
    identityLabel: '儒泰协作人员',
    metrics: [],
    serviceItems: SERVICE_ITEMS,
    accountItems: ACCOUNT_ITEMS
  },

  onShow() {
    const session = getCurrentSession()
    const entry = getEntry(session)
    if (entry.type === 'reLaunch') {
      wx.reLaunch({ url: entry.url })
      return
    }

    updateTabBar(this, 'profile')
    this.loadProfile(session)
  },

  onHide() {
    this.requestVersion += 1
  },

  onUnload() {
    this.requestVersion += 1
  },

  async loadProfile(session) {
    const version = ++this.requestVersion
    this.setData({ session, state: 'loading', stateMessage: '' })

    try {
      const [workbenchPayload, accountPayload] = await Promise.all([
        workbenchService.getWorkbench(session.userId),
        workbenchService.getAccountSummary(session.userId)
      ])
      if (version !== this.requestVersion) return

      const workbench = adaptWorkbench(workbenchPayload)
      const account = adaptAccountSummary(accountPayload)
      const displaySession = Object.assign({}, session, {
        userId: account.userId || session.userId,
        name: account.name || session.name,
        avatar: account.avatar || session.avatar
      })
      const accountItems = ACCOUNT_ITEMS.map((item) => Object.assign({}, item))
      const notificationItem = accountItems.find((item) => item.id === 'notification')
      if (notificationItem && account.unreadNotifications > 0) {
        notificationItem.badge = account.unreadNotifications > 99 ? '99+' : String(account.unreadNotifications)
      }

      this.setData({
        state: account.userId ? 'success' : 'empty',
        stateMessage: account.userId ? '' : '暂无账户摘要',
        session: displaySession,
        identityLabel: getIdentityLabel(displaySession),
        serviceItems: SERVICE_ITEMS.filter(
          (item) => !item.adminOnly || session.orgRole === 'admin'
        ),
        accountItems,
        metrics: buildProfileViewModel(workbench)
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.setData({
        state: errorState(error),
        stateMessage: error && error.message ? error.message : '请稍后再试'
      })
    }
  },

  retry() {
    this.loadProfile(getCurrentSession())
  },

  action(e) {
    const result = openAction(
      e.currentTarget.dataset.id,
      this.data.session
    )

    if (result.ok) {
      wx.navigateTo({ url: result.url })
    } else {
      wx.showToast({ title: result.message, icon: 'none' })
    }
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号吗？',
      confirmText: '退出',
      confirmColor: '#ef2929',
      success: async ({ confirm }) => {
        if (!confirm) return

        try {
          await authService.logoutAndClear()
        } catch (error) {
          // logoutAndClear always removes the local real-session state.
        }
        wx.reLaunch({ url: '/pages/auth/login/index' })
      }
    })
  }
})
