import http from './http'

function body(response) {
  return response.data?.data || response.data
}

export async function listComments(params = {}) {
  return body(await http.get('/admin/comments', { params }))
}

export async function getComment(commentId) {
  return body(await http.get(`/admin/comments/${encodeURIComponent(commentId)}`))
}

export async function updateComment(commentId, payload) {
  return body(await http.patch(`/admin/comments/${encodeURIComponent(commentId)}`, payload))
}
