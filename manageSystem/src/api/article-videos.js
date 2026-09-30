import http from './http'

export function validateVideoFile(file) {
  const mime = { mp4: 'video/mp4', mov: 'video/quicktime' }[String(file?.name || '').split('.').pop().toLowerCase()]
  if (!mime || (file.type && file.type !== mime)) throw new Error('仅支持 MP4/MOV 视频')
  if (!Number.isSafeInteger(file.size) || file.size <= 0 || file.size > 1_073_741_824) throw new Error('视频大小需在 1 GB 以内，不能上传空文件')
  return mime
}

function httpsUrl(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? value : null
  } catch { return null }
}

export function normalizeVideoState(value) {
  if (!value || !/^[1-9]\d*$/.test(String(value.videoId)) ||
      !['authorized', 'processing', 'ready', 'failed', 'deleting', 'deleted'].includes(value.status)) {
    throw new Error('视频状态数据异常，请重试')
  }
  return {
    videoId: String(value.videoId), fileName: String(value.fileName || ''), status: value.status,
    message: String(value.message || ''),
    playbackUrl: value.status === 'ready' ? httpsUrl(value.playbackUrl) : null,
    posterUrl: value.status === 'ready' ? httpsUrl(value.posterUrl) : null,
    durationSeconds: Number.isFinite(value.durationSeconds) ? value.durationSeconds : null,
  }
}

export async function authorizeVideoUpload(file) {
  const res = await http.post('/admin/article-videos/uploads', {
    fileName: file.name, contentType: validateVideoFile(file), sizeBytes: file.size,
  })
  const data = res.data.data
  if (!data?.uploadSignature || !data?.videoId) throw new Error('上传授权数据异常，请重试')
  return data
}

export async function readVideoState(videoId) {
  const res = await http.get(`/admin/article-videos/${videoId}`)
  return normalizeVideoState(res.data.data)
}
