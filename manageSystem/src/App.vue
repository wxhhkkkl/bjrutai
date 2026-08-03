<template>
  <div v-if="isLoginPage" class="app-plain">
    <router-view />
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
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
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
        <el-menu-item index="/customers/binding">
          <el-icon><Link /></el-icon>
          <span>绑定管理</span>
        </el-menu-item>
        <el-menu-item index="/contributions">
          <el-icon><TrendCharts /></el-icon>
          <span>业绩贡献</span>
        </el-menu-item>
        <el-menu-item index="/sharing-rules">
          <el-icon><Setting /></el-icon>
          <span>分成规则</span>
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
        <el-menu-item index="/promotions">
          <el-icon><Discount /></el-icon>
          <span>推广码</span>
        </el-menu-item>
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
              <el-badge :value="unreadCount" :hidden="unreadCount === 0">
                <el-icon :size="20" style="cursor:pointer"><Bell /></el-icon>
              </el-badge>
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
              <el-avatar :size="32" icon="UserFilled" />
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
        <router-view />
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
  Setting, DataAnalysis, Document, Bell, Discount,
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

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html, body, #app {
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
}
</style>

<style scoped>
.app-layout {
  height: 100vh;
}

.app-sidebar {
  background-color: #304156;
  overflow: hidden;
}

.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #2b2f3a;
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

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  height: 60px;
  padding: 0 20px;
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
  background: #f0f2f5;
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
