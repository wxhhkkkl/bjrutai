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

      <el-form-item label="标签" prop="tags">
        <el-input
          v-model="tagsInput"
          placeholder="多个标签用逗号分隔（选填）"
          @change="parseTags"
        />
      </el-form-item>

      <el-form-item label="文章内容" prop="content">
        <div class="editor-toolbar">
          <span class="toolbar-hint">
            支持 HTML 格式。常用标签：&lt;p&gt;, &lt;b&gt;, &lt;i&gt;, &lt;h1&gt;-&lt;h6&gt;, &lt;ul&gt;, &lt;ol&gt;, &lt;li&gt;, &lt;a&gt;, &lt;img&gt;, &lt;br&gt;
          </span>
        </div>
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="15"
          placeholder="请输入文章内容（支持HTML）"
          maxlength="100000"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button
          v-if="isEditing"
          type="primary"
          :loading="saving"
          @click="handleSave"
        >
          保存修改
        </el-button>
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
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useArticlesStore } from '@/stores/articles'

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

function resetForm() {
  form.title = ''
  form.summary = ''
  form.category = ''
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
      tags: form.tags.length > 0 ? form.tags : undefined,
    }

    if (isEditing.value) {
      data.version = props.article.version
      await store.updateArticle(props.article.articleId, data)
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
