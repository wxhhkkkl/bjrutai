import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ update: vi.fn(), create: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('@/stores/articles', () => ({ useArticlesStore: () => ({ updateArticle: mocks.update, createArticle: mocks.create }) }))
vi.mock('@/stores/categories', () => ({ useCategoriesStore: () => ({ categories: [], fetchCategories: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ hasPermission: () => true }) }))
vi.mock('element-plus', () => ({ ElMessage: { warning: mocks.warning, error: mocks.error } }))
import ArticleEditor from '../ArticleEditor.vue'

const slot = { template: '<div><slot /></div>' }
const upload = { name: 'ArticleVideoUpload', props: ['modelValue', 'active', 'enabled'], template: '<div />' }
const form = { props: ['model'], methods: { validate() { return Promise.resolve() }, clearValidate() {} }, template: '<div><slot /></div>' }
const button = { emits: ['click'], props: ['disabled'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' }
const stubs = { ArticleVideoUpload: upload, ArticleEditor: true, ElForm: form, ElFormItem: slot, ElButton: button,
  ElDialog: { props: ['modelValue'], template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>' },
  ElInput: true, ElSelect: true, ElOption: true, ElUpload: slot, ElIcon: slot }
const article = { articleId: '1', title: '文章标题', content: '<p>保留正文</p>', category_id: 1,
  status: 'published', version: 4, video: { videoId: '1', status: 'ready', playbackUrl: 'https://vod.example.cn/old.mp4' } }
function buttonWith(wrapper, label) { return wrapper.findAll('button').find((item) => item.text() === label) }

describe('article video form persistence', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.update.mockResolvedValue({}); mocks.create.mockResolvedValue({}) })

  it('keeps published replacement unsaved until ready, then saves the video and existing body', async () => {
    const wrapper = mount(ArticleEditor, { props: { article, visible: true }, global: { stubs } })
    wrapper.findComponent(upload).vm.$emit('update:modelValue', { videoId: '2', status: 'processing' })
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.update).not.toHaveBeenCalled()
    expect(mocks.warning).toHaveBeenCalled()
    wrapper.findComponent(upload).vm.$emit('update:modelValue', { videoId: '2', status: 'ready' })
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledWith('1', expect.objectContaining({ videoId: '2', content: '<p>保留正文</p>', version: 4 }))
    wrapper.unmount()
  })

  it('saves removal as null and leaves unchanged video out of a text-only save', async () => {
    const wrapper = mount(ArticleEditor, { props: { article, visible: true }, global: { stubs } })
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.update.mock.calls[0][1]).not.toHaveProperty('videoId')
    wrapper.findComponent(upload).vm.$emit('update:modelValue', null)
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.update.mock.calls[1][1].videoId).toBeNull()
    wrapper.unmount()
  })

  it('saves pending video drafts, and reopens the same article with stored video state', async () => {
    const draft = { ...article, status: 'draft' }
    const wrapper = mount(ArticleEditor, { props: { article: draft, visible: true }, global: { stubs } })
    wrapper.findComponent(upload).vm.$emit('update:modelValue', { videoId: '2', status: 'processing' })
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(mocks.update.mock.calls[0][1].videoId).toBe('2')
    await wrapper.setProps({ visible: false })
    await wrapper.setProps({ visible: true })
    expect(wrapper.findComponent(upload).props('modelValue').videoId).toBe('1')
    wrapper.unmount()
  })

  it('previews in a sandbox and preserves edit state after save failure', async () => {
    mocks.update.mockRejectedValue(new Error('conflict'))
    const wrapper = mount(ArticleEditor, { props: { article, visible: true }, global: { stubs } })
    await buttonWith(wrapper, '预览').trigger('click')
    const iframe = wrapper.find('iframe')
    expect(iframe.attributes('sandbox')).toBe('')
    expect(iframe.attributes('srcdoc')).toContain('<video controls')
    await buttonWith(wrapper, '保存修改').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(form).props('model').content).toBe('<p>保留正文</p>')
    expect(wrapper.emitted('saved')).toBeUndefined()
    wrapper.unmount()
  })
})
