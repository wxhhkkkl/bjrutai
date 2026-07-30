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
    path: '/hierarchy',
    name: 'Hierarchy',
    component: () => import('@/pages/hierarchy/index.vue'),
    meta: { title: '层级管理', icon: 'Share' },
  },
  {
    path: '/qualifications',
    name: 'Qualifications',
    component: () => import('@/pages/qualifications/index.vue'),
    meta: { title: '资质审核', icon: 'Checked' },
  },
  {
    path: '/customers',
    name: 'Customers',
    component: () => import('@/pages/customers/index.vue'),
    meta: { title: '客户管理', icon: 'User' },
  },
  {
    path: '/customers/binding',
    name: 'CustomerBinding',
    component: () => import('@/pages/customers/binding.vue'),
    meta: { title: '绑定管理', icon: 'Link' },
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
    meta: { title: '业绩贡献', icon: 'TrendCharts' },
  },
  {
    path: '/sharing-rules',
    name: 'SharingRules',
    component: () => import('@/pages/sharing-rules/index.vue'),
    meta: { title: '分成规则', icon: 'Setting' },
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
    path: '/accounts',
    name: 'Accounts',
    component: () => import('@/pages/accounts/index.vue'),
    meta: { title: '账户管理', icon: 'UserFilled' },
  },
  {
    path: '/accounts/roles',
    name: 'AccountRoles',
    component: () => import('@/pages/accounts/roles.vue'),
    meta: { title: '角色管理', icon: 'Key' },
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/pages/notifications/index.vue'),
    meta: { title: '消息通知', icon: 'Bell' },
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

// Navigation guard — check auth
router.beforeEach((to, from, next) => {
  if (to.meta.public) {
    return next()
  }
  const authStore = useAuthStore()
  if (!authStore.token) {
    return next({ name: 'Login', query: { redirect: to.fullPath } })
  }
  next()
})

export default router
