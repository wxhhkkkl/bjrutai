<template>
  <el-card class="sync-status-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <span class="card-title">数据同步状态</span>
        <el-tag :type="healthStatus.type" size="small" effect="dark">
          {{ healthStatus.label }}
        </el-tag>
      </div>
    </template>

    <div v-loading="loading" class="sync-body">
      <!-- Stats Row -->
      <el-row :gutter="16" class="stats-row">
        <el-col :span="8">
          <div class="stat-item">
            <div class="stat-label">最近同步</div>
            <div class="stat-value">{{ lastPollTime }}</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-item">
            <div class="stat-label">失败次数</div>
            <div class="stat-value" :class="{ 'text-danger': status.failure_count > 0 }">
              {{ status.failure_count }}
            </div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-item">
            <div class="stat-label">待重试</div>
            <div class="stat-value" :class="{ 'text-warning': status.pending_retries > 0 }">
              {{ status.pending_retries }}
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- Detail Info -->
      <el-descriptions :column="1" border size="small" class="sync-detail">
        <el-descriptions-item label="绑定用户轮询">
          {{ formatTime(status.last_bind_user_poll) }}
        </el-descriptions-item>
        <el-descriptions-item label="账单同步">
          {{ formatTime(status.last_bill_sync) }}
        </el-descriptions-item>
        <el-descriptions-item label="轮询状态">
          <el-tag :type="status.is_polling ? 'success' : 'info'" size="small">
            {{ status.is_polling ? '运行中' : '空闲' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="熔断器">
          <el-tag :type="status.circuit_breaker_open ? 'danger' : 'success'" size="small">
            {{ status.circuit_breaker_open ? '已熔断' : '正常' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <!-- Actions -->
      <div class="sync-actions">
        <el-button
          type="primary"
          size="small"
          :loading="retryingBindUser"
          :disabled="status.circuit_breaker_open"
          @click="retryBindUser"
        >
          重试绑定用户同步
        </el-button>
        <el-button size="small" :loading="loading" @click="fetchStatus">
          刷新状态
        </el-button>
      </div>

      <!-- Circuit Breaker Warning -->
      <el-alert
        v-if="status.circuit_breaker_open"
        title="熔断器已触发"
        type="error"
        :description="`连续失败 ${status.failure_count} 次，数据同步已暂停。请检查 Rutai API 连接后手动重试。`"
        show-icon
        :closable="false"
        class="sync-alert"
      />

      <!-- Warning for consecutive failures -->
      <el-alert
        v-else-if="status.failure_count >= 3"
        title="同步异常警告"
        type="warning"
        :description="`已有 ${status.failure_count} 次连续失败，请关注 API 连接状态。`"
        show-icon
        :closable="false"
        class="sync-alert"
      />
    </div>
  </el-card>
</template>

<script setup>
import { onMounted } from 'vue'
import { useSyncStore } from '@/stores/sync'
import { storeToRefs } from 'pinia'

const syncStore = useSyncStore()
const {
  status,
  loading,
  retryingBindUser,
  lastPollTime,
  lastBillSyncTime,
  healthStatus,
} = storeToRefs(syncStore)

const { fetchStatus, retryBindUser, formatTime } = syncStore

onMounted(() => {
  fetchStatus()
  // Auto-refresh every 30 seconds
  const timer = setInterval(fetchStatus, 30000)
  onUnmounted(() => clearInterval(timer))
})

import { onUnmounted } from 'vue'
</script>

<style scoped>
.sync-status-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.sync-body {
  min-height: 120px;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-item {
  text-align: center;
  padding: 8px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.text-danger {
  color: #f56c6c;
}

.text-warning {
  color: #e6a23c;
}

.sync-detail {
  margin-bottom: 16px;
}

.sync-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.sync-alert {
  margin-top: 8px;
}
</style>
