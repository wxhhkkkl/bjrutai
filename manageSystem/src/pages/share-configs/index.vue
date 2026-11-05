<template>
  <div class="share-configs-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">小程序分享配置</h2>
        <p class="page-subtitle">统一管理有独立分享场景的页面，每个页面仅保留一份配置。</p>
      </div>
      <el-button :loading="loading" @click="loadConfigs">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <section v-loading="loading" class="list-panel">
      <div class="panel-heading">
        <div>
          <h3>分享页面</h3>
          <span>应用当前配置后，小程序新发起的分享将使用更新内容</span>
        </div>
        <el-button v-if="canWrite" type="primary" @click="openSourcePicker">
          <el-icon><Plus /></el-icon>添加分享配置
        </el-button>
      </div>
      <el-table :data="items" row-key="pageKey" class="share-table" empty-text="暂无配置">
        <el-table-column label="页面" min-width="190">
          <template #default="{ row }">
            <div class="page-cell">
              <div><strong>{{ row.pageName }}</strong><small>{{ row.sourcePath }}</small></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分享渠道" width="190">
          <template #default="{ row }">
            <div class="channel-tags">
              <el-tag size="small" effect="plain" round>好友</el-tag>
              <el-tag v-if="row.channels.includes('timeline')" size="small" type="success" effect="plain" round>朋友圈</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="好友卡片" min-width="250">
          <template #default="{ row }">
            <div class="mini-preview">
              <el-image :src="previewImage(row.friendImageUrl)" fit="cover" class="mini-preview-image" />
              <span>{{ row.friendTitle }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="好友落地页面" min-width="220">
          <template #default="{ row }"><code>{{ row.landingPath }}</code></template>
        </el-table-column>
        <el-table-column label="最近更新" width="170">
          <template #default="{ row }">{{ formatDate(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button v-if="canWrite" text type="primary" :disabled="Boolean(deletingKey)" @click="openEditor(row)">编辑配置</el-button>
              <el-button v-if="canWrite" text type="danger" :loading="deletingKey === row.pageKey" :disabled="Boolean(deletingKey)" @click="deleteConfig(row)">删除配置</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="panel-footer">
        <el-icon><Lock /></el-icon>
        <span>每个页面仅允许一条配置；删除后小程序将使用内置默认分享内容。</span>
      </div>
    </section>

    <el-drawer v-model="drawerVisible" :size="drawerSize" :with-header="false" destroy-on-close>
      <div v-if="editing" class="editor-drawer">
        <header class="drawer-header">
          <div>
            <el-button text class="back-button" @click="drawerVisible = false"><el-icon><ArrowLeft /></el-icon>返回列表</el-button>
            <h2>{{ editorTitle }}</h2>
            <p>为所选页面设置分享标题和卡片图片；分享链接会跟随该页面的业务入口。</p>
          </div>
        </header>

        <div v-loading="saving" class="editor-body">
          <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="share-form">
            <section class="form-section">
              <div class="section-title"><span>01</span><div><h3>分享页面</h3><p>{{ creating ? '选择要设置分享的页面' : '当前分享配置对应的页面' }}</p></div></div>
              <el-form-item label="小程序页面" required>
                <el-select
                  v-if="creating"
                  v-model="selectedSourceKey"
                  class="full-width"
                  filterable
                  placeholder="请选择要配置分享的页面"
                  @change="onSourceSelect"
                >
                  <el-option
                    v-for="source in sources"
                    :key="source.pageKey"
                    :label="`${source.pageName}  ·  ${source.sourcePath}`"
                    :value="source.pageKey"
                  />
                </el-select>
                <el-input v-else :model-value="`${editing.pageName}  ·  ${editing.sourcePath}`" readonly>
                  <template #suffix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>
            </section>

            <section v-if="creating || editing.pageKey" class="form-section">
              <div class="section-title"><span>02</span><div><h3>好友分享卡片</h3><p>必选配置 · 用户发送给好友时展示</p></div></div>
              <el-form-item label="分享标题" prop="friendTitle">
                <el-input v-model="form.friendTitle" maxlength="100" show-word-limit placeholder="输入好友分享标题" />
              </el-form-item>
              <el-form-item label="卡片图片" prop="friendImageUrl">
                <div class="image-row">
                  <div class="image-picker">
                    <el-image
                      v-if="form.friendImageUrl"
                      :src="previewImage(form.friendImageUrl)"
                      :preview-src-list="[previewImage(form.friendImageUrl)]"
                      fit="contain"
                      preview-teleported
                      class="uploaded-image-thumb"
                    />
                    <el-upload :show-file-list="false" accept="image/jpeg,image/png,image/webp" :before-upload="validateImage" :http-request="(options) => uploadImage(options, 'friendImageUrl')">
                      <div class="upload-tile"><el-icon><Plus /></el-icon><span>{{ form.friendImageUrl ? '更换图片' : '上传图片' }}</span></div>
                    </el-upload>
                  </div>
                  <el-input v-model="form.friendImageUrl" readonly class="image-url-input" placeholder="上传后自动生成图片地址" />
                </div>
                <p class="field-hint">点击缩略图可放大预览。支持 JPG/PNG/WebP，最大 10 MB。</p>
              </el-form-item>
            </section>

            <section v-if="editing.pageKey === 'home' || (creating && !editing.pageKey)" class="form-section">
              <div class="section-title"><span>03</span><div><h3>朋友圈分享卡片</h3><p>必选配置 · 用户分享到朋友圈时展示</p></div></div>
              <el-form-item label="分享标题" prop="timelineTitle">
                <el-input v-model="form.timelineTitle" maxlength="100" show-word-limit placeholder="输入朋友圈分享标题" />
              </el-form-item>
              <el-form-item label="卡片图片" prop="timelineImageUrl">
                <div class="image-row">
                  <div class="image-picker">
                    <el-image
                      v-if="form.timelineImageUrl"
                      :src="previewImage(form.timelineImageUrl)"
                      :preview-src-list="[previewImage(form.timelineImageUrl)]"
                      fit="contain"
                      preview-teleported
                      class="uploaded-image-thumb"
                    />
                    <el-upload :show-file-list="false" accept="image/jpeg,image/png,image/webp" :before-upload="validateImage" :http-request="(options) => uploadImage(options, 'timelineImageUrl')">
                      <div class="upload-tile"><el-icon><Plus /></el-icon><span>{{ form.timelineImageUrl ? '更换图片' : '上传图片' }}</span></div>
                    </el-upload>
                  </div>
                  <el-input v-model="form.timelineImageUrl" readonly class="image-url-input" placeholder="上传后自动生成图片地址" />
                </div>
                <p class="field-hint">点击缩略图可放大预览。朋友圈使用当前页面路径，标题和图片使用此处配置。</p>
              </el-form-item>
            </section>

            <section v-if="creating || editing.pageKey" class="preview-section">
              <div class="section-title"><span>预览</span><div><h3>分享卡片预览</h3><p>实时查看标题和图片效果</p></div></div>
              <el-tabs v-model="previewChannel" class="preview-tabs">
                <el-tab-pane label="发送给好友" name="friend">
                  <div class="wechat-card-preview">
                    <div class="preview-author"><span class="brand-avatar">儒</span><strong>北京儒泰</strong></div>
                    <div class="friend-card">
                      <strong>{{ form.friendTitle || '分享标题将在此显示' }}</strong>
                      <div class="friend-card-image" :class="{ empty: !form.friendImageUrl }">
                        <img v-if="form.friendImageUrl" :src="previewImage(form.friendImageUrl)" alt="好友分享卡片图片">
                        <span v-else>分享图片预览</span>
                      </div>
                      <div class="friend-card-footer"><el-icon><Grid /></el-icon>儒泰医联小程序</div>
                    </div>
                  </div>
                </el-tab-pane>
                <el-tab-pane v-if="editing.pageKey === 'home' || (creating && !editing.pageKey)" label="分享到朋友圈" name="timeline">
                  <div class="timeline-preview">
                    <div class="timeline-author"><span class="brand-avatar">儒</span><strong>儒泰医联</strong></div>
                    <div class="timeline-card">
                      <div class="timeline-copy">{{ form.timelineTitle || '分享标题将在此显示' }}</div>
                      <img v-if="form.timelineImageUrl" :src="previewImage(form.timelineImageUrl)" alt="朋友圈卡片图片">
                      <div v-else class="timeline-placeholder">分享图片预览</div>
                    </div>
                  </div>
                </el-tab-pane>
              </el-tabs>
            </section>
          </el-form>
        </div>

        <footer class="drawer-footer">
          <span><el-icon><CircleCheckFilled /></el-icon>当前配置会用于下一次发起分享</span>
          <div><el-button @click="drawerVisible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="creating && !editing.pageKey" @click="saveConfig">{{ creating ? '添加配置' : '保存配置' }}</el-button></div>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, CircleCheckFilled, Grid, Lock, Plus, Refresh } from '@element-plus/icons-vue'
import http from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import miniProgramConfig from '../../../../miniProgram/app.json'
import homeFriendAsset from '../../../../miniProgram/assets/images/home-share-friend-v1.jpg'
import homeTimelineAsset from '../../../../miniProgram/assets/images/home-share-timeline-v1.jpg'
import promotionFriendAsset from '../../../../miniProgram/assets/images/promotion-share-friend-v1.jpg'

const loading = ref(false)
const saving = ref(false)
const deletingKey = ref('')
const authStore = useAuthStore()
const items = ref([])
const sources = ref([])
const editing = ref(null)
const drawerVisible = ref(false)
const selectedSourceKey = ref('')
const creating = ref(false)
const formRef = ref()
const previewChannel = ref('friend')
const form = reactive(blankForm())
const drawerSize = computed(() => window.innerWidth < 760 ? '100%' : '660px')
const canWrite = computed(() => authStore.hasPermission('mini_program_shares.write'))
const editorTitle = computed(() => {
  if (!editing.value) return ''
  if (creating.value) return editing.value.pageKey ? `添加${editing.value.pageName}分享` : '添加分享配置'
  return `配置${editing.value.pageName}分享`
})

const localImageAssets = {
  '/assets/images/home-share-friend-v1.jpg': homeFriendAsset,
  '/assets/images/home-share-timeline-v1.jpg': homeTimelineAsset,
  '/assets/images/promotion-share-friend-v1.jpg': promotionFriendAsset,
}

const pageNames = {
  'pages/home/index': '首页',
  'pages/customers/index': '客户',
  'pages/internet-hospital/index': '互联网医院',
  'pages/mall/index': '商城',
  'pages/customer-detail/index': '客户详情',
  'pages/customer-edit/index': '编辑客户',
  'pages/followup-record/index': '跟进记录',
  'pages/customer-analysis/index': '客户分析',
  'pages/contribution/index': '消费记录',
  'pages/contribution-detail/index': '消费详情',
  'pages/articles/index': '文章列表',
  'pages/article-detail/index': '文章详情',
  'pages/profile/index': '我的',
  'pages/account-profile/index': '账户信息',
  'pages/help-feedback/index': '帮助与反馈',
  'pages/notifications/index': '消息通知',
  'pages/privacy-authorization/index': '隐私授权',
  'pages/legal-document/index': '法律文档',
  'pages/promotion-code/index': '客户绑定码',
  'pages/patient-binding/index': '客户绑定',
  'pages/staff-invite/index': '员工邀请',
  'pages/staff-join/index': '加入组织',
  'pages/customer-binding/index': '客户绑定结果',
  'pages/binding-records/index': '绑定记录',
  'pages/binding-result/index': '绑定结果',
  'pages/auth/login/index': '登录',
  'pages/auth/profile-setup/index': '完善资料',
  'pages/auth/bind-wechat/index': '绑定微信',
  'pages/org-performance/index': '组织业绩',
  'pages/performance/index': '个人业绩',
  'pages/common/feature-placeholder/index': '功能占位页',
  'pages/index/index': '入口页',
}

const excludedShareSources = new Set([
  'pages/help-feedback/index',
  'pages/notifications/index',
  'pages/privacy-authorization/index',
  'pages/legal-document/index',
  'pages/patient-binding/index',
  'pages/staff-invite/index',
  'pages/staff-join/index',
  'pages/customer-binding/index',
  'pages/account-profile/index',
  'pages/binding-records/index',
  'pages/binding-result/index',
  'pages/auth/login/index',
  'pages/auth/profile-setup/index',
  'pages/auth/bind-wechat/index',
  'pages/org-performance/index',
])

function pageKeyForPath(path) {
  if (path === 'pages/home/index') return 'home'
  if (path === 'pages/promotion-code/index') return 'promotion-code'
  return path.replace(/\//g, '_')
}

function fallbackSources(items) {
  const configured = new Set(items.map((item) => item.pageKey))
  return miniProgramConfig.pages
    .filter((path) => !excludedShareSources.has(path) && !configured.has(pageKeyForPath(path)))
    .map((path) => ({
      pageKey: pageKeyForPath(path),
      pageName: pageNames[path] || path,
      sourcePath: path,
    }))
}

const rules = {
  friendTitle: [{ required: true, message: '请填写好友分享标题', trigger: 'blur' }],
  friendImageUrl: [{ required: true, message: '请上传或填写好友卡片图片', trigger: 'blur' }],
  timelineTitle: [{ validator: (_rule, value, callback) => {
    if (editing.value?.pageKey === 'home' && !String(value || '').trim()) callback(new Error('请填写朋友圈分享标题'))
    else callback()
  }, trigger: 'blur' }],
  timelineImageUrl: [{ validator: (_rule, value, callback) => {
    if (editing.value?.pageKey === 'home' && !String(value || '').trim()) callback(new Error('请上传或填写朋友圈卡片图片'))
    else callback()
  }, trigger: 'blur' }],
}

function blankForm() {
  return { friendTitle: '', friendImageUrl: '', timelineTitle: '', timelineImageUrl: '', landingPath: '', version: 1 }
}

function payload(response) {
  return response.data?.data || response.data || {}
}

function formatDate(value) {
  if (!value) return '尚未修改'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '尚未修改' : date.toLocaleString('zh-CN', { hour12: false })
}

function previewImage(value) {
  return localImageAssets[value] || value
}

async function loadConfigs() {
  loading.value = true
  try {
    const data = payload(await http.get('/admin/share-configs'))
    items.value = data.items || []
    sources.value = Array.isArray(data.sources) && data.sources.length > 0
      ? data.sources
      : fallbackSources(items.value)
  } catch (error) {
    sources.value = fallbackSources(items.value)
    ElMessage.error(error.userMessage || '获取分享配置失败')
  } finally {
    loading.value = false
  }
}

function openSourcePicker() {
  if (sources.value.length === 0) {
    ElMessage.info('当前小程序已注册页面均已配置分享')
    return
  }
  selectedSourceKey.value = ''
  editing.value = { pageKey: '', pageName: '分享配置' }
  creating.value = true
  Object.assign(form, blankForm())
  previewChannel.value = 'friend'
  drawerVisible.value = true
}

function onSourceSelect(pageKey) {
  const source = sources.value.find((item) => item.pageKey === pageKey)
  if (!source) return
  const page = {
    pageKey: source.pageKey,
    pageName: source.pageName,
    sourcePath: source.sourcePath,
    landingPath: source.pageKey === 'promotion-code'
      ? '/pages/patient-binding/index?refToken={refToken}'
      : source.sourcePath,
    version: 1,
    channels: ['friend'],
  }
  Object.assign(editing.value, page)
  Object.assign(form, blankForm(), page)
  previewChannel.value = 'friend'
  formRef.value?.clearValidate()
}

function openEditor(row, isCreating = false) {
  const config = {
    ...row,
    landingPath: row.pageKey === 'promotion-code'
      ? '/pages/patient-binding/index?refToken={refToken}'
      : row.sourcePath || row.landingPath,
  }
  editing.value = config
  creating.value = isCreating
  Object.assign(form, blankForm(), config)
  previewChannel.value = 'friend'
  drawerVisible.value = true
}

async function deleteConfig(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除“${row.pageName}”的后台分享配置？删除后，小程序将使用内置默认分享内容。`,
      '删除分享配置',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  deletingKey.value = row.pageKey
  try {
    await http.delete(`/admin/share-configs/${encodeURIComponent(row.pageKey)}`, {
      params: { version: row.version },
    })
    ElMessage.success('分享配置已删除')
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error.userMessage || '删除分享配置失败')
  } finally {
    deletingKey.value = ''
  }
}

function validateImage(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)
  if (!allowed) {
    ElMessage.error('图片格式仅支持 JPG、PNG 或 WebP')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10 MB')
    return false
  }
  return true
}

async function uploadImage(options, field) {
  const body = new FormData()
  body.append('file', options.file)
  try {
    const data = payload(await http.post('/admin/share-configs/upload-image-file', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }))
    form[field] = data.fileUrl
    options.onSuccess?.(data)
    ElMessage.success('图片上传成功')
  } catch (error) {
    options.onError?.(error)
    ElMessage.error(error.userMessage || '图片上传失败')
  }
}

async function saveConfig() {
  if (!formRef.value || !editing.value) return
  if (creating.value && !editing.value.pageKey) {
    ElMessage.warning('请先选择分享来源页面')
    return
  }
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const body = {
      friendTitle: form.friendTitle,
      friendImageUrl: form.friendImageUrl,
      landingPath: form.landingPath,
      timelineTitle: editing.value.pageKey === 'home' ? form.timelineTitle : null,
      timelineImageUrl: editing.value.pageKey === 'home' ? form.timelineImageUrl : null,
      version: form.version,
    }
    if (creating.value) {
      await http.post('/admin/share-configs', { pageKey: editing.value.pageKey, ...body })
    } else {
      await http.put(`/admin/share-configs/${encodeURIComponent(editing.value.pageKey)}`, body)
    }
    ElMessage.success(creating.value ? '分享配置已添加' : '分享配置已保存')
    drawerVisible.value = false
    creating.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error.userMessage || '保存分享配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.share-configs-page { padding: 0; color: #1f2937; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
.page-title { margin: 0; font-size: 22px; line-height: 1.35; color: #18202c; }
.page-subtitle { margin: 8px 0 0; color: #7a8493; font-size: 13px; }
.list-panel { overflow: hidden; border: 1px solid #e7ebf1; border-radius: 12px; background: #fff; box-shadow: 0 3px 12px rgba(31, 45, 61, .04); }
.panel-heading { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; border-bottom: 1px solid #edf0f4; }
.panel-heading h3 { margin: 0; font-size: 16px; }
.panel-heading span:not(.el-tag) { display: block; margin-top: 5px; color: #8993a2; font-size: 12px; }
.share-table { width: 100%; }
.row-actions { display: flex; align-items: center; justify-content: center; gap: 8px; white-space: nowrap; }
.row-actions .el-button + .el-button { margin-left: 0; }
.page-cell { display: flex; align-items: center; }
.page-cell strong { display: block; font-size: 13px; color: #293241; }
.page-cell small { display: block; margin-top: 4px; color: #9aa3b2; font-size: 11px; }
.channel-tags { display: flex; gap: 6px; }
.mini-preview { display: flex; align-items: center; gap: 10px; min-width: 0; }
.mini-preview-image { width: 70px; height: 56px; flex: 0 0 70px; border-radius: 5px; background: #f1f4f8; }
.mini-preview span { overflow: hidden; max-width: 220px; color: #4c5665; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
code { display: inline-block; padding: 4px 7px; border-radius: 5px; background: #f5f7fa; color: #627083; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; overflow-wrap: anywhere; }
.panel-footer { display: flex; align-items: center; gap: 7px; padding: 12px 20px; color: #8a94a3; background: #fafbfd; border-top: 1px solid #eef1f5; font-size: 12px; }
.editor-drawer { display: flex; flex-direction: column; height: 100%; margin: -20px; }
.drawer-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 22px 26px 18px; border-bottom: 1px solid #edf0f4; }
.back-button { margin-left: -9px; color: #738095; }
.drawer-header h2 { margin: 8px 0 5px; font-size: 20px; color: #1e2938; }
.drawer-header p { margin: 0; color: #8590a0; font-size: 12px; }
.editor-body { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 26px 24px; background: #f8fafd; }
.share-form { display: flex; flex-direction: column; gap: 15px; }
.form-section, .preview-section { padding: 18px 18px 8px; border: 1px solid #e8edf4; border-radius: 10px; background: #fff; }
.section-title { display: flex; align-items: flex-start; gap: 11px; margin-bottom: 17px; }
.section-title > span { display: grid; place-items: center; min-width: 29px; height: 27px; padding: 0 6px; border-radius: 7px; background: #edf4ff; color: #3678dc; font-size: 11px; font-weight: 700; }
.section-title h3 { margin: 1px 0 4px; font-size: 14px; }
.section-title p { margin: 0; color: #929ba8; font-size: 11px; }
.full-width { width: 100%; }
.path-hint { display: flex; align-items: center; gap: 5px; margin-top: 7px; color: #7e8da2; font-size: 11px; }
.path-hint .el-icon { color: #22a76a; }
.image-row { display: flex; align-items: center; gap: 12px; width: 100%; }
.image-picker { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.uploaded-image-thumb { width: 88px; height: 70px; border: 1px solid #e3e9f1; border-radius: 8px; background: #f7f9fc; cursor: zoom-in; }
.upload-tile { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 96px; height: 70px; border: 1px dashed #bfd0e5; border-radius: 8px; background: #f7faff; color: #5884c0; font-size: 11px; gap: 5px; }
.upload-tile .el-icon { font-size: 17px; }
.image-url-input { flex: 1; min-width: 0; }
.field-hint { margin: 6px 0 0; color: #9aa3b2; font-size: 11px; }
.preview-section { padding-bottom: 16px; }
.preview-tabs { margin-top: -5px; }
.wechat-card-preview { width: min(100%, 360px); margin: 7px auto 0; padding: 14px; border: 1px solid #edf0f4; border-radius: 9px; background: #f7f8fa; }
.preview-author, .timeline-author { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; color: #475467; font-size: 12px; }
.brand-avatar { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; background: #e7f1ec; color: #14594b; font-weight: 700; }
.friend-card { padding: 10px; border: 1px solid #e8ebef; border-radius: 7px; background: #fff; }
.friend-card > strong { display: block; min-height: 34px; margin-bottom: 8px; color: #253041; font-size: 12px; line-height: 1.45; }
.friend-card-image { width: 100%; aspect-ratio: 5 / 4; overflow: hidden; border-radius: 5px; background: #eef1f4; }
.friend-card-image img { width: 100%; height: 100%; object-fit: cover; }
.friend-card-image.empty, .timeline-placeholder { display: grid; place-items: center; color: #9aa3b2; font-size: 12px; }
.friend-card-footer { display: flex; align-items: center; gap: 5px; margin-top: 9px; color: #a2a9b3; font-size: 10px; }
.timeline-preview { width: min(100%, 360px); margin: 8px auto 0; padding: 15px; border: 1px solid #edf0f4; border-radius: 8px; background: #fff; }
.timeline-author { margin-bottom: 12px; }
.timeline-copy { margin-bottom: 8px; color: #344054; font-size: 12px; line-height: 1.5; }
.timeline-card { display: flex; gap: 10px; align-items: center; min-height: 88px; padding: 8px; border: 1px solid #f0f1f2; border-radius: 5px; background: #fafafa; }
.timeline-card img, .timeline-placeholder { width: 84px; height: 84px; flex: 0 0 84px; border-radius: 4px; object-fit: cover; background: #f0f2f4; }
.timeline-copy { flex: 1; }
.drawer-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 26px; border-top: 1px solid #e9edf2; background: #fff; }
.drawer-footer > span { display: flex; align-items: center; gap: 6px; color: #8792a1; font-size: 11px; }
.drawer-footer > span .el-icon { color: #25a96b; }
@media (max-width: 760px) {
  .page-header { align-items: flex-start; }
  .panel-heading { padding: 15px; }
  .drawer-header, .editor-body, .drawer-footer { padding-left: 18px; padding-right: 18px; }
  .drawer-footer { align-items: flex-start; flex-direction: column; }
}
</style>
