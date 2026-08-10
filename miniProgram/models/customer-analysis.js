const CUSTOMER_ANALYSIS_PERIODS = [
  {
    id: 'month',
    label: '近30天',
    addedLabel: '近30天新增',
    added: 12,
    overview: {
      total: 39,
      bound: 36,
      matching: 3,
      unbound: 0,
      followup: 8
    },
    trend: {
      categories: ['第1周', '第2周', '第3周', '第4周'],
      values: [28, 31, 35, 39],
      max: 50,
      interval: 10
    },
    followup: {
      completed: 24,
      pending: 8,
      idle: 7
    },
    sources: [
      { id: 'collaborator', label: '协作人员录入', value: 21, percent: 54 },
      { id: 'code', label: '推广码', value: 18, percent: 46 }
    ]
  },
  {
    id: 'quarter',
    label: '近3月',
    addedLabel: '近3月新增',
    added: 27,
    overview: {
      total: 54,
      bound: 48,
      matching: 6,
      unbound: 0,
      followup: 11
    },
    trend: {
      categories: ['5月', '6月', '7月'],
      values: [27, 42, 54],
      max: 60,
      interval: 10
    },
    followup: {
      completed: 34,
      pending: 11,
      idle: 9
    },
    sources: [
      { id: 'collaborator', label: '协作人员录入', value: 31, percent: 57 },
      { id: 'code', label: '推广码', value: 23, percent: 43 }
    ]
  },
  {
    id: 'year',
    label: '本年',
    addedLabel: '本年新增',
    added: 69,
    overview: {
      total: 96,
      bound: 86,
      matching: 10,
      unbound: 0,
      followup: 18
    },
    trend: {
      categories: ['第一季度', '第二季度', '第三季度', '第四季度'],
      values: [27, 54, 78, 96],
      max: 100,
      interval: 20
    },
    followup: {
      completed: 61,
      pending: 18,
      idle: 17
    },
    sources: [
      { id: 'collaborator', label: '协作人员录入', value: 58, percent: 60 },
      { id: 'code', label: '推广码', value: 38, percent: 40 }
    ]
  }
];

const CUSTOMER_ANALYSIS_TABS = [
  { id: 'month', label: '近30天', apiPeriod: '30d' },
  { id: 'quarter', label: '近3月', apiPeriod: '90d' },
  { id: 'year', label: '本年', apiPeriod: '1y' }
]

function getCustomerAnalysisPeriod(id) {
  return CUSTOMER_ANALYSIS_PERIODS.find((item) => item.id === id)
    || CUSTOMER_ANALYSIS_PERIODS[0];
}

function getBindingDistribution(period) {
  const total = Number(period.overview.total) || 0;
  return [
    {
      name: '已绑定',
      value: period.overview.bound,
      percent: total ? Math.round((period.overview.bound / total) * 100) : 0,
      color: '#14b86a'
    },
    {
      name: '待匹配',
      value: period.overview.matching,
      percent: total ? Math.round((period.overview.matching / total) * 100) : 0,
      color: '#ffb44b'
    },
    {
      name: '未绑定',
      value: period.overview.unbound,
      percent: total ? Math.round((period.overview.unbound / total) * 100) : 0,
      color: '#8b9bb4'
    }
  ];
}

const SOURCE_LABELS = {
  scan: '扫码录入',
  manual: '人工录入',
  share: '分享链接',
  import: '导入'
}

function adaptCustomerAnalysis(payload = {}) {
  const overview = payload.overview || {}
  const trend = Array.isArray(payload.trend) ? payload.trend : []
  const sources = Array.isArray(payload.sourceDistribution) ? payload.sourceDistribution : []
  const total = Number.isSafeInteger(overview.totalCustomers) ? overview.totalCustomers : 0
  const bound = Number.isSafeInteger(overview.boundCustomers) ? overview.boundCustomers : 0
  const matching = Number.isSafeInteger(overview.pendingCustomers) ? overview.pendingCustomers : 0
  const unbound = Number.isSafeInteger(overview.unboundCustomers) ? overview.unboundCustomers : 0
  const followup = Number.isSafeInteger(overview.followupCustomers) ? overview.followupCustomers : 0
  const sourceTotal = sources.reduce((sum, item) => sum + (Number.isSafeInteger(item.count) ? item.count : 0), 0)
  const values = trend.map((item) => Number.isSafeInteger(item.newCustomers) ? item.newCustomers : 0)
  const max = Math.max(10, ...values)
  return {
    id: payload.period === '90d' ? 'quarter' : payload.period === '1y' ? 'year' : 'month',
    label: payload.period || '30d',
    addedLabel: '新增客户',
    added: Number.isSafeInteger(overview.newCustomers) ? overview.newCustomers : 0,
    overview: {
      total,
      bound,
      matching,
      unbound,
      followup
    },
    trend: {
      categories: trend.map((item) => String(item.month || '').slice(5) + '月'),
      values,
      max: Math.ceil(max / 10) * 10,
      interval: Math.max(1, Math.ceil(max / 10))
    },
    followup: { completed: '—', pending: followup, idle: '—' },
    sources: sources.map((item) => ({
      id: String(item.source || ''),
      label: SOURCE_LABELS[item.source] || '其他来源',
      value: Number.isSafeInteger(item.count) ? item.count : 0,
      percent: sourceTotal ? Math.round((item.count / sourceTotal) * 100) : 0
    }))
  }
}

module.exports = {
  CUSTOMER_ANALYSIS_PERIODS,
  CUSTOMER_ANALYSIS_TABS,
  getCustomerAnalysisPeriod,
  getBindingDistribution,
  adaptCustomerAnalysis
};
