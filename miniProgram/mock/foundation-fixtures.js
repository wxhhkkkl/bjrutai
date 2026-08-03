const sessions = {
  promoter: { userId: 'demo-promoter-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'active', orgRole: 'admin', profileCompleted: true, name: '张小明' },
  doctor: { userId: 'demo-doctor-001', role: 'collaborator', identityType: 'doctor', activationStatus: 'active', profileCompleted: true, name: '李医生' },
  reviewing: { userId: 'demo-reviewing-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'active', profileCompleted: true, name: '张小明' },
  rejected: { userId: 'demo-rejected-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'active', profileCompleted: true, name: '张小明' },
  inactive: { userId: 'demo-inactive-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'inactive', profileCompleted: true, name: '张小明' },
  expiring: { userId: 'demo-expiring-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'active', profileCompleted: true, name: '张小明' },
  incomplete: { userId: 'demo-incomplete-001', role: 'collaborator', identityType: 'promoter', activationStatus: 'active', profileCompleted: false, name: '张小明' },
  unknown: { userId: '', role: 'unknown', activationStatus: 'inactive', profileCompleted: false, name: '' }
}

const summaries = {
  promoter: { monthlyContribution: '12,680', directMembers: '18', teamContribution: '86,420', pending: '3' },
  customers: [
    { id: 'customer-001', name: '王女士', phone: '138****1028', note: '最近服务：今日', status: '已绑定', tone: 'blue', avatar: '/assets/images/customer-avatar-blue.png' },
    { id: 'customer-002', name: '李先生', phone: '186****3681', note: '已提交，系统持续匹配', status: '待匹配', tone: 'orange', avatar: '/assets/images/customer-avatar-purple.png' },
    { id: 'customer-003', name: '刘女士', phone: '159****2650', note: '健康随访待完成', status: '待跟进', tone: 'green', avatar: '/assets/images/customer-avatar-green.png' },
    { id: 'customer-004', name: '赵先生', phone: '137****9186', note: '最近服务：7月18日', status: '已绑定', tone: 'blue', avatar: '/assets/images/customer-avatar-blue.png' }
  ],
  contributionOverview: {
    amount: '12,680',
    growth: '+18%'
  },
  contributionComposition: {
    binding: '8,400',
    service: '4,280'
  },
  contribution: [
    { title: '客户绑定成功', meta: '王女士 · 7月18日', value: '+1,200', icon: '/assets/images/contribution-bind-icon.png' },
    { title: '服务包已激活', meta: '李先生 · 7月16日', value: '+680', icon: '/assets/images/contribution-service-icon.png' },
    { title: '完成健康随访', meta: '刘女士 · 7月14日', value: '+300', icon: '/assets/images/contribution-followup-icon.png' }
  ]
}

module.exports = { sessions, summaries }
