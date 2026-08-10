const { formatYuan } = require('../utils/money')
const { formatChinaDateTime } = require('../utils/date-time')

const BINDING_STATUS_LABELS = Object.freeze({
  pending_match: '待匹配',
  matching: '匹配中',
  bound: '已绑定',
  no_consume: '暂无消费',
  retrying: '重试中',
  manual_review: '人工审核',
  abnormal: '异常',
  unbound: '未绑定',
  transferred: '已转移'
})

function nonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0
}

function amountCent(value) {
  if (value === undefined || value === null) return 0
  if (!Number.isSafeInteger(value)) throw new TypeError('金额必须使用整数分')
  return value
}

function normalizeRole(value) {
  if (value === 'promoter' || value === 'doctor') return 'collaborator'
  if (value === 'admin' || value === 'finance' || value === 'ops') return 'admin'
  return 'unknown'
}

function normalizeNoticeTitle(item) {
  const title = String(item && item.title || '')
  const match = title.match(/^绑定请求\s*[:：]\s*([a-z_]+)$/i)
  if (!match) return title
  return `绑定请求：${BINDING_STATUS_LABELS[match[1].toLowerCase()] || '处理中'}`
}

function adaptWorkbench(payload = {}) {
  const metrics = payload.metrics && typeof payload.metrics === 'object'
    ? payload.metrics
    : {}
  const role = normalizeRole(payload.role)

  if (role === 'admin') {
    return {
      role,
      metrics: {
        totalPromoters: nonNegativeInteger(metrics.totalPromoters),
        totalCustomers: nonNegativeInteger(metrics.totalCustomers),
        abnormalBindings: nonNegativeInteger(metrics.abnormalBindings),
        pendingQualifications: nonNegativeInteger(metrics.pendingQualifications)
      },
      welcomeMessage: String(payload.welcomeMessage || '')
    }
  }

  return {
    role,
    metrics: {
      myCustomers: nonNegativeInteger(metrics.myCustomers),
      myBindings: nonNegativeInteger(metrics.myBindings),
      myMonthlyConsumptionCent: amountCent(metrics.myMonthlyConsumption),
      pendingFollowups: nonNegativeInteger(metrics.pendingFollowups)
    },
    welcomeMessage: String(payload.welcomeMessage || '')
  }
}

function adaptNotices(payload = {}) {
  const notices = Array.isArray(payload.notices) ? payload.notices : []
  return notices.map((item) => ({
    type: String(item && item.type || 'system'),
    title: normalizeNoticeTitle(item),
    summary: String(item && item.summary || ''),
    time: formatChinaDateTime(item && item.time)
  }))
}

function adaptRecentBindings(payload = {}) {
  const items = Array.isArray(payload.items) ? payload.items : []
  return items.map((item) => {
    const statusCode = String(item && item.status || '')
    return {
      id: String(item && item.id || ''),
      name: String(item && item.customerName || '未命名客户'),
      phone: String(item && item.phoneMasked || ''),
      status: BINDING_STATUS_LABELS[statusCode] || '处理中',
      statusCode,
      time: formatChinaDateTime(item && (item.boundAt || item.createdAt))
    }
  })
}

function adaptAccountSummary(payload = {}) {
  return {
    userId: String(payload.userId || ''),
    name: String(payload.name || ''),
    avatar: String(payload.avatar || ''),
    role: String(payload.role || 'unknown'),
    qualificationStatus: String(payload.qualificationStatus || 'unknown'),
    unreadNotifications: nonNegativeInteger(payload.unreadNotifications)
  }
}

function buildHomeViewModel(workbench) {
  const value = workbench || adaptWorkbench()
  const metrics = value.metrics || {}
  if (value.role === 'admin') {
    return {
      monthlyConsumption: '—',
      firstMetricLabel: '推广人员',
      firstMetricValue: String(metrics.totalPromoters || 0),
      secondMetricLabel: '客户总数',
      secondMetricValue: String(metrics.totalCustomers || 0),
      thirdMetricLabel: '异常绑定',
      thirdMetricValue: String(metrics.abnormalBindings || 0)
    }
  }

  return {
    monthlyConsumption: formatYuan(metrics.myMonthlyConsumptionCent || 0),
    firstMetricLabel: '我的客户',
    firstMetricValue: String(metrics.myCustomers || 0),
    secondMetricLabel: '本月绑定',
    secondMetricValue: String(metrics.myBindings || 0),
    thirdMetricLabel: '待跟进',
    thirdMetricValue: String(metrics.pendingFollowups || 0)
  }
}

function buildProfileViewModel(workbench) {
  const value = workbench || adaptWorkbench()
  const metrics = value.metrics || {}
  if (value.role === 'admin') {
    return [
      { label: '推广人员', value: String(metrics.totalPromoters || 0) },
      { label: '客户', value: String(metrics.totalCustomers || 0) },
      { label: '异常绑定', value: String(metrics.abnormalBindings || 0) }
    ]
  }

  return [
    { label: '客户', value: String(metrics.myCustomers || 0) },
    { label: '本月消费', value: formatYuan(metrics.myMonthlyConsumptionCent || 0) },
    { label: '本月绑定', value: String(metrics.myBindings || 0) }
  ]
}

module.exports = {
  adaptWorkbench,
  adaptNotices,
  adaptRecentBindings,
  adaptAccountSummary,
  buildHomeViewModel,
  buildProfileViewModel
}
