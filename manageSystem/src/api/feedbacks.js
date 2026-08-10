import http from './http'

function body(response) {
  return response.data?.data || response.data
}

export async function listFeedbacks(params = {}) {
  return body(await http.get('/admin/feedbacks', { params }))
}

export async function getFeedback(feedbackNo) {
  return body(await http.get(`/admin/feedbacks/${encodeURIComponent(feedbackNo)}`))
}

export async function updateFeedback(feedbackNo, payload) {
  return body(await http.patch(`/admin/feedbacks/${encodeURIComponent(feedbackNo)}`, payload))
}
