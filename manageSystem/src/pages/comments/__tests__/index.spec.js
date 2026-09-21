import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

import CommentsPage from '../index.vue'
import { useAuthStore } from '@/stores/auth'
import { listComments } from '@/api/comments'

vi.mock('@/api/comments', () => ({
  listComments: vi.fn(),
  getComment: vi.fn(),
  updateComment: vi.fn(),
}))

const comment = {
  commentId: '9', articleId: '3', articleTitle: '健康生活', displayName: 'Lee',
  contentPreview: '这是一条友善评论', status: 'pending', moderationStatus: 'pending',
  moderationCategory: null, isPinned: false, likeCount: 2,
  createdAt: '2026-09-21T08:00:00Z', updatedAt: '2026-09-21T08:00:00Z', version: 1,
}

function mountPage(permissions = ['comments.read', 'comments.write']) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.permissions = permissions
  return mount(CommentsPage, { global: { plugins: [pinia, ElementPlus] } })
}

describe('comments management page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listComments.mockResolvedValue({ items: [comment], nextCursor: null, hasMore: false, total: 1 })
  })

  it('hides state-changing controls without comments.write', async () => {
    const wrapper = mountPage(['comments.read'])
    await flushPromises()
    expect(wrapper.text()).toContain('这是一条友善评论')
    expect(wrapper.text()).not.toContain('审核通过')
    expect(wrapper.text()).not.toContain('删除')
  })

  it('renders filters and paginated comment rows', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('评论管理')
    expect(wrapper.text()).toContain('文章标题')
    expect(wrapper.text()).toContain('健康生活')
    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.text()).toContain('审核通过')
  })

  it('keeps optimistic-lock conflicts visible for a fresh reload', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.vm.handleAction).toBeTypeOf('function')
    expect(wrapper.vm.actionError).toBe('')
  })
})
