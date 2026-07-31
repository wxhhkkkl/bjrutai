<template>
  <div class="page-container">
    <h2 class="page-title">消息通知</h2>

    <!-- Category filters -->
    <el-card shadow="never" class="filter-card">
      <el-radio-group v-model="filterCategory" size="small" @change="handleFilterChange">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="system">系统</el-radio-button>
        <el-radio-button label="binding">绑定</el-radio-button>
        <el-radio-button label="promotion">推广</el-radio-button>
        <el-radio-button label="bill">账单</el-radio-button>
        <el-radio-button label="followup">跟进</el-radio-button>
        <el-radio-button label="qualification">资质</el-radio-button>
      </el-radio-group>
      <el-switch
        v-model="unreadOnly"
        active-text="仅未读"
        size="small"
        style="margin-left: 16px;"
        @change="handleFilterChange"
      />
      <span class="unread-badge" v-if="unreadCount > 0">
        {{ unreadCount }} 条未读
      </span>
    </el-card>

    <!-- Notification list -->
    <el-card shadow="never" class="list-card">
      <div v-loading="loading" class="notif-list">
        <el-empty v-if="!loading && !items.length" description="暂无通知" />

        <div
          v-for="item in items"
          :key="item.id"
          class="notif-item"
          :class="{ unread: !item.isRead }"
          @click="markRead(item)"
        >
          <div class="notif-meta">
            <el-icon class="notif-icon" :size="18">
              <Bell />
            </el-icon>
            <div class="notif-body">
              <div class="notif-title">
                <span>{{ item.title }}</span>
                <el-tag
                  v-if="!item.isRead"
                  size="small"
                  type="danger"
                  effect="plain"
                  style="margin-left: 6px;"
                >
                  新
                </el-tag>
              </div>
              <div class="notif-summary">{{ item.summary }}</div>
            </div>
            <div class="notif-right">
              <span class="notif-time">{{ formatTime(item.createdAt) }}</span>
              <el-tag size="small" :type="categoryTagType(item.category)">
                {{ categoryLabel(item.category) }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- Load more -->
      <div class="load-more" v-if="hasMore">
        <el-button
          :loading="loadingMore"
          text
          size="small"
          @click="loadMore"
        >
          加载更多
        </el-button>
      </div>
      <div class="load-more" v-else-if="items.length > 0 && !loading">
        <span class="all-loaded">已加载全部</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'

const loading = ref(false)
const loadingMore = ref(false)
const items = ref([])
const filterCategory = ref('')
const unreadOnly = ref(false)
const nextCursor = ref(null)
const hasMore = ref(false)
const unreadCount = ref(0)

const categoryLabels = {
  system: '系统', binding: '绑定', promotion: '推广',
  bill: '账单', followup: '跟进', qualification: '资质',
}
const categoryTagTypes = {
  system: 'info', binding: 'success', promotion: 'warning',
  bill: '', followup: '', qualification: 'warning',
}

function categoryLabel(c) { return categoryLabels[c] || c }
function categoryTagType(c) { return categoryTagTypes[c] || 'info' }

onMounted(() => { fetchData() })

async function fetchData(cursor = null) {
  loading.value = !cursor
  try {
    const params = { pageSize: 20 }
    if (filterCategory.value) params.category = filterCategory.value
    if (unreadOnly.value) params.unreadOnly = true
    if (cursor) params.cursor = cursor

    const res = await http.get('/notifications', { params })
    const data = res.data?.data || res.data
    const newItems = data.items || []

    if (cursor) {
      items.value = [...items.value, ...newItems]
    } else {
      items.value = newItems
    }
    nextCursor.value = data.nextCursor || null
    hasMore.value = !!data.hasMore
    unreadCount.value = data.unreadCount || 0
  } catch (e) {
    ElMessage.error(e.userMessage || '加载通知失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function handleFilterChange() {
  items.value = []
  fetchData()
}

async function loadMore() {
  loadingMore.value = true
  await fetchData(nextCursor.value)
}

async function markRead(item) {
  if (item.isRead) return
  try {
    await http.post(`/notifications/${item.id}/read`)
    item.isRead = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    // Silently ignore
  }
}

function formatTime(t) {
  if (!t) return '-'
  try {
    const d = new Date(t)
    const now = new Date()
    const diffMs = now - d
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin}分钟前`
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}小时前`
    return d.toLocaleDateString('zh-CN')
  } catch {
    return t
  }
}
</script>

<style scoped>
.page-container { padding: 10px 0; }
.page-title { font-size: 20px; font-weight: 600; color: #303133; margin-bottom: 16px; }

.filter-card {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.unread-badge {
  font-size: 12px;
  color: #f56c6c;
  margin-left: auto;
}

.notif-list { min-height: 150px; }

.notif-item {
  padding: 12px 0;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
  transition: background-color 0.2s;
}
.notif-item:hover { background-color: #f5f7fa; }
.notif-item.unread { background-color: #ecf5ff; }

.notif-meta {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.notif-icon {
  color: #c0c4cc;
  margin-top: 2px;
  flex-shrink: 0;
}
.notif-body { flex: 1; min-width: 0; }
.notif-title {
  font-size: 14px;
  color: #303133;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
}
.notif-summary {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notif-right {
  flex-shrink: 0;
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.notif-time { font-size: 11px; color: #c0c4cc; }

.load-more { text-align: center; padding: 14px 0; }
.all-loaded { color: #b0b4bb; font-size: 12px; }
</style>
