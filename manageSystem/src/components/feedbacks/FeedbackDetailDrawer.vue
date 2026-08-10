<template>
  <el-drawer v-model="open" title="反馈详情" size="820px" :close-on-click-modal="!saving" @closed="reset">
    <el-skeleton v-if="loading" :rows="8" animated />
    <template v-else-if="detail">
      <el-descriptions :column="2" border class="section">
        <el-descriptions-item label="反馈编号">{{ detail.feedbackNo }}</el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="类型">{{ typeLabel(detail.type) }}</el-descriptions-item>
        <el-descriptions-item label="提交用户">{{ detail.submitter?.available ? (detail.submitter?.name || '未完善姓名') : '用户不可用' }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ detail.submitter?.phoneMasked || '-' }}</el-descriptions-item>
        <el-descriptions-item label="提交时间">{{ formatDate(detail.createdAt) }}</el-descriptions-item>
      </el-descriptions>

      <section class="section"><h4>问题描述</h4><p class="content">{{ detail.content }}</p></section>
      <section class="section"><h4>问题截图</h4><div v-if="detail.attachments?.length" class="images"><div v-for="item in detail.attachments" :key="item.order" class="image-cell"><el-image v-if="item.available" :src="item.previewUrl" :preview-src-list="previewUrls" fit="cover" :alt="`预览第 ${item.order + 1} 张截图`" /><span v-else>附件不可用</span></div></div><el-empty v-else description="没有上传截图" :image-size="50" /></section>
      <section class="section"><h4>处理记录</h4><el-timeline><el-timeline-item v-for="action in detail.actions" :key="action.actionId" :timestamp="formatDate(action.createdAt)"><strong>{{ action.operatorName }}</strong>：{{ statusLabel(action.fromStatus) }} → {{ statusLabel(action.toStatus) }}<p v-if="action.internalNote">内部备注：{{ action.internalNote }}</p><p v-if="action.userResolution">用户结果：{{ action.userResolution }}</p></el-timeline-item></el-timeline><el-empty v-if="!detail.actions?.length" description="暂未处理" :image-size="50" /></section>
      <section v-if="detail.status === 'resolved'" class="section"><h4>处理结果</h4><p class="content">{{ detail.resolution }}</p><el-tag size="small">站内通知：{{ notificationLabel(detail.notificationStatus) }}</el-tag></section>

      <section v-if="canWrite && detail.status !== 'resolved'" class="section process"><h4>处理反馈</h4><el-form label-position="top"><el-form-item label="处理动作"><el-radio-group v-model="form.status"><el-radio value="processing">标记处理中</el-radio><el-radio value="resolved">标记已解决</el-radio></el-radio-group></el-form-item><el-form-item label="内部备注" :required="detail.status === 'processing' && form.status === 'processing'"><el-input v-model="form.internalNote" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="仅后台可见" /></el-form-item><el-form-item v-if="form.status === 'resolved'" label="用户可见处理结果" required><el-input v-model="form.resolution" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="将出现在用户站内通知中" /></el-form-item><el-button type="primary" :loading="saving" @click="save">保存处理结果</el-button></el-form></section>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getFeedback, updateFeedback } from '@/api/feedbacks'

const props = defineProps({ modelValue: Boolean, feedbackNo: String })
const emit = defineEmits(['update:modelValue', 'saved'])
const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const detail = ref(null)
const form = reactive({ status: 'processing', internalNote: '', resolution: '' })
const open = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const canWrite = computed(() => authStore.hasPermission('feedbacks.write'))
const previewUrls = computed(() => (detail.value?.attachments || []).filter((item) => item.available).map((item) => item.previewUrl))
const statusLabel = (value) => ({ submitted: '待处理', processing: '处理中', resolved: '已解决' }[value] || value)
const statusType = (value) => ({ submitted: 'warning', processing: 'primary', resolved: 'success' }[value] || 'info')
const typeLabel = (value) => ({ bug: '功能异常', suggestion: '产品建议', other: '其他' }[value] || value)
const notificationLabel = (value) => ({ pending: '待发送', sent: '已发送', failed: '补发中', not_required: '无需发送' }[value] || value)
const formatDate = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'

async function load() {
  if (!props.feedbackNo) return
  loading.value = true
  try { detail.value = await getFeedback(props.feedbackNo); form.status = detail.value.status === 'submitted' ? 'processing' : detail.value.status } catch (error) { ElMessage.error(error.userMessage || '获取反馈详情失败'); open.value = false } finally { loading.value = false }
}
function reset() { detail.value = null; form.status = 'processing'; form.internalNote = ''; form.resolution = '' }
async function save() {
  if (form.status === 'resolved' && !form.resolution.trim()) return ElMessage.warning('请填写用户可见处理结果')
  if (detail.value.status === 'processing' && form.status === 'processing' && !form.internalNote.trim()) return ElMessage.warning('请填写内部备注')
  saving.value = true
  try { detail.value = await updateFeedback(detail.value.feedbackNo, { expectedVersion: detail.value.version, status: form.status, internalNote: form.internalNote || undefined, resolution: form.resolution || undefined }); form.internalNote = ''; form.resolution = ''; ElMessage.success('处理已保存'); emit('saved'); open.value = false } catch (error) { if (error.response?.status === 409) { ElMessage.warning('反馈已被其他管理员更新，已刷新最新内容'); await load() } else ElMessage.error(error.userMessage || '保存失败') } finally { saving.value = false }
}
watch(() => [props.modelValue, props.feedbackNo], ([visible]) => { if (visible) load() })
</script>

<style scoped>
.section { margin-bottom: 24px; }
.section h4 { margin: 0 0 12px; font-size: 16px; }
.content { white-space: pre-wrap; line-height: 1.7; margin: 0; }
.images { display: flex; flex-wrap: wrap; gap: 12px; }
.image-cell { width: 120px; height: 90px; border: 1px solid #e4e7ed; border-radius: 4px; display: grid; place-items: center; color: #909399; font-size: 13px; overflow: hidden; }
.image-cell :deep(.el-image) { width: 100%; height: 100%; }
.process { border-top: 1px solid #ebeef5; padding-top: 20px; }
</style>
