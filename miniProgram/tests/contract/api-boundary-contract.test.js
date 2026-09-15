const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

function jsFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) return jsFiles(target)
    return entry.name.endsWith('.js') ? [target] : []
  })
}

test('production API calls use request-service except the presigned COS binary upload', () => {
  const root = path.resolve(__dirname, '../..')
  const files = [
    ...jsFiles(path.join(root, 'pages')),
    ...jsFiles(path.join(root, 'services'))
  ]
  const offenders = files.filter((file) => (
    !file.endsWith(path.join('services', 'request-service.js'))
    && /wx\.request\s*\(/.test(fs.readFileSync(file, 'utf8'))
  ))

  assert.deepEqual(offenders.map((file) => path.relative(root, file)), ['services/cos-upload.js'])
  const cosUpload = fs.readFileSync(path.join(root, 'services/cos-upload.js'), 'utf8')
  assert.match(cosUpload, /url:\s*uploadInfo\.uploadUrl/)
})
