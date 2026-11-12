<template>
  <div
    class="image-upload"
    :class="{
      'image-upload--compact': compact,
      'image-upload--meta-below': metaBelow,
    }"
  >
    <input
      ref="fileInput"
      class="visually-hidden"
      type="file"
      accept="image/jpeg,image/png"
      :disabled="disabled || busy"
      @change="select"
    />
    <div class="image-upload__tile-column">
      <button
        class="upload-tile"
        :class="`upload-tile--${variant}`"
        type="button"
        :disabled="disabled || busy"
        :aria-label="`${label}：${previewUrl ? '更换图片' : '上传图片'}`"
        @click="fileInput?.click()"
      >
        <img v-if="previewUrl" :src="previewUrl" alt="" />
        <el-icon v-else :size="24"><Plus /></el-icon>
        <span v-if="busy" class="uploading-mask">上传中</span>
      </button>
      <el-button
        v-if="state && error"
        class="upload-retry"
        size="small"
        :disabled="busy || disabled"
        @click="upload"
      >
        重试图片上传
      </el-button>
    </div>
    <div v-if="!compact" class="image-upload__meta">
      <span v-if="busy" class="upload-status">正在上传并核验…</span>
      <p class="product-hint">JPG / PNG，单张最多 5 MB。</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { uploadProductImage } from '@/api/mall-catalog'
import { useMallToast } from '@/composables/useMallToast'

defineProps({
  label: { type: String, default: '' },
  previewUrl: { type: String, default: '' },
  variant: { type: String, default: 'square' },
  compact: Boolean,
  metaBelow: Boolean,
  disabled: Boolean,
})

const emit = defineEmits(['uploaded', 'busy'])
const fileInput = ref(null)
const busy = ref(false)
const error = ref('')
useMallToast(error)
let state = null

async function select(event) {
  const file = event.target.files?.[0]
  if (!file) return
  state = { file }
  event.target.value = ''
  await upload()
}

async function upload() {
  if (busy.value || !state) return
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
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}
.image-upload--compact {
  flex: 0 0 var(--product-image-size);
  width: var(--product-image-size);
  gap: 0;
}
.image-upload__tile-column {
  flex: 0 0 var(--product-image-size);
  width: var(--product-image-size);
}
.visually-hidden {
  display: none;
}
.upload-tile {
  position: relative;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: var(--app-radius-md);
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    background-color 0.15s ease;
}
.upload-retry {
  margin-top: 4px;
}
.upload-tile:hover:not(:disabled) {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.upload-tile:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.upload-tile:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.upload-tile img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.uploading-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #fff;
  background: rgb(31 36 45 / 55%);
  font-size: 12px;
}
.image-upload__meta {
  flex: 1 1 auto;
  min-width: 150px;
  padding-top: 2px;
}
.image-upload--meta-below {
  flex-direction: column;
  gap: 8px;
}
.image-upload--meta-below .image-upload__meta {
  flex: 0 0 auto;
  width: max-content;
  min-width: max-content;
  padding-top: 0;
}
.image-upload__meta p {
  margin: 0;
  white-space: nowrap;
}
.upload-status {
  display: block;
  margin-bottom: 4px;
  color: var(--el-color-success);
  font-size: 12px;
}
</style>
