<template>
  <el-dialog
    :model-value="visible"
    :title="isEditing ? '编辑文章' : '新建文章'"
    width="800px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @closed="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item label="文章标题" prop="title">
        <el-input
          v-model="form.title"
          placeholder="请输入文章标题（2-200字）"
          maxlength="200"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="文章摘要" prop="summary">
        <el-input
          v-model="form.summary"
          type="textarea"
          :rows="2"
          placeholder="请输入文章摘要（选填，最多500字）"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="文章分类" prop="category">
        <el-input
          v-model="form.category"
          placeholder="请输入分类（选填）"
          maxlength="50"
        />
      </el-form-item>

      <el-form-item label="封面图片" prop="coverImageUrl">
        <el-input
          v-model="form.coverImageUrl"
          placeholder="请输入封面图片URL（选填）"
        />
      </el-form-item>

      <el-form-item label="分类" prop="category_id">
        <el-select v-model="form.category_id" placeholder="选择分类" clearable style="width: 100%">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="Number(c.id)" />
        </el-select>
      </el-form-item>

      <el-form-item label="标签" prop="tags">
        <el-input
          v-model="tagsInput"
          placeholder="多个标签用逗号分隔（选填）"
          @change="parseTags"
        />
      </el-form-item>

      <el-form-item label="文章内容" prop="content">
        <ArticleEditor v-model="form.content" />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button @click="handlePreview">预览</el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="handleSave"
        >
          {{ isEditing ? '保存修改' : '保存草稿' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useArticlesStore } from '@/stores/articles'
import { useCategoriesStore } from '@/stores/categories'
import ArticleEditor from '@/components/ArticleEditor.vue'

const categoriesStore = useCategoriesStore()
const categories = computed(() => categoriesStore.categories)

const props = defineProps({
  visible: { type: Boolean, default: false },
  article: { type: Object, default: null },
})

const emit = defineEmits(['update:visible', 'saved'])

const store = useArticlesStore()
const formRef = ref(null)
const saving = ref(false)
const tagsInput = ref('')

const isEditing = computed(() => !!props.article)

const form = reactive({
  title: '',
  summary: '',
  category: '',
  category_id: null,
  coverImageUrl: '',
  tags: [],
  content: '',
})

const rules = {
  title: [
    { required: true, message: '请输入文章标题', trigger: 'blur' },
    { min: 2, max: 200, message: '标题长度在2-200字之间', trigger: 'blur' },
  ],
  content: [
    { max: 100000, message: '内容不能超过100,000字符', trigger: 'blur' },
  ],
  summary: [
    { max: 500, message: '摘要不能超过500字符', trigger: 'blur' },
  ],
  coverImageUrl: [
    { max: 2048, message: '封面图片URL不能超过2048字符', trigger: 'blur' },
  ],
}

// Watch for article prop to populate form
watch(
  () => props.article,
  (val) => {
    if (val) {
      form.title = val.title || ''
      form.summary = val.summary || ''
      form.category = val.category || ''
      form.category_id = val.category_id || null
      form.coverImageUrl = val.coverImageUrl || ''
      form.tags = val.tags || []
      form.content = val.content || ''
      tagsInput.value = (val.tags || []).join(', ')
    } else {
      resetForm()
    }
  },
  { immediate: true }
)

function parseTags() {
  if (!tagsInput.value) {
    form.tags = []
    return
  }
  form.tags = tagsInput.value
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
    .slice(0, 20)
}

onMounted(() => { categoriesStore.fetchCategories() })

function resetForm() {
  form.title = ''
  form.summary = ''
  form.category = ''
  form.category_id = null
  form.coverImageUrl = ''
  form.tags = []
  form.content = ''
  tagsInput.value = ''
  saving.value = false
  formRef.value?.resetFields()
}

function handleCancel() {
  emit('update:visible', false)
}

function handlePreview() {
  // Open preview in new tab using current form content
  const previewWin = window.open('', '_blank')
  if (previewWin) {
    previewWin.document.write(`<!DOCTYPE html><html><head><meta charset=utf-8><title>预览: ${form.title || '文章'}</title><style>body{max-width:780px;margin:40px auto;padding:0 20px;font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:16px;line-height:1.9;color:#303133} img{max-width:100%;height:auto;border-radius:4px} h1{font-size:28px} .meta{color:#909399;font-size:14px;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #eee}</style></head><body><h1>${form.title||'无标题'}</h1><div class=meta>${form.category||''}</div>${form.content||'<p style=color:#999>暂无内容</p>'}</body></html>`)
    previewWin.document.close()
  }
}

async function handleSave() {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    const data = {
      title: form.title,
      summary: form.summary || undefined,
      content: form.content || undefined,
      coverImageUrl: form.coverImageUrl || undefined,
      category: form.category || undefined,
      category_id: form.category_id || undefined,
      tags: form.tags.length > 0 ? form.tags : undefined,
    }

    if (isEditing.value) {
      data.version = props.article.version
      await store.updateArticle(props.article.articleId || props.article.id, data)
    } else {
      await store.createArticle(data)
    }

    emit('saved')
  } catch (e) {
    // Error handled in store
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.editor-toolbar {
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #909399;
}

.toolbar-hint {
  line-height: 1.6;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
