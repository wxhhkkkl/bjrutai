<template>
  <div class="comments-page">
    <div class="page-head">
      <div><h2>评论管理</h2><p>审核、隐藏和维护文章评论，所有变更都会记录操作日志</p></div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-form :inline="true" class="filters" @submit.prevent="search">
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 130px" @change="search">
            <el-option label="待审核" value="pending" /><el-option label="已展示" value="visible" />
            <el-option label="已隐藏" value="hidden" /><el-option label="已拒绝" value="rejected" /><el-option label="已删除" value="deleted" />
          </el-select>
        </el-form-item>
        <el-form-item label="文章标题"><el-input v-model="filters.keyword" clearable placeholder="标题、昵称或评论内容" @keyup.enter="search" /></el-form-item>
        <el-form-item><el-button type="primary" @click="search">搜索</el-button><el-button @click="reset">重置</el-button></el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="items" empty-text="暂无符合条件的评论" row-key="commentId">
        <el-table-column prop="articleTitle" label="文章" min-width="180" show-overflow-tooltip />
        <el-table-column label="评论内容" min-width="230" show-overflow-tooltip><template #default="{ row }">{{ row.contentPreview }}</template></el-table-column>
        <el-table-column prop="displayName" label="用户" width="110" />
        <el-table-column label="状态" width="95"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="审核" width="95"><template #default="{ row }"><el-tag size="small" :type="row.moderationStatus === 'flagged' ? 'danger' : 'info'">{{ moderationLabel(row.moderationStatus) }}</el-tag></template></el-table-column>
        <el-table-column label="赞" prop="likeCount" width="65" />
        <el-table-column label="时间" width="175"><template #default="{ row }">{{ formatDate(row.createdAt) }}</template></el-table-column>
        <el-table-column label="操作" fixed="right" width="250"><template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          <template v-if="canWrite">
            <el-button v-if="row.status === 'pending' || row.status === 'rejected'" link type="success" @click="handleAction(row, 'approve')">审核通过</el-button>
            <el-button v-if="row.status === 'pending'" link type="warning" @click="handleAction(row, 'reject', true)">拒绝</el-button>
            <el-button v-if="row.status === 'visible'" link type="warning" @click="handleAction(row, 'hide', true)">隐藏</el-button>
            <el-button v-if="row.status === 'hidden'" link type="success" @click="handleAction(row, 'restore')">恢复</el-button>
            <el-button v-if="row.status !== 'deleted'" link type="danger" @click="handleAction(row, 'delete', true)">删除</el-button>
            <el-button v-if="row.status === 'visible' || row.status === 'hidden'" link @click="handleAction(row, row.isPinned ? 'unpin' : 'pin')">{{ row.isPinned ? '取消置顶' : '置顶' }}</el-button>
          </template>
        </template></el-table-column>
      </el-table>
      <div class="pagination"><span>共 {{ total }} 条</span><el-button v-if="hasMore" :loading="loadingMore" @click="loadMore">加载更多</el-button></div>
    </el-card>

    <el-drawer v-model="drawerOpen" title="评论详情" size="420px">
      <template v-if="detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="文章">{{ detail.articleTitle || '-' }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ detail.displayName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusLabel(detail.status) }}</el-descriptions-item>
          <el-descriptions-item label="审核">{{ moderationLabel(detail.moderationStatus) }}</el-descriptions-item>
          <el-descriptions-item label="内容"><div class="detail-content">{{ detail.content }}</div></el-descriptions-item>
          <el-descriptions-item label="审核说明">{{ detail.moderationReason || '—' }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
        </el-descriptions>
        <h4>操作记录</h4><el-timeline><el-timeline-item v-for="action in detail.actions || []" :key="action.actionId">{{ action.actionType }} · {{ action.operatorName || '管理员' }}<br><small>{{ action.reason || '—' }}</small></el-timeline-item></el-timeline>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getComment, listComments, updateComment } from '@/api/comments'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canWrite = computed(() => authStore.hasPermission('comments.write'))
const loading = ref(false); const loadingMore = ref(false); const items = ref([]); const total = ref(0); const cursor = ref(null); const hasMore = ref(false); const actionError = ref('')
const drawerOpen = ref(false); const detail = ref(null)
const filters = reactive({ status: '', keyword: '' })
const statusLabel = (value) => ({ pending: '待审核', visible: '已展示', hidden: '已隐藏', rejected: '已拒绝', deleted: '已删除' }[value] || value || '-')
const statusType = (value) => ({ pending: 'warning', visible: 'success', hidden: 'info', rejected: 'danger', deleted: 'info' }[value] || 'info')
const moderationLabel = (value) => ({ pending: '待审核', passed: '已通过', flagged: '命中规则', rejected: '已拒绝', error: '异常' }[value] || value || '-')
const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'

async function load({ append = false } = {}) {
  if (append) loadingMore.value = true; else loading.value = true
  actionError.value = ''
  try {
    const data = await listComments({ articleId: undefined, status: filters.status || undefined, keyword: filters.keyword.trim() || undefined, cursor: append ? cursor.value : undefined, limit: 20 })
    items.value = append ? [...items.value, ...(data.items || [])] : (data.items || [])
    total.value = data.total || 0; cursor.value = data.nextCursor || null; hasMore.value = Boolean(data.hasMore)
  } catch (error) { actionError.value = error.userMessage || '获取评论列表失败'; ElMessage.error(actionError.value) } finally { loading.value = false; loadingMore.value = false }
}
function search() { cursor.value = null; load() }
function reset() { filters.status = ''; filters.keyword = ''; search() }
function loadMore() { return load({ append: true }) }
async function openDetail(row) { drawerOpen.value = true; detail.value = null; try { detail.value = await getComment(row.commentId) } catch (error) { ElMessage.error(error.userMessage || '获取评论详情失败') } }
async function handleAction(row, action, needsReason = false) {
  let reason
  if (needsReason) {
    try { const result = await ElMessageBox.prompt('请输入处理原因（将记录到操作日志）', '处理评论', { inputPlaceholder: '例如：包含不适宜内容', inputValidator: (value) => value?.trim() ? true : '请输入原因' }); reason = result.value } catch { return }
  }
  try {
    await updateComment(row.commentId, { action, expectedVersion: row.version || detail.value?.version || 1, reason })
    ElMessage.success('评论状态已更新'); await load()
    if (detail.value?.commentId === row.commentId) detail.value = await getComment(row.commentId)
  } catch (error) {
    actionError.value = error.userMessage || '评论状态更新失败'
    ElMessage.error(error.response?.status === 409 ? '评论已被其他管理员更新，请刷新后重试' : actionError.value)
    if (error.response?.status === 409) await load()
  }
}
onMounted(load)
</script>

<style scoped>
.comments-page { padding: 0; }.page-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }.page-head h2 { margin:0 0 4px; }.page-head p { margin:0; color:#909399; }.filters { margin-bottom:8px; }.pagination { display:flex; justify-content:space-between; align-items:center; margin-top:16px; color:#606266; }.detail-content { white-space:pre-wrap; word-break:break-word; line-height:1.6; }
</style>
