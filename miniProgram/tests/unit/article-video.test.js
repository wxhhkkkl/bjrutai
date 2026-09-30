const test = require('node:test')
const assert = require('node:assert/strict')
const { adaptArticleDetail } = require('../../models/article')
const fs = require('node:fs')
const path = require('node:path')

const article = { articleId: '1', title: '视频文章', status: 'published', content: '<p>正文</p>' }

test('old articles have no video; valid HTTPS video uses article cover as fallback', () => {
  assert.equal(adaptArticleDetail(article).video, null)
  const result = adaptArticleDetail({ ...article, coverImageUrl: 'https://example.cn/cover.jpg', video: {
    playbackUrl: 'https://vod.example.cn/a.mp4', posterUrl: null, durationSeconds: 12
  } })
  assert.equal(result.video.playbackUrl, 'https://vod.example.cn/a.mp4')
  assert.equal(result.video.posterUrl, 'https://example.cn/cover.jpg')
})

test('invalid video does not prevent reading article text', () => {
  for (const video of [{ playbackUrl: 'javascript:alert(1)' }, { playbackUrl: 'http://example.cn/a.mp4' }, [], 'invalid']) {
    const result = adaptArticleDetail({ ...article, video })
    assert.equal(result.video, null)
    assert.equal(result.content, '<p>正文</p>')
  }
})

test('native video is between summary and body, without autoplay or empty-body placeholder', () => {
  const template = fs.readFileSync(path.resolve(__dirname, '../../pages/article-detail/index.wxml'), 'utf8')
  const summary = template.indexOf('article-detail-summary')
  const video = template.indexOf('id="articleVideo"')
  const body = template.indexOf('class="article-content"')
  assert.ok(summary < video && video < body)
  assert.match(template, /autoplay="\{\{false\}\}"/)
  assert.match(template, /show-fullscreen-btn="\{\{true\}\}"/)
  assert.match(template, /wx:elif="\{\{!article.video\}\}"/)
})
