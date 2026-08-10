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
    name: 'Articles',
    component: () => import('@/pages/articles/index.vue'),
    meta: { title: '文章管理', icon: 'Document' },
  },
  {
    path: '/articles/categories',
    name: 'ArticleCategories',
    component: () => import('@/pages/articles/categories.vue'),
    meta: { title: '文章分类', permission: 'articles.read' },
  },
  {
    path: '/articles/preview/:id',
    name: 'ArticlePreview',
    component: () => import('@/pages/articles/preview.vue'),
    meta: { title: '文章预览', public: true },
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
  history: createWebHistory(),
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
  next()
})

export default router
