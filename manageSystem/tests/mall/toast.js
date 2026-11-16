import { ElMessage } from 'element-plus'

// The mall pages surface errors and notices through ElMessage toasts. In
// jsdom those render outside the mounted wrapper, so tests read them back
// through the mock instead of wrapper.text().
export function capturedToasts() {
  return ElMessage.mock.calls.map(([options]) =>
    typeof options === 'string' ? options : options.message
  )
}

export function clearToasts() {
  ElMessage.mockClear()
}
