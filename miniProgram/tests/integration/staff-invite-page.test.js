const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const pageRoot = path.resolve(__dirname, '../../pages/staff-invite')

test('staff invite page retries a failed QR image and exposes a manual fallback', () => {
  const controller = fs.readFileSync(path.join(pageRoot, 'index.js'), 'utf8')
  const template = fs.readFileSync(path.join(pageRoot, 'index.wxml'), 'utf8')
  const styles = fs.readFileSync(path.join(pageRoot, 'index.wxss'), 'utf8')

  assert.match(controller, /handleQrError\(\)/)
  assert.match(controller, /refreshInvite\(\{ silent: true \}\)/)
  assert.match(template, /binderror="handleQrError"/)
  assert.match(template, /重新生成/)
  assert.match(styles, /\.invite-qr-error/)
})
