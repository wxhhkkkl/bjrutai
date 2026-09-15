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
        icon: 'friends-o',
        businessOnly: true
    },
    {
        id: 'contribution',
        label: '消费',
        pagePath: '/pages/contribution/index',
        icon: 'diamond-o',
        businessOnly: true
    },
    {
        id: 'profile',
        label: '我的',
        pagePath: '/pages/profile/index',
        icon: 'contact-o'
    }
]

function getVisibleTabs(session) {
    const businessReady = Boolean(
        session && session.hasBusinessMembership === true &&
        session.membershipStatus !== 'disabled' && session.orgStatus !== 'disabled'
    )
    return TAB_ITEMS.filter((item) => !item.businessOnly || businessReady)
}

const ACTION_TARGETS = {
    'promote-code': {
        title: '客户绑定码',
        path: '/pages/promotion-code/index',
        capability: 'promotion'
    },
    'staff-invite': {
        title: '发展业务员',
        path: '/pages/staff-invite/index',
        capability: 'staffInvite'
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
        title: '消费明细',
        path: '/pages/contribution-detail/index',
        capability: 'contribution'
    },
    'article-list': {
        title: '文章资讯',
        path: '/pages/articles/index'
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
        path: '/pages/notifications/index'
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
    getVisibleTabs,
    ACTION_TARGETS
}
