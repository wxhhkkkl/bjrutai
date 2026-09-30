<template>
  <div class="article-video-upload">
    <input ref="input" type="file" accept=".mp4,.mov,video/mp4,video/quicktime" hidden @change="chooseFile" />
    <div v-if="displayVideo" class="article-video-upload__file">
      <strong>{{ displayVideo.fileName || '文章视频' }}</strong>
      <span>{{ statusText }}</span>
    </div>
    <video v-if="playerSource" :key="playerSource" ref="player"
      class="article-video-upload__player" :src="playerSource"
      :poster="localPreviewUrl ? '' : (displayVideo?.posterUrl || '')"
      controls preload="metadata" />
    <p v-if="localPreviewUrl" class="article-video-upload__hint">当前为本地预览，云端处理完成后会切换为正式播放视频。</p>
    <el-progress v-if="uploading" :percentage="progress" :stroke-width="8" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="article-video-upload__actions">
      <el-button v-if="!uploading" :disabled="!enabled" @click="input?.click()">{{ modelValue ? '更换视频' : '上传视频' }}</el-button>
      <el-button v-if="uploading" @click="cancelUpload">取消上传</el-button>
      <el-button v-if="error && selectedFile && !uploading" :disabled="!enabled" @click="upload(selectedFile)">重新上传</el-button>
      <el-button v-if="error && modelValue && !uploading" :disabled="!enabled" @click="resumePolling">刷新状态</el-button>
      <el-button v-if="modelValue && !uploading" :disabled="!enabled" @click="removeVideo">移除视频</el-button>
    </div>
    <p class="article-video-upload__hint">选填，单个 MP4/MOV 视频，最大 1 GB。更换或移除后需保存文章。</p>
    <p v-if="!enabled" class="article-video-upload__hint">当前账号没有视频编辑权限。</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { authorizeVideoUpload, readVideoState, validateVideoFile } from '@/api/article-videos'

const props = defineProps({ modelValue: { type: Object, default: null }, active: Boolean, enabled: Boolean })
const emit = defineEmits(['update:modelValue', 'busy'])
const input = ref(null)
const player = ref(null)
const candidate = ref(null)
const selectedFile = ref(null)
const localPreviewUrl = ref('')
const localPreviewVideoId = ref(null)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const displayVideo = computed(() => candidate.value || props.modelValue)
const playerSource = computed(() => localPreviewUrl.value || (
  displayVideo.value?.status === 'ready' ? displayVideo.value.playbackUrl || '' : ''
))
const statusText = computed(() => uploading.value ? `上传中 ${progress.value}%` : (
  displayVideo.value?.message || ({ authorized: '等待云端确认', processing: '视频处理中', ready: '视频已就绪',
    failed: '视频处理失败，请重新上传', deleting: '视频正在清理', deleted: '视频已清理' }[displayVideo.value?.status] || '')
))
let uploader = null
let uploadGeneration = 0
let pollGeneration = 0
let pollTimer = null

function setBusy(value) { uploading.value = value; emit('busy', value) }
function stopPolling() { pollGeneration += 1; clearTimeout(pollTimer); pollTimer = null }
function clearLocalPreview() {
  const url = localPreviewUrl.value
  localPreviewUrl.value = ''
  localPreviewVideoId.value = null
  if (url && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url)
}

function setLocalPreview(file) {
  clearLocalPreview()
  if (typeof URL.createObjectURL !== 'function') return
  try { localPreviewUrl.value = URL.createObjectURL(file) } catch { /* Upload can proceed without local preview. */ }
}

async function poll(videoId, generation, attempt = 0) {
  try {
    const video = await readVideoState(videoId)
    if (generation !== pollGeneration || !props.active) return
    error.value = ''
    emit('update:modelValue', video)
    if (['authorized', 'processing'].includes(video.status)) {
      // Leave the article editable, but let the user explicitly refresh after 15 minutes.
      if (attempt >= 180) { error.value = '视频处理时间较长，可保存草稿并稍后刷新状态'; return }
      pollTimer = setTimeout(() => poll(videoId, generation, attempt + 1), 5000)
    }
  } catch (err) {
    if (generation === pollGeneration && props.active) error.value = err.userMessage || err.message || '视频状态加载失败，请刷新状态'
  }
}

function resumePolling() {
  stopPolling()
  if (props.active && props.modelValue && props.enabled) poll(props.modelValue.videoId, pollGeneration)
}

function chooseFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) upload(file)
}

async function upload(file) {
  if (uploading.value || !props.enabled || !props.active) return
  try { validateVideoFile(file) } catch (err) { error.value = err.message; return }
  stopPolling()
  const generation = ++uploadGeneration
  player.value?.pause()
  selectedFile.value = file
  candidate.value = { fileName: file.name, status: 'selected' }
  setLocalPreview(file)
  error.value = ''
  progress.value = 0
  setBusy(true)
  try {
    const auth = await authorizeVideoUpload(file)
    if (generation !== uploadGeneration || !props.active) return
    candidate.value = { videoId: String(auth.videoId), status: 'authorized', fileName: file.name }
    localPreviewVideoId.value = String(auth.videoId)
    const { default: TcVod } = await import('vod-js-sdk-v6')
    if (generation !== uploadGeneration || !props.active) return
    const client = new TcVod({
      getSignature: () => Promise.resolve(auth.uploadSignature), allowReport: false,
      // SDK resume caches a previous VOD session by filename/size. Each retry
      // here has a new server context, so it must start a matching cloud session.
      enableResume: false,
    })
    uploader = client.upload({ mediaFile: file })
    uploader.on('media_progress', (event) => {
      if (generation === uploadGeneration) progress.value = Math.min(100, Math.round((event.percent || 0) * 100))
    })
    await uploader.done()
    if (generation !== uploadGeneration || !props.active) return
    emit('update:modelValue', candidate.value)
    candidate.value = null
    selectedFile.value = null
    // No FileId/URL from the browser is accepted as proof of readiness.
  } catch (err) {
    if (generation === uploadGeneration && props.active) {
      candidate.value = null
      clearLocalPreview()
      error.value = err.userMessage || '视频上传失败，请检查网络后重试'
    }
  } finally {
    if (generation === uploadGeneration) { uploader = null; setBusy(false) }
  }
}

function cancelUpload() {
  uploadGeneration += 1
  uploader?.cancel()
  uploader = null
  candidate.value = null
  selectedFile.value = null
  clearLocalPreview()
  error.value = ''
  setBusy(false)
}

function removeVideo() {
  stopPolling()
  player.value?.pause()
  error.value = ''
  candidate.value = null
  selectedFile.value = null
  clearLocalPreview()
  emit('update:modelValue', null)
}

watch(() => [props.modelValue?.videoId, props.modelValue?.status, props.modelValue?.playbackUrl], ([videoId, status, playbackUrl]) => {
  if (status === 'ready' && playbackUrl && videoId && String(videoId) === localPreviewVideoId.value) {
    clearLocalPreview()
  }
})

watch([() => props.active, () => props.modelValue?.videoId, () => props.enabled], () => {
  stopPolling()
  if (!props.active) { cancelUpload(); player.value?.pause(); return }
  if (props.enabled && props.modelValue && ['authorized', 'processing'].includes(props.modelValue.status)) resumePolling()
}, { immediate: true })
onBeforeUnmount(() => { stopPolling(); cancelUpload(); player.value?.pause() })
</script>

<style scoped>
.article-video-upload { width: 100%; }
.article-video-upload__file { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; overflow-wrap: anywhere; }
.article-video-upload__file span, .article-video-upload__hint { color: #909399; font-size: 12px; line-height: 1.6; }
.article-video-upload__player { display: block; width: 100%; max-height: 320px; background: #000; border-radius: 6px; margin-bottom: 12px; }
.article-video-upload__actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.article-video-upload__actions :deep(.el-button) { margin-left: 0; }
</style>
