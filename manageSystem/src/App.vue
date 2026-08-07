<template>
  <div v-if="isLoginPage" class="app-plain">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" :key="route.path" />
      </transition>
    </router-view>
  </div>
  <el-container v-else class="app-layout">
    <!-- Sidebar -->
    <el-aside :width="isCollapsed ? '64px' : '220px'" class="app-sidebar">
      <div class="sidebar-logo" @click="goHome">
        <span v-if="!isCollapsed" class="logo-text">北京儒泰</span>
        <span v-else class="logo-icon">儒</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        :collapse-transition="false"
        router
      >
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/org">
          <el-icon><Share /></el-icon>
          <span>组织人员管理</span>
        </el-menu-item>
        <el-menu-item index="/customers">
          <el-icon><User /></el-icon>
          <span>客户管理</span>
        </el-menu-item>
        <el-menu-item index="/contributions">
          <el-icon><TrendCharts /></el-icon>
          <span>消费业绩</span>
        </el-menu-item>
        <el-menu-item index="/performance-rules">
          <el-icon><Setting /></el-icon>
          <span>绩效规则</span>
        </el-menu-item>
        <el-menu-item index="/performance">
          <el-icon><DataAnalysis /></el-icon>
          <span>绩效计算</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据报表</span>
        </el-menu-item>
        <el-menu-item index="/articles">
          <el-icon><Document /></el-icon>
          <span>文章管理</span>
        </el-menu-item>
        <el-sub-menu
          v-if="authStore.hasPermission('accounts.read') || authStore.hasPermission('roles.read')"
          index="/accounts"
        >
          <template #title>
            <el-icon><UserFilled /></el-icon>
            <span>账户管理</span>
          </template>
          <el-menu-item
            v-if="authStore.hasPermission('accounts.read')"
            index="/accounts/admins"
          >
            <span>管理员列表</span>
          </el-menu-item>
          <el-menu-item
            v-if="authStore.hasPermission('roles.read')"
            index="/accounts/roles"
          >
            <span>角色管理</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <!-- Right section -->
    <el-container>
      <!-- Header -->
      <el-header class="app-header">
        <div class="header-left">
          <el-button
            text
            @click="isCollapsed = !isCollapsed"
          >
            <el-icon :size="20">
              <Fold v-if="!isCollapsed" />
              <Expand v-else />
            </el-icon>
          </el-button>
          <span class="app-crumb">{{ route.meta.title || '' }}</span>
        </div>
        <div class="header-right">
          <!-- Notification bell with floating popover -->
          <el-popover
            placement="bottom-end"
            :width="360"
            trigger="click"
            @show="fetchNotifications"
          >
            <template #reference>
              <span class="bell-btn" :class="{ 'bell-pulse': unreadCount > 0 }">
                <el-badge :value="unreadCount" :hidden="unreadCount === 0">
                  <el-icon :size="20" style="cursor:pointer"><Bell /></el-icon>
                </el-badge>
              </span>
            </template>
            <div class="notif-panel">
              <div class="notif-header">
                <span>消息通知</span>
                <el-button text size="small" @click="markAllRead">全部已读</el-button>
              </div>
              <div class="notif-list" v-if="notifications.length">
                <div
                  v-for="item in notifications"
                  :key="item.id"
                  class="notif-item"
                  :class="{ unread: !item.isRead }"
                  @click="handleNotifClick(item)"
                >
                  <div class="notif-title">{{ item.title }}</div>
                  <div class="notif-summary">{{ item.summary }}</div>
                  <div class="notif-time">{{ formatNotifTime(item.createdAt) }}</div>
                </div>
              </div>
              <div v-else class="notif-empty">暂无消息</div>
            </div>
          </el-popover>
          <el-dropdown trigger="click">
            <span class="user-dropdown">
              <el-avatar :size="32">
                <el-icon><UserFilled /></el-icon>
              </el-avatar>
              <span class="username">{{ authStore.user?.account || authStore.user?.username || '管理员' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>
                  <span>账户：{{ authStore.user?.account || authStore.user?.username || '-' }}</span>
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- Main content -->
      <el-main class="app-main">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer, Share, User, Link, TrendCharts,
  Setting, DataAnalysis, Document, Bell,
  Fold, Expand, ArrowDown, UserFilled,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCollapsed = ref(false)
const unreadCount = ref(0)
const notifications = ref([])

// Fetch notifications for floating panel
async function fetchNotifications() {
  try {
    const http = (await import('@/api/http')).default
    const res = await http.get('/notifications', { params: { unreadOnly: false, pageSize: 10 } })
    const body = res.data.data || res.data
    notifications.value = (body.items || []).map((item) => ({
      ...item,
      isRead: item.isRead !== undefined ? item.isRead : item.is_read,
    }))
    unreadCount.value = notifications.value.filter((n) => !n.isRead).length
  } catch { /* silence */ }
}

async function markAllRead() {
  try {
    const http = (await import('@/api/http')).default
    for (const item of notifications.value) {
      if (!item.isRead) {
        await http.post(`/notifications/${item.id}/read`).catch(() => {})
      }
    }
    notifications.value.forEach((n) => (n.isRead = true))
    unreadCount.value = 0
  } catch { /* silence */ }
}

function handleNotifClick(item) {
  if (!item.isRead) {
    import('@/api/http').then(({ default: http }) => {
      http.post(`/notifications/${item.id}/read`).catch(() => {})
    })
    item.isRead = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }
}

function formatNotifTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return d.toLocaleDateString('zh-CN')
}

const isLoginPage = computed(() => route.name === 'Login')

const activeMenu = computed(() => route.path)

// Restore session on page refresh (user is not persisted)
onMounted(async () => {
  if (authStore.token && !authStore.user) {
    try {
      await authStore.fetchSession()
    } catch {
      // Session fetch failed — stay on current page, header will show fallback
    }
  }
})

function goHome() {
  router.push('/')
}

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
}

.app-sidebar {
  background: var(--app-sidebar-bg);
  overflow: hidden;
  transition: width var(--app-dur) var(--app-ease);
  /* 侧栏作用域内的菜单换肤变量（只在侧栏生效） */
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--app-sidebar-text);
  --el-menu-active-color: #fff;
  --el-menu-hover-text-color: #fff;
  --el-menu-hover-bg-color: var(--app-sidebar-hover-bg);
}

.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #fff;
  cursor: pointer;
  user-select: none;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 2px;
}

.logo-icon {
  font-size: 22px;
}

.el-menu {
  border-right: none;
}

/* 侧栏菜单：hover 过渡 + 图标微动 */
.app-sidebar :deep(.el-menu-item) {
  position: relative;
  transition: background-color var(--app-dur-fast) var(--app-ease), color var(--app-dur-fast) var(--app-ease);
}
.app-sidebar :deep(.el-menu-item .el-icon) {
  transition: transform var(--app-dur) var(--app-ease);
}
.app-sidebar :deep(.el-menu-item:not(.is-active):hover .el-icon) {
  transform: translateX(3px);
}

/* 侧栏菜单激活指示条 */
.app-sidebar :deep(.el-menu-item.is-active) {
  background: var(--app-sidebar-active-bg);
  color: #fff;
}
.app-sidebar :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--el-color-primary);
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--app-header-bg);
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  border-bottom: 1px solid var(--app-border-color);
  height: 60px;
  padding: 0 20px;
}

.app-crumb {
  margin-left: 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.username {
  font-size: 14px;
  color: #333;
}

.app-main {
  background: var(--app-bg-gradient);
  padding: 20px;
  overflow-y: auto;
}

/* Notification popover */
.notif-panel { max-height: 380px; display: flex; flex-direction: column; }
.notif-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 10px; border-bottom: 1px solid #ebeef5; margin-bottom: 8px; font-weight: 600; }
.notif-list { overflow-y: auto; flex: 1; }
.notif-item { padding: 10px 8px; border-radius: 4px; cursor: pointer; border-bottom: 1px solid #f2f2f2; }
.notif-item:hover { background: #f5f7fa; }
.notif-item.unread { background: #ecf5ff; }
.notif-title { font-size: 14px; color: #303133; margin-bottom: 4px; }
.notif-summary { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.notif-time { font-size: 11px; color: #c0c4cc; margin-top: 4px; }
.notif-empty { text-align: center; padding: 30px 0; color: #c0c4cc; font-size: 14px; }

.app-plain {
  height: 100vh;
}
</style>
