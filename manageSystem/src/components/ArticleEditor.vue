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
import { computed, ref } from 'vue'
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])
const quillRef = ref(null)

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

function imageHandler() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = 'image/jpeg,image/png,image/gif,image/webp'
  input.onchange = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    if (!['image/jpeg','image/png','image/gif','image/webp'].includes(file.type)) { ElMessage.error('仅支持 JPG/PNG/GIF/WebP'); return }
    if (file.size > 10485760) { ElMessage.error('图片不超过10MB'); return }
    try {
      const res = await http.post('/admin/articles/upload-image',{ fileName:file.name, contentType:file.type })
      const { uploadUrl, fileUrl } = res.data.data || res.data
      await fetch(uploadUrl,{ method:'PUT',body:file,headers:{'Content-Type':file.type} })
      const q = quillRef.value?.getQuill(); if (q) { const r = q.getSelection(true); q.insertEmbed(r.index,'image',fileUrl); q.setSelection(r.index+1) }
    } catch(err) { ElMessage.error('上传失败: '+(err.userMessage||err.message||'网络错误')) }
  }
  input.click()
}
</script>

<style>
.quill-editor-wrapper .ql-editor { min-height: 400px; font-size: 15px; line-height: 1.8; }
.quill-editor-wrapper .ql-toolbar { border-radius: 4px 4px 0 0; border-color: #dcdfe6; }
.quill-editor-wrapper .ql-container { border-radius: 0 0 4px 4px; border-color: #dcdfe6; font-family: 'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif; }
</style>
