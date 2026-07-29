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

function getCustomerAnalysisPeriod(id) {
  return CUSTOMER_ANALYSIS_PERIODS.find((item) => item.id === id)
    || CUSTOMER_ANALYSIS_PERIODS[0];
}

function getBindingDistribution(period) {
  return [
    {
      name: '已绑定',
      value: period.overview.bound,
      percent: Math.round(
        (period.overview.bound / period.overview.total) * 100
      ),
      color: '#14b86a'
    },
    {
      name: '待匹配',
      value: period.overview.matching,
      percent: Math.round(
        (period.overview.matching / period.overview.total) * 100
      ),
      color: '#ffb44b'
    }
  ];
}

module.exports = {
  CUSTOMER_ANALYSIS_PERIODS,
  getCustomerAnalysisPeriod,
  getBindingDistribution
};
