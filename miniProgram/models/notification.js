const { formatChinaDateTime } = require('../utils/date-time')

const CATEGORY_LABELS = Object.freeze({
  all: '全部',
  system: '系统',
  binding: '客户绑定',
  promotion: '推广',
  bill: '消费',
  followup: '跟进',
  qualification: '资质'
})

function getNotificationFilters(role) {
  const categoryIds = ['all', 'unread', 'system', 'binding', 'bill']
  const visibleIds = role === 'personal'
    ? categoryIds.filter((id) => id !== 'binding' && id !== 'bill')
    : categoryIds
  return visibleIds.map((id) => ({ id, label: id === 'unread' ? '未读' : CATEGORY_LABELS[id] }))
}

const TARGET_PATHS = Object.freeze([
  '/pages/binding-records/index',
  '/pages/customer-detail/index',
  '/pages/customers/index',
  '/pages/contribution-detail/index',
  '/pages/help-feedback/index',
  '/pages/account-profile/index'
])

function resolveNotificationTarget(target) {
  const value = String(target || '').trim()
  if (!value || !value.startsWith('/pages/')) return ''
  const base = value.split('?')[0]
  return TARGET_PATHS.includes(base) ? value : ''
}

function adaptNotifications(payload = {}) {
  const items = Array.isArray(payload.items) ? payload.items : []
  return {
    items: items.map((item) => ({
      id: String(item && item.id || ''),
      category: String(item && item.category || 'system'),
      categoryLabel: CATEGORY_LABELS[String(item && item.category || 'system')] || '通知',
      title: String(item && item.title || '系统通知'),
      summary: String(item && item.summary || ''),
      createdAt: formatChinaDateTime(item && item.createdAt),
      isRead: item && item.isRead === true,
      targetPath: resolveNotificationTarget(item && item.target)
    })),
    unreadCount: Number.isSafeInteger(payload.unreadCount) && payload.unreadCount >= 0 ? payload.unreadCount : 0,
    nextCursor: String(payload.nextCursor || ''),
    hasMore: payload.hasMore === true
  }
}

module.exports = { CATEGORY_LABELS, getNotificationFilters, adaptNotifications, resolveNotificationTarget }
