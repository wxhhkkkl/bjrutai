<template>
  <div class="binding-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">绑定管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        新建绑定
      </el-button>
    </div>

    <!-- Summary Cards -->
    <el-row :gutter="16" class="summary-row">
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card">
          <div class="summary-value">{{ summary.totalBindings }}</div>
          <div class="summary-label">总绑定数</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card summary-active">
          <div class="summary-value">{{ summary.activeBindings }}</div>
          <div class="summary-label">已绑定</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card summary-pending">
          <div class="summary-value">{{ summary.pendingRequests }}</div>
          <div class="summary-label">进行中</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card summary-warning">
          <div class="summary-value">{{ abnormalCount }}</div>
          <div class="summary-label">异常/无消费</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card summary-danger">
          <div class="summary-value">{{ summary.rejectedRequests }}</div>
          <div class="summary-label">已拒绝</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="summary-card summary-info">
          <div class="summary-value">{{ summary.expiredRequests }}</div>
          <div class="summary-label">已过期</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Filter Tabs -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange" class="filter-tabs">
      <el-tab-pane label="全部" name="" />
      <el-tab-pane label="已绑定" name="bound" />
      <el-tab-pane label="匹配中" name="matching" />
      <el-tab-pane label="异常" name="abnormal" />
      <el-tab-pane label="已解绑" name="unbound" />
    </el-tabs>

    <!-- Search Bar -->
    <div class="toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索客户姓名或手机号"
        clearable
        style="width: 260px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button type="primary" @click="handleSearch">搜索</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <!-- Table -->
    <el-table
      :data="bindings"
      v-loading="loading"
      stripe
      style="width: 100%"
      @sort-change="handleSortChange"
    >
      <el-table-column prop="requestId" label="请求ID" width="120" />
      <el-table-column label="客户信息" min-width="160">
        <template #default="{ row }">
          <div class="cell-customer">
            <div>{{ row.customerInfo?.name || '-' }}</div>
            <div class="text-muted">{{ row.customerInfo?.phone || '-' }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="推广员" min-width="120">
        <template #default="{ row }">
          <div>{{ row.target?.displayName || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="提交人" min-width="120">
        <template #default="{ row }">
          <div>{{ row.initiator?.displayName || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="匹配级别" width="100">
        <template #default="{ row }">
          <span v-if="row.matchLevel">{{ getMatchLabel(row.matchLevel) }}</span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="180" prop="submittedAt" sortable="custom" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleViewDetail(row)">
            详情
          </el-button>
          <el-button
            v-if="canRetry(row)"
            link
            type="warning"
            size="small"
            @click="handleRetry(row)"
          >
            重试
          </el-button>
          <el-button
            v-if="canUnbind(row)"
            link
            type="danger"
            size="small"
            @click="handleOpenUnbind(row)"
          >
            解绑
          </el-button>
          <el-button
            v-if="canTransfer(row)"
            link
            type="primary"
            size="small"
            @click="handleOpenTransfer(row)"
          >
            转移
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Load More -->
    <div class="load-more" v-if="hasMore">
      <el-button :loading="loadingMore" @click="handleLoadMore">
        加载更多
      </el-button>
    </div>

    <!-- Detail Dialog -->
    <el-dialog
      v-model="showDetailDialog"
      title="绑定详情"
      width="640px"
      :close-on-click-modal="false"
    >
      <template v-if="currentBinding">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="请求ID">{{ currentBinding.requestId }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(currentBinding.status)" size="small">
              {{ getStatusLabel(currentBinding.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="客户姓名">{{ currentBinding.customerInfo?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户电话">{{ currentBinding.customerInfo?.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="身份证号">{{ currentBinding.customerInfo?.idCard || '-' }}</el-descriptions-item>
          <el-descriptions-item label="匹配级别">{{ getMatchLabel(currentBinding.matchLevel) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="提交人">{{ currentBinding.initiator?.displayName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="推广员">{{ currentBinding.target?.displayName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ currentBinding.submittedAt || '-' }}</el-descriptions-item>
          <el-descriptions-item label="过期时间">{{ currentBinding.expiresAt || '-' }}</el-descriptions-item>
          <el-descriptions-item label="重试次数">{{ currentBinding.retryCount }}</el-descriptions-item>
          <el-descriptions-item label="失败原因" :span="2">{{ currentBinding.failureReason || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- Audit Events -->
        <el-divider content-position="left">操作记录</el-divider>
        <el-timeline v-if="currentBinding.events?.length">
          <el-timeline-item
            v-for="(event, idx) in currentBinding.events"
            :key="idx"
            :timestamp="event.timestamp"
          >
            {{ event.actionLabel }}
            <span class="text-muted" v-if="event.operatorName">（{{ event.operatorName }}）</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录" :image-size="60" />
      </template>
    </el-dialog>

    <!-- Unbind Dialog -->
    <UnbindDialog
      v-model="showUnbindDialog"
      :request-id="selectedRequest?.requestId"
      :customer-name="selectedRequest?.customerInfo?.name"
      :promoter-name="selectedRequest?.target?.displayName"
      :has-settlements="false"
      @success="handleUnbind"
    />

    <!-- Transfer Dialog -->
    <TransferDialog
      v-model="showTransferDialog"
      :request-id="selectedRequest?.requestId"
      :customer-name="selectedRequest?.customerInfo?.name"
      :current-promoter-name="selectedRequest?.target?.displayName"
      :status-label="selectedRequest ? getStatusLabel(selectedRequest.status) : ''"
      :status-type="selectedRequest ? getStatusType(selectedRequest.status) : 'info'"
      @success="handleTransfer"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { useBindingStore } from '@/stores/binding'
import UnbindDialog from '@/components/customers/UnbindDialog.vue'
import TransferDialog from '@/components/customers/TransferDialog.vue'

const bindingStore = useBindingStore()

// State
const activeTab = ref('')
const searchKeyword = ref('')
const loadingMore = ref(false)
const showDetailDialog = ref(false)
const showUnbindDialog = ref(false)
const showTransferDialog = ref(false)
const showCreateDialog = ref(false)
const selectedRequest = ref(null)

// Computed
const bindings = computed(() => bindingStore.bindings)
const loading = computed(() => bindingStore.loading)
const hasMore = computed(() => bindingStore.hasMore)
const summary = computed(() => bindingStore.summary)
const currentBinding = computed(() => bindingStore.currentBinding)
const abnormalCount = computed(() => bindingStore.abnormalCount)

// Methods
function getStatusLabel(status) {
  return bindingStore.getStatusLabel(status)
}

function getStatusType(status) {
  return bindingStore.getStatusType(status)
}

function getMatchLabel(level) {
  const labels = { exact: '精确匹配', fuzzy: '模糊匹配', none: '未匹配' }
  return labels[level] || level
}

function canRetry(row) {
  return ['abnormal', 'no_consume', 'manual_review'].includes(row.status)
}

function canUnbind(row) {
  return ['bound'].includes(row.status)
}

function canTransfer(row) {
  return ['bound'].includes(row.status)
}

// Tab / Filter
function handleTabChange(status) {
  bindingStore.filterStatus = status
  bindingStore.resetState()
  loadData()
}

function handleSearch() {
  bindingStore.resetState()
  loadData()
}

function handleReset() {
  searchKeyword.value = ''
  activeTab.value = ''
  bindingStore.filterStatus = ''
  bindingStore.filterKeyword = ''
  bindingStore.resetState()
  loadData()
}

function handleSortChange({ prop, order }) {
  bindingStore.resetState()
  loadData(order ? { sortBy: prop, sortOrder: order === 'ascending' ? 'asc' : 'desc' } : {})
}

async function loadData(extra = {}) {
  await bindingStore.fetchBindings({
    status: bindingStore.filterStatus || undefined,
    keyword: searchKeyword.value || undefined,
    limit: 20,
    ...extra,
  })
}

async function handleLoadMore() {
  loadingMore.value = true
  try {
    await bindingStore.fetchBindings({
      status: bindingStore.filterStatus || undefined,
      keyword: searchKeyword.value || undefined,
      cursor: bindingStore.nextCursor,
      limit: 20,
    })
  } finally {
    loadingMore.value = false
  }
}

// Detail
async function handleViewDetail(row) {
  try {
    const data = await bindingStore.fetchBindingDetail(row.requestId)
    showDetailDialog.value = true
  } catch {
    // Error handled in store
  }
}

// Retry
async function handleRetry(row) {
  try {
    await ElMessageBox.confirm('确定要重试此绑定请求吗？', '确认重试', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await bindingStore.retryBinding(row.requestId)
    bindingStore.resetState()
    await loadData()
  } catch {
    // Cancelled
  }
}

// Unbind
function handleOpenUnbind(row) {
  selectedRequest.value = row
  showUnbindDialog.value = true
}

async function handleUnbind({ reason }) {
  try {
    await bindingStore.unbindCustomer(selectedRequest.value.requestId, reason)
    showUnbindDialog.value = false
    bindingStore.resetState()
    await loadData()
  } catch {
    // Error handled in store
  }
}

// Transfer
function handleOpenTransfer(row) {
  selectedRequest.value = row
  showTransferDialog.value = true
}

async function handleTransfer({ newPromoterId, reason }) {
  try {
    await bindingStore.transferCustomer(selectedRequest.value.requestId, newPromoterId, reason)
    showTransferDialog.value = false
    bindingStore.resetState()
    await loadData()
  } catch {
    // Error handled in store
  }
}

// Lifecycle
onMounted(async () => {
  await Promise.all([
    loadData(),
    bindingStore.fetchBindingSummary(),
  ])
})
</script>

<style scoped>
.binding-page {
  padding: 10px 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.summary-row {
  margin-bottom: 16px;
}

.summary-card {
  text-align: center;
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.summary-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.summary-active .summary-value { color: #67c23a; }
.summary-pending .summary-value { color: #409eff; }
.summary-warning .summary-value { color: #e6a23c; }
.summary-danger .summary-value { color: #f56c6c; }
.summary-info .summary-value { color: #909399; }

.filter-tabs {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.cell-customer {
  line-height: 1.4;
}

.text-muted {
  color: #909399;
  font-size: 12px;
}

.load-more {
  text-align: center;
  padding: 20px 0;
}
</style>
