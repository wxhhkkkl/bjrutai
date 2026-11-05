<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">文章分类</h2>
      <el-button type="primary" @click="openCreate">新建分类</el-button>
    </div>
    <el-card shadow="never">
      <el-table :data="store.categories" v-loading="store.loading" stripe>
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="sort_order" label="排序" width="100" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="editRow(row)">编辑</el-button>
            <el-button v-if="!row.home_section_key" text size="small" type="danger" @click="deleteRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑分类' : '新建分类'" width="400px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="分类名称" />
          <p v-if="editingHomeSectionKey" class="home-category-hint">
            该分类固定关联小程序首页“{{ homeSectionLabel(editingHomeSectionKey) }}”；修改名称后，首页入口和模块标题会同步更新。
          </p>
        </el-form-item>
        <el-form-item label="排序号" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCategoriesStore } from '@/stores/categories'

const store = useCategoriesStore()
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const editingHomeSectionKey = ref('')
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', sort_order: 0 })
const rules = { name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }] }
const homeSectionLabels = {
  about: '关于儒泰',
  wellness: '心脑维养',
  women: '女性专区',
  articles: '健康资讯',
}

onMounted(() => store.fetchCategories())

function homeSectionLabel(key) { return homeSectionLabels[key] || '首页入口' }
function openCreate() { isEdit.value = false; editId.value = null; editingHomeSectionKey.value = ''; form.name = ''; form.sort_order = 0; dialogVisible.value = true }
function editRow(row) { isEdit.value = true; editId.value = Number(row.id); editingHomeSectionKey.value = row.home_section_key || ''; form.name = row.name; form.sort_order = row.sort_order; dialogVisible.value = true }
function resetForm() { formRef.value?.resetFields(); editingHomeSectionKey.value = '' }

async function save() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (isEdit.value) { await store.updateCategory(editId.value, { name: form.name, sort_order: form.sort_order }); ElMessage.success('已更新') }
    else { await store.createCategory({ name: form.name, sort_order: form.sort_order }); ElMessage.success('已创建') }
    dialogVisible.value = false
  } catch (e) { ElMessage.error(e.userMessage || e.response?.data?.message || '操作失败') }
  finally { saving.value = false }
}

async function deleteRow(row) {
  try { await ElMessageBox.confirm(`确定删除分类 "${row.name}"？`, '确认', { type: 'warning' }) }
  catch { return }
  try { await store.deleteCategory(Number(row.id)); ElMessage.success('已删除') }
  catch (e) { ElMessage.error(e.userMessage || e.response?.data?.message || '删除失败') }
}

function formatTime(t) { if (!t) return '-'; try { return new Date(t).toLocaleString('zh-CN') } catch { return t } }
</script>

<style scoped>
.muted { color: #98a2b3; }
.home-category-hint { margin: 6px 0 0; color: #7a8493; font-size: 12px; line-height: 1.5; }
</style>
