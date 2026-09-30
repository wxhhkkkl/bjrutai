import { describe, expect, it } from 'vitest'
import { validateVideoFile, normalizeVideoState } from '../article-videos'

describe('article VOD media boundaries', () => {
  it('accepts MP4/MOV up to 1 GB, including browsers without a MIME type', () => {
    expect(validateVideoFile({ name: 'video.MOV', type: '', size: 1_073_741_824 })).toBe('video/quicktime')
    expect(validateVideoFile({ name: 'video.mp4', type: 'video/mp4', size: 1 })).toBe('video/mp4')
    for (const file of [
      { name: 'video.exe', type: 'video/mp4', size: 1 },
      { name: 'video.mp4', type: 'video/quicktime', size: 1 },
      { name: 'video.mp4', type: 'video/mp4', size: 1_073_741_825 },
      { name: 'video.mp4', type: 'video/mp4', size: 0 },
    ]) expect(() => validateVideoFile(file)).toThrow()
  })

  it('rejects malformed status and never previews unsafe URLs', () => {
    expect(() => normalizeVideoState({ videoId: '1', status: 'unknown' })).toThrow()
    const video = normalizeVideoState({ videoId: '1', status: 'ready', fileName: 'clip.mp4', playbackUrl: 'javascript:alert(1)' })
    expect(video.playbackUrl).toBeNull()
    expect(normalizeVideoState({ videoId: '1', status: 'processing', playbackUrl: 'https://vod.example.cn/a.mp4' }).playbackUrl).toBeNull()
  })
})
