import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ authorize: vi.fn(), read: vi.fn(), upload: vi.fn(), cancel: vi.fn() }))
vi.mock('@/api/article-videos', async (original) => ({
  ...await original(), authorizeVideoUpload: mocks.authorize, readVideoState: mocks.read,
}))
vi.mock('vod-js-sdk-v6', () => ({ default: class { upload() { return mocks.upload() } } }))
import ArticleVideoUpload from '../ArticleVideoUpload.vue'

const button = { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

describe('article video upload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
    URL.createObjectURL = vi.fn(() => 'blob:local-preview')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    if (originalCreateObjectURL) URL.createObjectURL = originalCreateObjectURL
    else delete URL.createObjectURL
    if (originalRevokeObjectURL) URL.revokeObjectURL = originalRevokeObjectURL
    else delete URL.revokeObjectURL
  })

  it('previews the selected file, then switches to confirmed cloud playback', async () => {
    vi.useFakeTimers()
    let finish
    let progress
    mocks.authorize.mockResolvedValue({ videoId: '2', uploadSignature: 'test', status: 'authorized' })
    mocks.upload.mockReturnValue({ on: (name, callback) => { progress = callback },
      done: () => new Promise((resolve) => { finish = resolve }), cancel: mocks.cancel })
    mocks.read.mockResolvedValueOnce({ videoId: '2', fileName: 'new.mp4', status: 'processing' })
      .mockResolvedValueOnce({ videoId: '2', fileName: 'new.mp4', status: 'ready', playbackUrl: 'https://vod.example.cn/new.mp4' })
    let wrapper
    wrapper = mount(ArticleVideoUpload, { props: { modelValue: null, active: true, enabled: true,
      'onUpdate:modelValue': (video) => wrapper.setProps({ modelValue: video }) },
      global: { stubs: { ElButton: button, ElProgress: true, ElAlert: true } } })
    Object.defineProperty(wrapper.find('input').element, 'files', { value: [new File(['data'], 'new.mp4', { type: 'video/mp4' })] })
    await wrapper.find('input').trigger('change')
    await flushPromises()
    expect(wrapper.find('video').attributes('src')).toBe('blob:local-preview')
    progress({ percent: 0.42 })
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('上传中 42%')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    finish({ fileId: 'untrusted-client-id', video: { url: 'https://client.example.cn/source.mov' } })
    await flushPromises()
    expect(wrapper.text()).toContain('视频处理中')
    expect(wrapper.find('video').attributes('src')).toBe('blob:local-preview')
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(wrapper.find('video').attributes('src')).toBe('https://vod.example.cn/new.mp4')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-preview')
    wrapper.unmount()
  })

  it('keeps the saved video while replacement uploads, and cancels on close', async () => {
    const old = { videoId: '1', status: 'ready', fileName: 'old.mp4', playbackUrl: 'https://vod.example.cn/old.mp4' }
    mocks.authorize.mockResolvedValue({ videoId: '2', uploadSignature: 'test', status: 'authorized' })
    mocks.upload.mockReturnValue({ on: vi.fn(), done: () => new Promise(() => {}), cancel: mocks.cancel })
    const wrapper = mount(ArticleVideoUpload, { props: { modelValue: old, active: true, enabled: true },
      global: { stubs: { ElButton: button, ElProgress: true, ElAlert: true } } })
    expect(wrapper.find('video').attributes('src')).toBe(old.playbackUrl)
    Object.defineProperty(wrapper.find('input').element, 'files', { value: [new File(['data'], 'new.mp4', { type: 'video/mp4' })] })
    await wrapper.find('input').trigger('change')
    await flushPromises()
    expect(wrapper.find('video').attributes('src')).toBe('blob:local-preview')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('busy').at(-1)).toEqual([true])
    await wrapper.setProps({ active: false })
    expect(mocks.cancel).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-preview')
    wrapper.unmount()
  })

  it('removes only the form relation until article save', async () => {
    const wrapper = mount(ArticleVideoUpload, { props: { modelValue: { videoId: '1', status: 'ready' }, active: true, enabled: true },
      global: { stubs: { ElButton: button, ElProgress: true, ElAlert: true } } })
    await wrapper.findAll('button').find((element) => element.text() === '移除视频').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual([null])
    expect(mocks.authorize).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
