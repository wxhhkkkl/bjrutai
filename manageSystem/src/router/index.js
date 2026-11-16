import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/login/index.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/pages/dashboard/index.vue'),
    meta: { title: '仪表盘', icon: 'Odometer' },
  },
  {
    path: '/org',
    name: 'OrgTree',
    component: () => import('@/pages/org/org-tree.vue'),
    meta: { title: '组织人员管理', icon: 'Share', permission: 'org.read' },
  },
  {
    path: '/org/detail',
    name: 'OrgDetail',
    component: () => import('@/pages/org/org-detail.vue'),
    meta: { title: '组织详情', hidden: true, permission: 'org.read' },
  },
  {
    path: '/customers',
    name: 'Customers',
    component: () => import('@/pages/customers/index.vue'),
    meta: { title: '客户管理', icon: 'User' },
  },
  {
    path: '/customers/binding',
    redirect: '/customers',
  },
  {
    path: '/customers/:id',
    name: 'CustomerDetail',
    component: () => import('@/pages/customers/detail.vue'),
    meta: { title: '客户详情', hidden: true },
  },
  {
    path: '/contributions',
    name: 'Contributions',
    component: () => import('@/pages/contributions/index.vue'),
    meta: { title: '消费业绩', icon: 'TrendCharts' },
  },
  {
    path: '/performance-rules',
    name: 'PerformanceRules',
    component: () => import('@/pages/performance-rules/index.vue'),
    meta: { title: '绩效规则', icon: 'Setting' },
  },
  {
    path: '/performance',
    name: 'PerformanceSettlement',
    component: () => import('@/pages/performance/settlement.vue'),
    meta: { title: '绩效计算', icon: 'DataAnalysis' },
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('@/pages/reports/index.vue'),
    meta: { title: '数据报表', icon: 'DataAnalysis' },
  },
  {
    path: '/articles',
    name: 'ArticleManagement',
    component: () => import('@/pages/articles/layout.vue'),
    meta: { title: '文章管理', icon: 'Document' },
    children: [
      {
        path: 'categories',
        name: 'ArticleCategories',
        component: () => import('@/pages/articles/categories.vue'),
        meta: { title: '文章分类', permission: 'articles.read' },
      },
      {
        path: '',
        name: 'Articles',
        component: () => import('@/pages/articles/index.vue'),
        meta: { title: '文章管理', permission: 'articles.read' },
      },
      {
        path: 'comments',
        name: 'Comments',
        component: () => import('@/pages/comments/index.vue'),
        meta: { title: '评论管理', permission: 'comments.read' },
      },
      {
        path: 'preview/:id',
        name: 'ArticlePreview',
        component: () => import('@/pages/articles/preview.vue'),
        meta: { title: '文章预览', public: true, hidden: true },
      },
    ],
  },
  {
    path: '/comments',
    redirect: '/articles/comments',
  },
  {
    path: '/banners',
    name: 'Banners',
    component: () => import('@/pages/banners/index.vue'),
    meta: { title: '轮播图管理', icon: 'Picture' },
  },
  {
    path: '/share-configs',
    name: 'MiniProgramShareConfigs',
    component: () => import('@/pages/share-configs/index.vue'),
    meta: { title: '小程序分享配置', icon: 'Share', permission: 'mini_program_shares.read' },
  },
  {
    path: '/mall/workbench',
    name: 'MallWorkbench',
    component: () => import('@/pages/mall/workbench/index.vue'),
    meta: {
      title: '商城工作台',
      permissionAny: [
        'mall.orders.read',
        'mall.shipments.write',
        'mall.aftersales.read',
        'mall.aftersales.review',
        'mall.returns.receive',
        'mall.payments.read',
        'mall.payments.query',
        'mall.refunds.read',
        'mall.refunds.query',
        'mall.refunds.execute',
        'mall.attribution.write',
        'performance.settle',
        'mall.invoices.read',
        'mall.invoices.write',
        'mall.stock.read',
        'mall.stock.write',
      ],
    },
  },
  {
    path: '/mall/categories',
    name: 'MallCategories',
    component: () => import('@/pages/mall/categories/index.vue'),
    meta: { title: '商品分类', permission: 'mall.products.read' },
  },
  {
    path: '/mall/products',
    name: 'MallProducts',
    component: () => import('@/pages/mall/products/index.vue'),
    meta: { title: '商品管理', permission: 'mall.products.read' },
  },
  {
    path: '/mall/settings/delivery',
    name: 'MallDeliverySettings',
    component: () => import('@/pages/mall/settings/delivery.vue'),
    meta: { title: '配送设置', permission: 'mall.settings.read', activeMenu: '/mall/settings/delivery' },
  },
  {
    path: '/mall/settings/freight',
    name: 'MallFreightSettings',
    component: () => import('@/pages/mall/settings/freight.vue'),
    meta: { title: '运费设置', permission: 'mall.settings.read', activeMenu: '/mall/settings/freight' },
  },
  {
    path: '/mall/settings/trade',
    name: 'MallTradeSettings',
    component: () => import('@/pages/mall/settings/trade.vue'),
    meta: { title: '交易设置', permission: 'mall.settings.read', activeMenu: '/mall/settings/trade' },
  },
  {
    path: '/mall/orders',
    name: 'MallOrders',
    component: () => import('@/pages/mall/orders/index.vue'),
    meta: { title: '交易订单', permission: 'mall.orders.read' },
  },
  {
    path: '/mall/payments',
    name: 'MallPayments',
    component: () => import('@/pages/mall/payments/index.vue'),
    meta: {
      title: '支付订单',
      permission: 'mall.payments.read',
    },
  },
  {
    path: '/mall/refunds',
    name: 'MallRefunds',
    component: () => import('@/pages/mall/refunds/index.vue'),
    meta: { title: '退款订单', permission: 'mall.refunds.read' },
  },
  {
    path: '/mall/orders/:id',
    name: 'MallOrderDetail',
    component: () => import('@/pages/mall/orders/detail.vue'),
    props: true,
    meta: { title: '交易订单详情', permission: 'mall.orders.read', activeMenu: '/mall/orders' },
  },
  {
    path: '/mall/invoices',
    name: 'MallInvoices',
    component: () => import('@/pages/mall/invoices/index.vue'),
    meta: { title: '发票与红冲', permission: 'mall.invoices.read' },
  },
  {
    path: '/mall/invoices/:id',
    name: 'MallInvoiceDetail',
    component: () => import('@/pages/mall/invoices/detail.vue'),
    props: true,
    meta: {
      title: '发票办理详情',
      permission: 'mall.invoices.read',
      activeMenu: '/mall/invoices',
    },
  },
  {
    path: '/mall/aftersales',
    name: 'MallAftersales',
    component: () => import('@/pages/mall/aftersales/index.vue'),
    meta: { title: '售后处理', permission: 'mall.aftersales.read' },
  },
  {
    path: '/mall/aftersales/:id',
    name: 'MallAftersaleDetail',
    component: () => import('@/pages/mall/aftersales/detail.vue'),
    props: true,
    meta: {
      title: '售后详情',
      permission: 'mall.aftersales.read',
      activeMenu: '/mall/aftersales',
    },
  },
  {
    path: '/accounts',
    name: 'Accounts',
    redirect: '/accounts/admins',
    meta: { title: '账户管理', icon: 'UserFilled' },
    children: [
      {
        path: 'admins',
        name: 'AccountAdmins',
        component: () => import('@/pages/accounts/index.vue'),
        meta: { title: '管理员列表', permission: 'accounts.read' },
      },
      {
        path: 'roles',
        name: 'AccountRoles',
        component: () => import('@/pages/accounts/roles.vue'),
        meta: { title: '角色管理', permission: 'roles.read' },
      },
    ],
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/pages/notifications/index.vue'),
    meta: { title: '消息通知', icon: 'Bell' },
  },
  {
    path: '/feedbacks',
    name: 'Feedbacks',
    component: () => import('@/pages/feedbacks/index.vue'),
    meta: { title: '意见与反馈', icon: 'ChatDotRound', permission: 'feedbacks.read' },
  },
  {
    path: '/promotions',
    name: 'Promotions',
    component: () => import('@/pages/promotions/index.vue'),
    meta: { title: '推广码', icon: 'Discount' },
  },
]

const router = createRouter({
  // 部署在 /admin/ 子路径下
  history: createWebHistory('/admin/'),
  routes,
})

// Navigation guard — check auth + permissions
router.beforeEach(async (to, from, next) => {
  if (to.meta.public) {
    return next()
  }
  const authStore = useAuthStore()
  if (!authStore.token) {
    return next({ name: 'Login', query: { redirect: to.fullPath } })
  }

  // On a full-page refresh Pinia restores the token from localStorage, but
  // the user and permissions are populated asynchronously. Wait for the
  // session before checking route permissions; otherwise a permitted deep
  // route (for example /feedbacks) is incorrectly redirected to '/'.
  if (!authStore.user) {
    try {
      await authStore.fetchSession()
    } catch {
      // Keep the requested route on a transient session/network failure.
      // The page/API layer can surface the error and the interceptor will
      // handle an actually expired token.
      return next()
    }
  }

  // Permission check for routes that declare required permission
  if (to.meta.permission && !authStore.hasPermission(to.meta.permission)) {
    return next({ name: 'Dashboard' })
  }
  if (
    to.meta.permissionAny?.length &&
    !to.meta.permissionAny.some((permission) => authStore.hasPermission(permission))
  ) {
    return next({ name: 'Dashboard' })
  }
  next()
})

export default router
