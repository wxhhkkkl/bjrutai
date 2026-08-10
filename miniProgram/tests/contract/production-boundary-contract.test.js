const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '../..')

test('production pages/services do not import Demo fixtures or expose fixed business identities', () => {
  const files = []
  function walk(dir) { for (const entry of fs.readdirSync(dir, { withFileTypes: true })) { const full = path.join(dir, entry.name); if (entry.isDirectory()) walk(full); else if (/\.(js|wxml)$/.test(entry.name)) files.push(full) } }
  walk(path.join(root, 'pages')); walk(path.join(root, 'services'))
  const prohibited = /mock\/(?:foundation-fixtures|demo-control)|张小明|demo-collaborator|12,680|138\*\*\*1028/
  const offenders = files.filter((file) => prohibited.test(fs.readFileSync(file, 'utf8')))
  assert.deepEqual(offenders, [])
})
