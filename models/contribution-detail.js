const CONTRIBUTION_MONTHS = [
  {
    id: '2026-07',
    label: '2026年7月',
    total: '12,680',
    totalCount: 12,
    settledCount: 10,
    pendingCount: 2
  },
  {
    id: '2026-06',
    label: '2026年6月',
    total: '10,420',
    totalCount: 10,
    settledCount: 9,
    pendingCount: 1
  },
  {
    id: '2026-05',
    label: '2026年5月',
    total: '9,860',
    totalCount: 9,
    settledCount: 8,
    pendingCount: 1
  }
];

const CONTRIBUTION_RECORDS = [
  {
    id: 'detail-001',
    month: '2026-07',
    date: '7月18日',
    category: 'binding',
    title: '客户绑定成功',
    customer: '王女士',
    phone: '138****1028',
    time: '10:30',
    points: '+1,200',
    status: 'settled',
    statusLabel: '已结算',
    tone: 'green',
    icon: 'contact-o'
  },
  {
    id: 'detail-002',
    month: '2026-07',
    date: '7月16日',
    category: 'service',
    title: '服务包已激活',
    customer: '李先生',
    phone: '186****3156',
    time: '14:20',
    points: '+680',
    status: 'settled',
    statusLabel: '已结算',
    tone: 'green',
    icon: 'certificate'
  },
  {
    id: 'detail-003',
    month: '2026-07',
    date: '7月14日',
    category: 'service',
    title: '完成健康随访',
    customer: '刘女士',
    phone: '139****6721',
    time: '16:30',
    points: '+300',
    status: 'pending',
    statusLabel: '待结算',
    tone: 'orange',
    icon: 'calendar-o'
  },
  {
    id: 'detail-004',
    month: '2026-07',
    date: '7月14日',
    category: 'binding',
    title: '客户绑定成功',
    customer: '陈先生',
    phone: '137****9046',
    time: '09:40',
    points: '+1,020',
    status: 'settled',
    statusLabel: '已结算',
    tone: 'green',
    icon: 'contact-o'
  },
  {
    id: 'detail-005',
    month: '2026-07',
    date: '7月12日',
    category: 'service',
    title: '客户服务完成',
    customer: '赵女士',
    phone: '135****4482',
    time: '11:15',
    points: '+880',
    status: 'settled',
    statusLabel: '已结算',
    tone: 'blue',
    icon: 'friends-o'
  },
  {
    id: 'detail-006',
    month: '2026-06',
    date: '6月28日',
    category: 'binding',
    title: '客户绑定成功',
    customer: '周女士',
    phone: '136****7812',
    time: '15:10',
    points: '+1,000',
    status: 'settled',
    statusLabel: '已结算',
    tone: 'green',
    icon: 'contact-o'
  },
  {
    id: 'detail-007',
    month: '2026-05',
    date: '5月26日',
    category: 'service',
    title: '健康随访完成',
    customer: '吴先生',
    phone: '139****3617',
    time: '09:20',
    points: '+420',
    status: 'pending',
    statusLabel: '待结算',
    tone: 'orange',
    icon: 'calendar-o'
  }
];

function getContributionMonth(id) {
  return CONTRIBUTION_MONTHS.find((item) => item.id === id)
    || CONTRIBUTION_MONTHS[0];
}

function getStatusFilters(month) {
  return [
    { id: 'all', label: '全部', count: month.totalCount },
    { id: 'settled', label: '已结算', count: month.settledCount },
    { id: 'pending', label: '待结算', count: month.pendingCount }
  ];
}

function filterContributionDetails(records, options) {
  const month = options.month;
  const status = options.status || 'all';
  const category = options.category || 'all';

  return records.filter((record) => (
    record.month === month
    && (status === 'all' || record.status === status)
    && (category === 'all' || record.category === category)
  ));
}

function groupContributionDetails(records) {
  const groups = [];

  for (const record of records) {
    const lastGroup = groups[groups.length - 1];

    if (lastGroup && lastGroup.date === record.date) {
      lastGroup.items.push(record);
    } else {
      groups.push({
        date: record.date,
        items: [record]
      });
    }
  }

  return groups;
}

module.exports = {
  CONTRIBUTION_MONTHS,
  CONTRIBUTION_RECORDS,
  getContributionMonth,
  getStatusFilters,
  filterContributionDetails,
  groupContributionDetails
};
