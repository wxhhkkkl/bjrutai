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
          <el-table-column prop="qualificationId" label="ID" width="70" />
          <el-table-column label="资质图片" width="100">
            <template #default="{ row }">
              <el-image
                v-if="firstFile(row)"
                :src="firstFile(row)"
                :preview-src-list="fileListOf(row)"
                preview-teleported
                fit="cover"
                style="width: 60px; height: 60px; border-radius: 4px; cursor: pointer"
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="legalEntityName" label="法人主体" min-width="140" />
          <el-table-column label="类型" width="180">
            <template #default="{ row }">
              <el-tag v-for="t in row.qualificationTypes" :key="t" size="small" style="margin-right: 4px">{{ typeLabel(t) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reviewComment" label="审核意见" min-width="140" />
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
        <el-form-item label="资质类型" required>
          <el-select v-model="form.qualificationTypes" multiple placeholder="请选择资质类型">
            <el-option label="营业执照" value="business_license" />
            <el-option label="医疗机构许可证" value="medical_institution_permit" />
            <el-option label="法人证书" value="legal_person_certificate" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传文件" required>
          <el-upload
            v-model:file-list="fileList"
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".jpg,.jpeg,.png,.gif,.webp"
          >
            <el-button size="small" type="primary">{{ uploading ? '上传中...' : '选择图片上传' }}</el-button>
          </el-upload>
          <el-image
            v-if="fileUrl"
            :src="fileUrl"
            :preview-src-list="[fileUrl]"
            preview-teleported
            fit="cover"
            style="width: 120px; height: 120px; margin-top: 10px; border-radius: 6px; cursor: pointer"
          />
        </el-form-item>
        <el-form-item label="法人主体" required>
          <el-input v-model="form.legalEntityName" maxlength="256" />
        </el-form-item>
        <el-form-item label="信用代码" required>
          <el-input v-model="form.creditCode" maxlength="64" />
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
const form = ref({ legalEntityName: '', creditCode: '', qualificationTypes: ['business_license'] })

function statusType(s) {
  return { reviewing: 'warning', approved: 'success', rejected: 'danger' }[s] || 'info'
}
function statusLabel(s) {
  return { reviewing: '审核中', approved: '已通过', rejected: '已驳回' }[s] || s
}
function typeLabel(t) {
  return { business_license: '营业执照', medical_institution_permit: '医疗机构许可证', legal_person_certificate: '法人证书' }[t] || t
}
function firstFile(row) {
  return (row.fileUrls && row.fileUrls[0] && row.fileUrls[0].url) || ''
}
function fileListOf(row) {
  return (row.fileUrls || []).map((f) => f.url).filter(Boolean)
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
  form.value = { legalEntityName: '', creditCode: '', qualificationTypes: ['business_license'] }
  fileUrl.value = ''
  fileList.value = []
  uploadVisible.value = true
}

async function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  if (!raw.type || !raw.type.startsWith('image/')) {
    ElMessage.warning('只支持上传图片（jpg/png/gif/webp）')
    fileList.value = []
    return
  }
  if (raw.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10MB')
    fileList.value = []
    return
  }
  uploading.value = true
  try {
    const result = await orgQualificationApi.uploadFile(raw)
    fileUrl.value = result.fileUrl
    ElMessage.success('图片已上传')
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
  if (form.value.qualificationTypes.length === 0 || !fileUrl.value || !form.value.legalEntityName || !form.value.creditCode) {
    ElMessage.warning('请填写完整资质信息（资质类型必选、上传图片、法人主体、信用代码）')
    return
  }
  saving.value = true
  try {
    await orgQualificationApi.upload(orgId, {
      ...form.value,
      fileUrls: [{ url: fileUrl.value, type: 'image', size: 0 }],
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
