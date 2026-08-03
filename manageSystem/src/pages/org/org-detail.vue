<template>
  <div class="org-detail">
    <el-page-header @back="$router.back()" :content="`组织详情 — ${orgName}`" />

    <el-tabs v-model="activeTab" style="margin-top: 16px">
      <el-tab-pane label="资质文件" name="qualification">
        <div class="qual-toolbar">
          <el-button type="primary" @click="openUpload">
            <el-icon style="margin-right: 4px"><Upload /></el-icon>上传资质
          </el-button>
        </div>

        <el-table :data="qualifications" v-loading="loading" border style="width: 100%">
          <el-table-column prop="qualificationId" label="ID" width="80" />
          <el-table-column prop="legalEntityName" label="法人主体" />
          <el-table-column label="类型" width="200">
            <template #default="{ row }">
              <el-tag v-for="t in row.qualificationTypes" :key="t" size="small" style="margin-right: 4px">{{ t }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="validUntil" label="有效期至" width="120" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reviewComment" label="审核意见" min-width="160" />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'reviewing'"
                size="small"
                type="success"
                @click="review(row, 'approve')"
              >通过</el-button>
              <el-button
                v-if="row.status === 'reviewing'"
                size="small"
                type="danger"
                @click="review(row, 'reject')"
              >驳回</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- Upload dialog -->
    <el-dialog v-model="uploadVisible" title="上传组织资质" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="法人主体" required>
          <el-input v-model="form.legalEntityName" maxlength="256" />
        </el-form-item>
        <el-form-item label="信用代码" required>
          <el-input v-model="form.creditCode" maxlength="64" />
        </el-form-item>
        <el-form-item label="资质类型" required>
          <el-select v-model="form.qualificationTypes" multiple placeholder="请选择资质类型">
            <el-option label="营业执照" value="business_license" />
            <el-option label="医疗机构许可证" value="medical_institution_permit" />
            <el-option label="法人证书" value="legal_person_certificate" />
          </el-select>
        </el-form-item>
        <el-form-item label="有效期至" required>
          <el-date-picker v-model="form.validUntil" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="资质文件" required>
          <el-upload
            v-model:file-list="fileList"
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".jpg,.jpeg,.png,.pdf"
          >
            <el-button size="small" type="primary">选择文件并上传至腾讯 COS</el-button>
          </el-upload>
          <div v-if="fileUrl" class="file-url-tip">已上传：{{ fileUrl }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { orgQualificationApi } from '@/api/org'

const route = useRoute()
const orgId = route.params.orgId || route.query.orgId
const orgName = ref(route.query.orgName || `组织 #${orgId}`)

const activeTab = ref('qualification')
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const qualifications = ref([])
const uploadVisible = ref(false)
const fileUrl = ref('')
const fileList = ref([])
const form = ref({ legalEntityName: '', creditCode: '', qualificationTypes: ['business_license'], validUntil: '' })

function statusType(s) {
  return { reviewing: 'warning', approved: 'success', rejected: 'danger' }[s] || 'info'
}
function statusLabel(s) {
  return { reviewing: '审核中', approved: '已通过', rejected: '已驳回' }[s] || s
}

async function load() {
  loading.value = true
  try {
    const data = await orgQualificationApi.list(orgId)
    qualifications.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '加载资质失败')
  } finally {
    loading.value = false
  }
}

function openUpload() {
  form.value = { legalEntityName: '', creditCode: '', qualificationTypes: ['business_license'], validUntil: '' }
  fileUrl.value = ''
  fileList.value = []
  uploadVisible.value = true
}

async function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  if (raw.size > 10 * 1024 * 1024) {
    ElMessage.warning('文件大小不能超过 10MB')
    fileList.value = []
    return
  }
  uploading.value = true
  try {
    const token = await orgQualificationApi.uploadToken({
      fileName: raw.name,
      contentType: raw.type || 'application/octet-stream',
      fileSize: raw.size,
    })
    await fetch(token.uploadUrl, { method: 'PUT', body: raw, headers: { 'Content-Type': raw.type } })
    fileUrl.value = token.fileUrl
    ElMessage.success('已上传到腾讯 COS')
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '上传失败')
    fileUrl.value = ''
    fileList.value = []
  } finally {
    uploading.value = false
  }
}

function onFileRemove() {
  fileUrl.value = ''
}

async function submitUpload() {
  if (!form.value.legalEntityName || !form.value.creditCode || form.value.qualificationTypes.length === 0 || !form.value.validUntil || !fileUrl.value) {
    ElMessage.warning('请填写完整资质信息（资质类型必选，并上传资质文件）')
    return
  }
  saving.value = true
  try {
    await orgQualificationApi.upload(orgId, {
      ...form.value,
      fileUrls: [{ url: fileUrl.value, type: form.value.qualificationTypes.join(','), size: 0 }],
    })
    ElMessage.success('上传成功，等待审核')
    uploadVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '上传失败')
  } finally {
    saving.value = false
  }
}

async function review(row, action) {
  const comment = action === 'reject' ? (window.prompt('请输入驳回原因') || '') : undefined
  if (action === 'reject' && !comment) {
    ElMessage.warning('驳回必须填写原因')
    return
  }
  try {
    await orgQualificationApi.review(row.qualificationId, { action, comment })
    ElMessage.success(action === 'approve' ? '已通过' : '已驳回')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '审核失败')
  }
}

onMounted(load)
</script>

<style scoped>
.org-detail { padding: 16px; }
.qual-toolbar { margin-bottom: 12px; }
.file-url-tip { margin-top: 8px; font-size: 12px; color: #67c23a; word-break: break-all; }
</style>
