<template>
  <div class="quill-editor-wrapper">
    <QuillEditor
      ref="quillRef"
      v-model:content="model"
      :options="editorOptions"
      contentType="html"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])
const quillRef = ref(null)
const MAX_IMAGE_SIZE = 10 * 1024 * 1024

const model = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const editorOptions = {
  theme: 'snow',
  modules: {
    toolbar: {
      container: [
        [{ header: [1,2,3,false] }],
        ['bold','italic','underline'],
        [{ list:'ordered' },{ list:'bullet' }],
        ['link','image'],
        ['clean'],
      ],
      handlers: { image: imageHandler },
    },
  },
  placeholder: '请输入文章内容...',
}

function validateImageFile(file) {
  if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)) {
    ElMessage.error('仅支持 JPG/PNG/GIF/WebP 格式')
    return false
  }
  if (file.size > MAX_IMAGE_SIZE) {
    ElMessage.error('单张图片不能超过 10MB')
    return false
  }
  return true
}

async function uploadAndInsertImage(file) {
  if (!validateImageFile(file)) return
  try {
    const uploadForm = new FormData()
    uploadForm.append('file', file, file.name || 'article-image.png')
    const res = await http.post('/admin/articles/upload-image-file', uploadForm, {
      headers: { 'Content-Type': undefined },
    })
    const { fileUrl } = res.data.data || res.data
    if (!fileUrl) throw new Error('上传结果缺少图片地址')
    const quill = quillRef.value?.getQuill()
    if (!quill) return
    const range = quill.getSelection(true) || { index: quill.getLength(), length: 0 }
    quill.insertEmbed(range.index, 'image', fileUrl, 'user')
    quill.setSelection(range.index + 1, 0, 'silent')
  } catch (error) {
    ElMessage.error(`上传失败：${error.userMessage || error.message || '网络错误'}`)
  }
}

function imageHandler() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/jpeg,image/png,image/gif,image/webp'
  input.onchange = (event) => {
    const file = event.target.files?.[0]
    if (file) uploadAndInsertImage(file)
  }
  input.click()
}

function interceptPastedOrDroppedImages(event) {
  const files = Array.from(event.clipboardData?.files || event.dataTransfer?.files || [])
    .filter((file) => file.type.startsWith('image/'))
  if (!files.length) return
  event.preventDefault()
  files.reduce(
    (sequence, file) => sequence.then(() => uploadAndInsertImage(file)),
    Promise.resolve(),
  )
}

function rejectInlineImage(node, delta) {
  if (/^data:image\//i.test(node.getAttribute('src') || '')) {
    ElMessage.warning('请使用图片上传功能插入图片，不能直接粘贴内嵌图片')
    return { ops: [] }
  }
  return delta
}

onMounted(async () => {
  await nextTick()
  const quill = quillRef.value?.getQuill()
  if (!quill) return
  quill.root.addEventListener('paste', interceptPastedOrDroppedImages)
  quill.root.addEventListener('drop', interceptPastedOrDroppedImages)
  quill.clipboard.addMatcher('IMG', rejectInlineImage)
})

onBeforeUnmount(() => {
  const quill = quillRef.value?.getQuill()
  quill?.root.removeEventListener('paste', interceptPastedOrDroppedImages)
  quill?.root.removeEventListener('drop', interceptPastedOrDroppedImages)
})
</script>

<style>
.quill-editor-wrapper .ql-editor { min-height: 400px; font-size: 15px; line-height: 1.8; }
.quill-editor-wrapper .ql-toolbar { border-radius: 4px 4px 0 0; border-color: #dcdfe6; }
.quill-editor-wrapper .ql-container { border-radius: 0 0 4px 4px; border-color: #dcdfe6; font-family: 'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif; }
</style>
