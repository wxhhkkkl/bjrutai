<template>
  <el-dialog
    v-model="visible"
    title="资质审核"
    width="560px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <!-- Qualification details -->
    <div v-if="!qualificationData" class="empty-state">
      无法加载资质信息
    </div>
    <template v-else>
      <el-descriptions :column="2" border size="small" class="review-descriptions">
        <el-descriptions-item label="法人实体">
          {{ qualificationData.legal_entity || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="资质类型">
          {{ qualificationData.qualification_type || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="统一社会信用代码">
          {{ maskCreditCode(qualificationData.credit_code) }}
        </el-descriptions-item>
        <el-descriptions-item label="有效期至">
          {{ formatDate(qualificationData.expires_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="store.getStatusType(qualificationData.status)" size="small">
            {{ store.getStatusLabel(qualificationData.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="提交时间">
          {{ formatDate(qualificationData.submitted_at || qualificationData.created_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- File info -->
      <div v-if="qualificationData.file_name" class="file-section">
        <span class="file-label">资质文件：</span>
        <span class="file-name">{{ qualificationData.file_name }}</span>
        <span v-if="qualificationData.file_type" class="file-type">（{{ qualificationData.file_type.toUpperCase() }}）</span>
        <el-button
          v-if="qualificationData.file_url"
          size="small"
          type="primary"
          link
          @click="previewFile"
          style="margin-left: 8px"
        >
          <el-icon style="margin-right: 4px"><View /></el-icon>预览文件
        </el-button>
      </div>

      <!-- Review history -->
      <div v-if="showHistory" class="review-history">
        <el-divider content-position="left">审核记录</el-divider>
        <div v-if="historyLoading" style="text-align: center; padding: 16px">
          <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        </div>
        <el-timeline v-else-if="store.reviews.length > 0">
          <el-timeline-item
            v-for="item in store.reviews"
            :key="item.id"
            :timestamp="formatDate(item.created_at)"
            placement="top"
          >
            <div class="history-item">
              <span class="history-action">
                {{ item.action === 'approve' ? '审核通过' : '审核驳回' }}
              </span>
              <span v-if="item.reviewer" class="history-reviewer">— {{ item.reviewer }}</span>
              <p v-if="item.comment" class="history-comment">{{ item.comment }}</p>
            </div>
          </el-timeline-item>
        </el-timeline>
        <div v-else style="text-align: center; color: #909399; padding: 12px">暂无审核记录</div>
      </div>

      <!-- Review action (only for reviewing status) -->
      <div v-if="qualificationData.status === 'reviewing'" class="review-action">
        <el-divider content-position="left">审核操作</el-divider>
        <el-form ref="formRef" :model="reviewForm" :rules="rules" label-width="80px">
          <el-form-item label="审核意见" prop="comment" v-if="reviewForm.action === 'reject'">
            <el-input
              v-model="reviewForm.comment"
              type="textarea"
              :rows="3"
              placeholder="请输入驳回原因"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <template v-if="qualificationData && qualificationData.status === 'reviewing'">
        <el-button type="danger" :loading="submitting" @click="handleReview('reject')">
          驳回
        </el-button>
        <el-button type="primary" :loading="submitting" @click="handleReview('approve')">
          通过
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useQualificationsStore } from '@/stores/qualifications'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  qualificationData: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'success'])

const store = useQualificationsStore()

const visible = ref(props.modelValue)
const submitting = ref(false)
const showHistory = ref(false)
const historyLoading = ref(false)
const formRef = ref(null)

const reviewForm = reactive({
  action: '',
  comment: '',
})

const rules = {
  comment: [
    { required: true, message: '驳回原因不能为空', trigger: 'blur' },
  ],
}

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && props.qualificationData) {
    loadReviewHistory()
  }
})
watch(visible, (val) => { emit('update:modelValue', val) })

function formatDate(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function maskCreditCode(code) {
  if (!code) return '-'
  if (code.length <= 8) return code
  const prefix = code.slice(0, 4)
  const suffix = code.slice(-4)
  const masked = prefix + '****' + suffix
  return masked
}

function previewFile() {
  if (props.qualificationData?.file_url) {
    window.open(props.qualificationData.file_url, '_blank')
  }
}

async function loadReviewHistory() {
  if (!props.qualificationData?.id) return
  showHistory.value = true
  historyLoading.value = true
  try {
    await store.fetchReviews(props.qualificationData.id)
  } finally {
    historyLoading.value = false
  }
}

async function handleReview(action) {
  if (action === 'reject') {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
  }

  submitting.value = true
  try {
    await store.reviewQualification(
      props.qualificationData.id,
      action,
      action === 'reject' ? reviewForm.comment : ''
    )
    visible.value = false
    emit('success')
  } finally {
    submitting.value = false
  }
}

function handleClosed() {
  reviewForm.action = ''
  reviewForm.comment = ''
  showHistory.value = false
  formRef.value?.resetFields()
}
</script>

<style scoped>
.empty-state {
  text-align: center;
  color: #909399;
  padding: 40px;
}

.review-descriptions {
  margin-bottom: 16px;
}

.file-section {
  display: flex;
  align-items: center;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 8px;
}

.file-label {
  font-size: 14px;
  color: #606266;
}

.file-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.file-type {
  font-size: 12px;
  color: #909399;
}

.review-history {
  margin-top: 8px;
}

.history-item {
  font-size: 14px;
}

.history-action {
  font-weight: 500;
  color: #303133;
}

.history-reviewer {
  font-size: 12px;
  color: #909399;
}

.history-comment {
  margin-top: 4px;
  font-size: 13px;
  color: #606266;
}

.review-action {
  margin-top: 8px;
}
</style>
