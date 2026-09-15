const test = require('node:test')
const assert = require('node:assert/strict')

const { adaptBanner, adaptBannerList, normalizeBannerId } = require('../../models/banner')

const source = {
  bannerId: '0012',
  title: ' 秋季健康活动 ',
  imageUrl: 'https://example.com/banner.webp',
  actionType: 'article',
  articleId: '008',
  sortOrder: 3
}

test('normalizes public banner data and an article action', () => {
  assert.deepEqual(adaptBanner(source), {
    bannerId: '12',
    title: '秋季健康活动',
    imageUrl: 'https://example.com/banner.webp',
    actionType: 'article',
    articleId: '8',
    sortOrder: 3
  })
  assert.equal(normalizeBannerId('004'), '4')
})

test('requires valid identifiers, image URLs and explicit action types', () => {
  assert.throws(() => adaptBanner({ ...source, bannerId: '0' }), /轮播图 ID/)
  assert.throws(() => adaptBanner({ ...source, imageUrl: '/banner.png' }), /图片地址/)
  assert.throws(() => adaptBanner({ ...source, actionType: 'url' }), /跳转类型/)
  assert.throws(() => adaptBanner({ ...source, articleId: '' }), /文章 ID/)
})

test('adapts a public list and keeps the no-action variant inert', () => {
  assert.deepEqual(adaptBannerList({ items: [{ ...source, actionType: 'none', articleId: null }] }), [{
    bannerId: '12',
    title: '秋季健康活动',
    imageUrl: 'https://example.com/banner.webp',
    actionType: 'none',
    articleId: '',
    sortOrder: 3
  }])
  assert.throws(() => adaptBannerList({}), /轮播图列表/)
})
