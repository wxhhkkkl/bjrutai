const CUSTOMER_DETAIL_TABS = [
  { id: 'info', label: '客户信息' },
  { id: 'service', label: '服务记录' },
  { id: 'contribution', label: '贡献记录' }
];

const CONTRIBUTION_FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'binding', label: '客户绑定' },
  { id: 'service', label: '服务完成' }
];

const BASE_CUSTOMER_DETAIL = {
  id: 'customer-001',
  name: '王女士',
  phone: '138****1028',
  idCard: '230***********4621',
  medicalAccount: '2301****6820',
  familyPhone: '186****3156',
  boundAt: '2026年7月18日',
  owner: '张小明',
  userId: 'RT****4826',
  totalContribution: '3,200',
  monthlyContribution: '1,880',
  serviceCount: 4,
  followupCount: 1,
  avatar: '/assets/images/customer-avatar-purple.png',
  contributionAvatar: '/assets/images/customer-avatar-blue.png'
};

const CUSTOMER_DETAILS = {
  'customer-001': BASE_CUSTOMER_DETAIL,
  'customer-002': {
    ...BASE_CUSTOMER_DETAIL,
    id: 'customer-002',
    name: '李先生',
    phone: '186****3681',
    avatar: '/assets/images/customer-avatar-purple.png'
  },
  'customer-003': {
    ...BASE_CUSTOMER_DETAIL,
    id: 'customer-003',
    name: '刘女士',
    phone: '159****2650',
    avatar: '/assets/images/customer-avatar-green.png',
    contributionAvatar: '/assets/images/customer-avatar-green.png'
  },
  'customer-004': {
    ...BASE_CUSTOMER_DETAIL,
    id: 'customer-004',
    name: '赵先生',
    phone: '137****9186'
  }
};

const SERVICE_RECORDS = [
  {
    id: 'service-001',
    title: '健康随访',
    time: '计划时间：今天 16:00',
    status: '待跟进',
    statusTone: 'green',
    tone: 'green',
    icon: 'calendar-o'
  },
  {
    id: 'service-002',
    title: '客户绑定',
    time: '2026年7月18日 10:30',
    status: '已完成',
    statusTone: 'blue',
    tone: 'blue',
    icon: 'link-o'
  },
  {
    id: 'service-003',
    title: '服务包激活',
    time: '2026年7月16日 14:20',
    status: '已完成',
    statusTone: 'blue',
    tone: 'blue',
    icon: 'gift-o'
  },
  {
    id: 'service-004',
    title: '电话回访',
    time: '2026年7月12日 09:40',
    status: '已完成',
    statusTone: 'blue',
    tone: 'blue',
    icon: 'phone-o'
  }
];

const CONTRIBUTION_RECORDS = [
  {
    id: 'contribution-001',
    category: 'binding',
    title: '客户绑定成功',
    time: '2026年7月18日 10:30',
    points: '+1,200',
    tone: 'blue',
    icon: 'link-o'
  },
  {
    id: 'contribution-002',
    category: 'service',
    title: '服务包已激活',
    time: '2026年7月16日 14:20',
    points: '+680',
    tone: 'green',
    icon: 'certificate'
  },
  {
    id: 'contribution-003',
    category: 'service',
    title: '健康随访完成',
    time: '2026年7月14日 16:30',
    points: '+300',
    tone: 'purple',
    icon: 'calendar-o'
  },
  {
    id: 'contribution-004',
    category: 'service',
    title: '客户服务完成',
    time: '2026年7月12日 09:40',
    points: '+1,020',
    tone: 'blue',
    icon: 'friends-o'
  }
];

function normalizeCustomerDetailTab(tab) {
  return CUSTOMER_DETAIL_TABS.some((item) => item.id === tab)
    ? tab
    : 'info';
}

function getCustomerDetail(id) {
  return { ...(CUSTOMER_DETAILS[id] || BASE_CUSTOMER_DETAIL) };
}

function filterContributionRecords(records, category) {
  if (category === 'all') return records.slice();
  return records.filter((record) => record.category === category);
}

module.exports = {
  CUSTOMER_DETAIL_TABS,
  CONTRIBUTION_FILTERS,
  SERVICE_RECORDS,
  CONTRIBUTION_RECORDS,
  normalizeCustomerDetailTab,
  getCustomerDetail,
  filterContributionRecords
};
