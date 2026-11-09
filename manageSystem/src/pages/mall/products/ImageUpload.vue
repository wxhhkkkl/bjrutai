<template>
  <div class="image-upload">
    <label>{{ label }}
      <input
        type="file"
        accept="image/jpeg,image/png"
        :disabled="disabled || busy"
        @change="select"
      ></label>
    <span v-if="value">已上传并核验</span>
    <span v-if="busy">正在上传并核验…</span>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button
      v-if="state && error"
      :disabled="busy || disabled"
      @click="upload"
    >
      重试图片上传
    </el-button>
    <p>JPG / PNG，最多 5 MB；私有存储未开启时无法上传。</p>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { commandKey } from '@/composables/useMallCommand'
import { uploadProductImage } from '@/api/mall-catalog'
defineProps({
  label: { type: String, default: '' },
  value: { type: String, default: '' },
  disabled: Boolean,
})
const emit = defineEmits(['uploaded', 'busy'])
const busy = ref(false),
  error = ref('')
let state = null
async function select(event) {
  const file = event.target.files?.[0]
  if (!file) return
  state = { file, ticketKey: commandKey(), verifyKey: commandKey() }
  event.target.value = ''
  await upload()
}
async function upload() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  emit('busy', true)
  try {
    emit('uploaded', (await uploadProductImage(state)).id, state.file)
  } catch (e) {
    error.value = e.userMessage || e.message
  } finally {
    busy.value = false
    emit('busy', false)
  }
}
</script>
<style scoped>
.image-upload {
  margin: 12px 0;
}
p {
  font-size: 12px;
  color: #606266;
}
</style>
