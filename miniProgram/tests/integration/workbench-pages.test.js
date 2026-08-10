const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../..')

test('home and profile production pages use real workbench service and no Demo fixtures', () => {
  for (const relative of ['pages/home/index.js', 'pages/profile/index.js']) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /workbench-service/)
    assert.doesNotMatch(source, /mock\/demo-control|mock\/foundation-fixtures/)
    assert.match(source, /state:\s*['"]loading['"]/)
    assert.match(source, /recoverable-error/)
  }
})

test('home and profile guard page state against stale asynchronous responses', () => {
  for (const relative of ['pages/home/index.js', 'pages/profile/index.js']) {
    const source = fs.readFileSync(path.join(root, relative), 'utf8')
    assert.match(source, /requestVersion/)
    assert.match(source, /version\s*!==\s*this\.requestVersion/)
  }
})

test('workbench pages expose empty and forbidden state handling', () => {
  const home = fs.readFileSync(path.join(root, 'pages/home/index.js'), 'utf8')
  const profile = fs.readFileSync(path.join(root, 'pages/profile/index.js'), 'utf8')
  assert.match(home, /empty/)
  assert.match(home, /forbidden/)
  assert.match(profile, /empty/)
  assert.match(profile, /forbidden/)
})
