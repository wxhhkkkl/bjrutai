const BINDING_SUMMARY = [
  {
    id: 'bound',
    label: '已绑定',
    count: 32,
    icon: 'contact-o',
    tone: 'green'
  },
  {
    id: 'matching',
    label: '待匹配',
    count: 3,
    icon: 'clock-o',
    tone: 'blue'
  },
  {
    id: 'processing',
    label: '处理中',
    count: 1,
    icon: 'replay',
    tone: 'orange'
  }
];

const BINDING_FILTERS = [
  { id: 'all', label: '全部', count: 36 },
  ...BINDING_SUMMARY.map(({ id, label, count }) => ({ id, label, count }))
];

const BINDING_RECORDS = [
  {
    id: 'binding-001',
    name: '王女士',
    phone: '138****1028',
    idCard: '1101********1234',
    status: 'bound',
    statusLabel: '已绑定',
    statusIcon: 'link-o',
    tone: 'green',
    note: '绑定时间：7月18日 10:30',
    detail: '',
    submittedAt: '2026年7月22日 10:30'
  },
  {
    id: 'binding-002',
    name: '李先生',
    phone: '186****3681',
    idCard: '2301********3681',
    status: 'matching',
    statusLabel: '待匹配',
    statusIcon: 'clock-o',
    tone: 'blue',
    note: '已提交，系统持续匹配',
    detail: '无需重复提交',
    submittedAt: '2026年7月22日 10:30'
  },
  {
    id: 'binding-003',
    name: '刘女士',
    phone: '159****2650',
    idCard: '2301********2650',
    status: 'processing',
    statusLabel: '处理中',
    statusIcon: 'replay',
    tone: 'orange',
    note: '接口异常，系统自动重试中',
    detail: '第1次重试 · 10分钟后',
    submittedAt: '2026年7月22日 10:30'
  },
  {
    id: 'binding-004',
    name: '赵先生',
    phone: '137****9186',
    idCard: '1101********9186',
    status: 'bound',
    statusLabel: '已绑定',
    statusIcon: 'link-o',
    tone: 'green',
    note: '绑定时间：7月15日 16:42',
    detail: '',
    submittedAt: '2026年7月15日 16:42'
  }
];

function filterBindingRecords(records, status, keyword) {
  const normalizedKeyword = String(keyword || '').trim().toLowerCase();

  return records.filter((record) => {
    const matchesStatus = status === 'all' || record.status === status;
    const searchableText = [
      record.name,
      record.phone,
      record.idCard
    ].join(' ').toLowerCase();

    return matchesStatus
      && (!normalizedKeyword || searchableText.includes(normalizedKeyword));
  });
}

function sortBindingRecords(records, mode) {
  const result = records.slice();

  if (mode === 'name') {
    result.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
  } else if (mode === 'status') {
    const order = { processing: 0, matching: 1, bound: 2 };

    result.sort((left, right) => order[left.status] - order[right.status]);
  }

  return result;
}

module.exports = {
  BINDING_SUMMARY,
  BINDING_FILTERS,
  BINDING_RECORDS,
  filterBindingRecords,
  sortBindingRecords
};
