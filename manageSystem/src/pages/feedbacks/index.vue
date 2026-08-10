<template>
  <div class="feedback-page"><div class="page-head"><div><h2>意见与反馈</h2><p>集中查看和处理小程序用户提交的意见与问题</p></div><el-button @click="load">刷新</el-button></div>
    <el-card shadow="never"><el-form :inline="true" class="filters"><el-form-item label="状态"><el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px" @change="search"><el-option label="待处理" value="submitted" /><el-option label="处理中" value="processing" /><el-option label="已解决" value="resolved" /></el-select></el-form-item><el-form-item label="类型"><el-select v-model="filters.type" clearable placeholder="全部" style="width: 120px" @change="search"><el-option label="功能异常" value="bug" /><el-option label="产品建议" value="suggestion" /><el-option label="其他" value="other" /></el-select></el-form-item><el-form-item label="提交日期"><el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DDTHH:mm:ss" range-separator="至" start-placeholder="开始" end-placeholder="结束" /></el-form-item><el-form-item><el-input v-model="filters.keyword" placeholder="反馈编号/用户姓名" clearable @keyup.enter="search" /></el-form-item><el-form-item><el-button type="primary" @click="search">搜索</el-button><el-button @click="reset">重置</el-button></el-form-item></el-form>
      <el-table v-loading="loading" :data="items" empty-text="暂无符合条件的反馈"><el-table-column prop="feedbackNo" label="反馈编号" width="190" /><el-table-column label="类型" width="105"><template #default="{ row }"><el-tag size="small">{{ typeLabel(row.type) }}</el-tag></template></el-table-column><el-table-column prop="contentSummary" label="内容摘要" min-width="230" show-overflow-tooltip /><el-table-column prop="imageCount" label="图片" width="70" /><el-table-column label="提交用户" width="120"><template #default="{ row }">{{ row.submitter?.available ? (row.submitter?.name || '未完善姓名') : '用户不可用' }}</template></el-table-column><el-table-column label="手机号" width="125"><template #default="{ row }">{{ row.submitter?.phoneMasked || '-' }}</template></el-table-column><el-table-column label="状态" width="95"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column><el-table-column label="提交时间" width="175"><template #default="{ row }">{{ formatDate(row.createdAt) }}</template></el-table-column><el-table-column label="更新时间" width="175"><template #default="{ row }">{{ formatDate(row.updatedAt) }}</template></el-table-column><el-table-column label="操作" fixed="right" width="80"><template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">查看</el-button></template></el-table-column></el-table>
      <div class="pagination"><span>共 {{ total }} 条</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" layout="sizes, prev, pager, next" :total="total" :page-sizes="[20, 50, 100]" @current-change="load" @size-change="changeSize" /></div>
    </el-card><FeedbackDetailDrawer v-model="drawerOpen" :feedback-no="selectedNo" @saved="load" /></div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listFeedbacks } from '@/api/feedbacks'
import FeedbackDetailDrawer from '@/components/feedbacks/FeedbackDetailDrawer.vue'
const loading = ref(false); const items = ref([]); const total = ref(0); const page = ref(1); const pageSize = ref(20); const drawerOpen = ref(false); const selectedNo = ref('')
const filters = reactive({ status: '', type: '', keyword: '', dates: [] })
const statusLabel = (value) => ({ submitted: '待处理', processing: '处理中', resolved: '已解决' }[value] || value)
const statusType = (value) => ({ submitted: 'warning', processing: 'primary', resolved: 'success' }[value] || 'info')
const typeLabel = (value) => ({ bug: '功能异常', suggestion: '产品建议', other: '其他' }[value] || value)
const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
async function load() { loading.value = true; try { const data = await listFeedbacks({ status: filters.status || undefined, type: filters.type || undefined, keyword: filters.keyword.trim() || undefined, submittedFrom: filters.dates?.[0], submittedTo: filters.dates?.[1], page: page.value, pageSize: pageSize.value }); items.value = data.items || []; total.value = data.total || 0 } catch (error) { ElMessage.error(error.userMessage || '获取反馈列表失败') } finally { loading.value = false } }
function search() { page.value = 1; load() }
function reset() { filters.status = ''; filters.type = ''; filters.keyword = ''; filters.dates = []; search() }
function changeSize() { page.value = 1; load() }
function openDetail(row) { selectedNo.value = row.feedbackNo; drawerOpen.value = true }
onMounted(load)
</script>

<style scoped>
.feedback-page { padding: 0; }.page-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }.page-head h2 { margin:0 0 4px; }.page-head p { margin:0; color:#909399; }.filters { margin-bottom: 8px; }.pagination { display:flex; justify-content:space-between; align-items:center; margin-top:16px; color:#606266; }
</style>
