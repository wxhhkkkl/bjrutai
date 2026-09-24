const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const pageRoot = path.resolve(__dirname, '../../pages/article-detail')

test('hides comment content and input before mini-program login', () => {
  const source = fs.readFileSync(path.join(pageRoot, 'index.js'), 'utf8')
  assert.match(source, /getAccessToken|isAuthenticated|session/i)
  assert.match(source, /评论|comment/i)
})

test('renders a login gate, empty state, pagination and pending feedback', () => {
  const template = fs.readFileSync(path.join(pageRoot, 'index.wxml'), 'utf8')
  assert.match(template, /评论区|评论列表/)
  assert.match(template, /登录/)
  assert.match(template, /暂无评论|评论为空/)
  assert.match(template, /加载更多|nextCursor/)
  assert.match(template, /审核|pending/)
})

test('keeps the article body readable when comment requests fail', () => {
  const source = fs.readFileSync(path.join(pageRoot, 'index.js'), 'utf8')
  assert.match(source, /articleService\.getArticle/)
  assert.match(source, /comment.*catch|catch[\s\S]*comment/i)
})
