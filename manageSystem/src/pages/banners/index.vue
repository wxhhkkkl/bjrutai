<template>
  <div class="banners-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">轮播图管理</h2>
        <p class="page-subtitle">已启用的轮播图将展示在小程序首页，排序值越小越靠前。</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        新建轮播图
      </el-button>
    </div>

    <div class="filter-bar">
      <el-radio-group v-model="statusFilter" @change="loadBanners">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="enabled">已启用</el-radio-button>
        <el-radio-button label="disabled">已停用</el-radio-button>
      </el-radio-group>
    </div>

    <el-table v-loading="loading" :data="items" stripe empty-text="暂无轮播图，请先新建一张">
      <el-table-column label="预览" width="190">
        <template #default="{ row }">
          <el-image
            :src="row.imageUrl"
            fit="cover"
            class="banner-thumb"
            :preview-src-list="[row.imageUrl]"
            preview-teleported
          />
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="180">
        <template #default="{ row }">{{ row.title || '未设置标题' }}</template>
      </el-table-column>
      <el-table-column label="点击动作" width="170">
        <template #default="{ row }">
          <span v-if="row.actionType === 'article'">跳转文章 #{{ row.articleId }}</span>
          <span v-else>不跳转</span>
        </template>
      </el-table-column>
      <el-table-column prop="sortOrder" label="排序" width="90" align="center" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
            {{ row.statusLabel }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ formatDate(row.updatedAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="row.status === 'disabled'"
            text
            type="success"
            size="small"
            @click="changeStatus(row, 'enable')"
          >启用</el-button>
          <el-button
            v-else
            text
            type="warning"
            size="small"
            @click="changeStatus(row, 'disable')"
          >停用</el-button>
          <el-button text type="danger" size="small" @click="removeBanner(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑轮播图' : '新建轮播图'" width="620px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="轮播图片" prop="imageUrl">
          <div class="image-control">
            <el-upload
              :show-file-list="false"
              accept="image/jpeg,image/png,image/gif,image/webp"
              :before-upload="validateImage"
              :http-request="uploadImage"
            >
              <div v-if="form.imageUrl" class="image-preview"><img :src="form.imageUrl" alt="轮播图预览" /></div>
              <div v-else class="image-placeholder">
                <el-icon><Plus /></el-icon>
                <span>上传图片</span>
              </div>
            </el-upload>
            <el-input v-model="form.imageUrl" class="image-url" placeholder="或输入 HTTPS 图片地址" clearable />
            <p class="field-hint">建议使用 5:2 横图，JPG/PNG/GIF/WebP，最大 10 MB。</p>
          </div>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="100" show-word-limit placeholder="选填，展示在图片底部" />
        </el-form-item>
        <el-form-item label="点击动作" prop="actionType">
          <el-radio-group v-model="form.actionType" @change="clearArticleWhenNone">
            <el-radio label="none">不跳转</el-radio>
            <el-radio label="article">跳转文章</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.actionType === 'article'" label="文章 ID" prop="articleId">
          <el-input-number v-model="form.articleId" :min="1" :precision="0" controls-position="right" />
          <span class="field-hint field-hint--inline">填写已发布文章的 ID。</span>
        </el-form-item>
        <el-form-item label="展示排序" prop="sortOrder">
          <el-input-number v-model="form.sortOrder" :min="0" :max="9999" :precision="0" controls-position="right" />
          <span class="field-hint field-hint--inline">数值越小越靠前。</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveBanner">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import http from '@/api/http'

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const statusFilter = ref('')
const dialogVisible = ref(false)
const editingId = ref('')
const formRef = ref()
const form = reactive(newForm())

const rules = {
  imageUrl: [
    { required: true, message: '请上传或填写轮播图片', trigger: 'blur' },
    { pattern: /^https?:\/\//i, message: '图片地址必须以 http:// 或 https:// 开头', trigger: 'blur' },
  ],
  title: [{ max: 100, message: '标题不能超过 100 个字符', trigger: 'blur' }],
  articleId: [{ validator: (_rule, value, callback) => {
    if (form.actionType === 'article' && (!Number.isInteger(value) || value < 1)) {
      callback(new Error('请输入有效的文章 ID'))
      return
    }
    callback()
  }, trigger: 'change' }],
}

function newForm() {
  return { title: '', imageUrl: '', actionType: 'none', articleId: null, sortOrder: 0, version: 1 }
}

function resetForm(value = newForm()) {
  Object.assign(form, newForm(), value)
}

function payload(response) {
  return response.data?.data || response.data || {}
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadBanners() {
  loading.value = true
  try {
    const params = statusFilter.value ? { status: statusFilter.value } : {}
    const data = payload(await http.get('/admin/banners', { params }))
    items.value = data.items || []
  } catch (error) {
    ElMessage.error(error.userMessage || '获取轮播图失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = ''
  resetForm()
  dialogVisible.value = true
}

function openEdit(item) {
  editingId.value = item.bannerId
  resetForm({
    title: item.title || '',
    imageUrl: item.imageUrl || '',
    actionType: item.actionType || 'none',
    articleId: item.articleId ? Number(item.articleId) : null,
    sortOrder: item.sortOrder || 0,
    version: item.version,
  })
  dialogVisible.value = true
}

function clearArticleWhenNone() {
  if (form.actionType === 'none') form.articleId = null
}

function validateImage(file) {
  if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)) {
    ElMessage.error('仅支持 JPG、PNG、GIF 或 WebP 图片')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片不能超过 10 MB')
    return false
  }
  return true
}

async function uploadImage({ file, onSuccess, onError }) {
  try {
    const uploadForm = new FormData()
    uploadForm.append('file', file, file.name)
    const data = payload(await http.post('/admin/banners/upload-image-file', uploadForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }))
    form.imageUrl = data.fileUrl
    ElMessage.success('图片上传成功')
    onSuccess?.()
  } catch (error) {
    ElMessage.error(error.userMessage || '图片上传失败')
    onError?.(error)
  }
}

async function saveBanner() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const data = {
      title: form.title.trim() || null,
      imageUrl: form.imageUrl.trim(),
      actionType: form.actionType,
      articleId: form.actionType === 'article' ? form.articleId : null,
      sortOrder: form.sortOrder,
    }
    if (editingId.value) {
      await http.put(`/admin/banners/${editingId.value}`, { ...data, version: form.version })
      ElMessage.success('轮播图已更新')
    } else {
      await http.post('/admin/banners', data)
      ElMessage.success('轮播图已创建，启用后会在首页显示')
    }
    dialogVisible.value = false
    await loadBanners()
  } catch (error) {
    ElMessage.error(error.response?.status === 409 ? '内容已被修改，请刷新后重试' : (error.userMessage || '保存失败'))
  } finally {
    saving.value = false
  }
}

async function changeStatus(item, action) {
  const nextLabel = action === 'enable' ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(`确认${nextLabel}“${item.title || '此轮播图'}”吗？`, `${nextLabel}确认`, {
      type: action === 'enable' ? 'info' : 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await http.post(`/admin/banners/${item.bannerId}/${action}`)
    ElMessage.success(`轮播图已${nextLabel}`)
    await loadBanners()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error.userMessage || `${nextLabel}失败`)
  }
}

async function removeBanner(item) {
  try {
    await ElMessageBox.confirm(`删除后无法恢复“${item.title || '此轮播图'}”，是否继续？`, '删除轮播图', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
    await http.delete(`/admin/banners/${item.bannerId}`)
    ElMessage.success('轮播图已删除')
    await loadBanners()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error.userMessage || '删除失败')
  }
}

onMounted(loadBanners)
</script>

<style scoped>
.banners-page { padding: 0; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
.page-title { margin: 0; color: #18202c; font-size: 22px; line-height: 1.35; }
.page-subtitle { margin: 8px 0 0; color: #7a8493; font-size: 13px; }
.filter-bar { margin-bottom: 14px; }
.banner-thumb { width: 160px; height: 64px; border-radius: 6px; background: #f3f5f8; }
.image-control { width: 100%; }
.image-preview, .image-placeholder { width: 300px; height: 120px; overflow: hidden; border: 1px dashed #ccd3dd; border-radius: 8px; background: #f7f9fc; }
.image-preview img { display: block; width: 100%; height: 100%; object-fit: cover; }
.image-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #8490a0; cursor: pointer; }
.image-placeholder .el-icon { font-size: 24px; }
.image-url { margin-top: 10px; max-width: 420px; }
.field-hint { margin: 7px 0 0; color: #8a94a3; font-size: 12px; line-height: 1.5; }
.field-hint--inline { margin: 0 0 0 10px; }
</style>
