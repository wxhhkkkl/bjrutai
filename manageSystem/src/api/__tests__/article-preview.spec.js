import { expect, it } from 'vitest'
import { buildArticlePreview } from '@/utils/article-preview'

it('escapes metadata and permits playback only for a ready HTTPS video in a script-free sandbox', () => {
  const value = buildArticlePreview({ title: '<script>alert(1)</script>', content: '<p>正文</p>',
    video: { status: 'ready', playbackUrl: 'https://vod.example.cn/a.mp4' } })
  expect(value).toContain('&lt;script&gt;')
  expect(value).toContain('<video controls')
  expect(value).toContain("default-src 'none'")
  expect(buildArticlePreview({ video: { status: 'processing', playbackUrl: 'https://vod.example.cn/a.mp4' } })).not.toContain('<video')
  expect(buildArticlePreview({ video: { status: 'ready', playbackUrl: 'javascript:alert(1)' } })).not.toContain('<video')
})
