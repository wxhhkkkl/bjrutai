const TAB_ITEMS = [{
        id: 'home',
        label: '首页',
        pagePath: '/pages/home/index',
        icon: 'home-o'
    },
    {
        id: 'customers',
        label: '客户',
        pagePath: '/pages/customers/index',
        icon: 'friends-o'
    },
    {
        id: 'contribution',
        label: '贡献',
        pagePath: '/pages/contribution/index',
        icon: 'diamond-o'
    },
    {
        id: 'profile',
        label: '我的',
        pagePath: '/pages/profile/index',
        icon: 'contact-o'
    }
]

const ACTION_TARGETS = {
    'promote-code': {
        title: '我的推广码',
        path: '/pages/promotion-code/index',
        capability: 'promotion'
    },
    'bind-client': {
        title: '客户绑定',
        path: '/pages/customer-binding/index',
        capability: 'customerBinding'
    },
    'binding-records': {
        title: '绑定记录',
        path: '/pages/binding-records/index',
        capability: 'customerBinding'
    },
    'contribution-detail': {
        title: '贡献明细',
        path: '/pages/contribution-detail/index',
        capability: 'contribution'
    },
    'org-performance': {
        title: '组织业绩',
        path: '/pages/org-performance/index',
        capability: 'orgPerformance'
    },
    'customer-analysis': {
        title: '客户分析',
        path: '/pages/customer-analysis/index',
        capability: 'customerAnalysis'
    },
    notification: {
        title: '消息通知',
        path: '/pages/common/feature-placeholder/index?title=消息通知'
    },
    profile: {
        title: '账号信息',
        path: '/pages/account-profile/index'
    },
    'help-feedback': {
        title: '帮助与反馈',
        path: '/pages/help-feedback/index'
    },
    privacy: {
        title: '隐私与授权',
        path: '/pages/privacy-authorization/index'
    }
}

module.exports = {
    TAB_ITEMS,
    ACTION_TARGETS
}
