<template>
  <el-dialog
    v-model="opened"
    :title="form.id ? '编辑商品' : '新增商品'"
    width="min(1080px, calc(100vw - 24px))"
    top="5vh"
    class="mall-management-overlay product-overlay product-editor-dialog"
    destroy-on-close
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :before-close="close"
    @closed="clearBlobs"
  >
    <section class="product-form-stack" v-loading="loading">
      <el-alert
        title="先保存草稿，再从列表上架。上架需有效分类、主图、商品详情、销售价大于零的商品规格和商城配送售后规则。"
        type="info"
        :closable="false"
      />
      <el-form
        v-if="!loadError"
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        :disabled="locked"
        @submit.prevent
      >
        <el-tabs v-model="tab" class="product-surface editor-tabs">
          <el-tab-pane label="基础设置" name="basic">
            <div class="basic-fields">
              <el-form-item label="商品属性" class="product-attribute">
                <el-radio-group v-model="productType">
                  <el-radio value="physical">实物商品</el-radio>
                  <el-radio value="virtual">虚拟商品</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item prop="name" label="商品名称" required>
                <el-input v-model="form.name" maxlength="64" />
              </el-form-item>
              <el-form-item prop="categoryId" label="分类" required>
                <el-select v-model="form.categoryId" clearable>
                  <el-option
                    v-for="c in categories"
                    :key="c.id"
                    :label="c.label || c.name"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="简述">
                <el-input v-model="form.summary" maxlength="128" />
              </el-form-item>
              <el-form-item label="排序">
                <div class="product-sort-field">
                  <el-input-number v-model="form.sort" :precision="0" />
                  <span class="product-hint">数值越小越靠前</span>
                </div>
              </el-form-item>
              <div class="product-return-row" role="group" aria-label="是否支持退货">
                <span class="product-return-row__label">是否支持退货</span>
                <el-switch v-model="form.supportsReturn" active-text="支持退货" inactive-text="不支持退货" />
              </div>
              <el-form-item label="退货说明" class="product-attribute">
                <el-input
                  v-model="form.returnInstructions"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                  show-word-limit
                  placeholder="选填，留空时使用交易设置中的配送与退货说明"
                />
              </el-form-item>
              <div class="asset-fields">
                <el-form-item
                  prop="coverFileId"
                  label="商品主图"
                  required
                  class="asset-form-item"
                >
                  <div class="asset-content">
                    <div class="cover-upload-wrap">
                      <ImageUpload
                        label="商品主图"
                        meta-below
                        :preview-url="previews[form.coverFileId]"
                        :disabled="locked"
                        @uploaded="setCover"
                        @busy="imageBusy = $event"
                      />
                      <el-button
                        v-if="form.coverFileId"
                        circle
                        plain
                        class="gallery-remove cover-remove"
                        type="danger"
                        aria-label="移除商品主图"
                        :disabled="locked"
                        @click="form.coverFileId = null"
                      >
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </el-form-item>
                <el-form-item label="商品轮播图">
                  <div class="asset-content">
                    <div class="gallery-list">
                      <div
                        v-for="(id, index) in form.galleryFileIds"
                        :key="`${id}-${index}`"
                        class="gallery-item"
                      >
                        <el-image
                          v-if="previews[id]"
                          :src="previews[id]"
                          fit="cover"
                          class="gallery-preview"
                        />
                        <el-button
                          circle
                          plain
                          class="gallery-remove"
                          type="danger"
                          :aria-label="`移除第 ${index + 1} 张商品轮播图`"
                          :disabled="locked"
                          @click="form.galleryFileIds.splice(index, 1)"
                        >
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </div>
                      <ImageUpload
                        v-if="form.galleryFileIds.length < 8"
                        label="添加商品轮播图"
                        variant="square"
                        compact
                        :disabled="locked"
                        @uploaded="addGallery"
                        @busy="imageBusy = $event"
                      />
                    </div>
                    <p class="product-hint asset-hint">
                      最多添加 8 张，支持 JPG / PNG，单张不超过 5 MB。
                    </p>
                  </div>
                </el-form-item>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="价格库存" name="stock">
            <SkuEditor v-model:skus="form.skus" :disabled="locked" />
          </el-tab-pane>
          <el-tab-pane label="物流设置" name="delivery">
            <template v-if="form.deliveryMethod !== 'virtual'">
              <el-form-item label="配送方式" required>
                <el-radio-group v-model="form.deliveryMethod">
                  <el-radio value="express">快递发货</el-radio>
                  <el-radio value="pickup">用户自提</el-radio>
                </el-radio-group>
              </el-form-item>
            </template>
            <el-alert
              v-else
              title="虚拟商品不需要收货地址和运费模板，买家付款后由后台人员手工交付。"
              type="info"
              :closable="false"
            />
            <el-form-item
              v-if="form.deliveryMethod === 'express'"
              label="运费模板"
              required
            >
              <el-select
                v-model="form.freightTemplateId"
                placeholder="请选择运费模板"
                style="max-width: 340px"
              >
                <el-option
                  v-for="item in freightOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <p v-if="form.deliveryMethod === 'pickup'" class="product-hint">
              自提商品可保存为草稿，当前商城暂不支持自提履约。
            </p>
          </el-tab-pane>
          <el-tab-pane label="商品详情" name="details">
            <el-form-item label="商品详情">
              <div class="detail-editor">
                <input
                  ref="detailImageInput"
                  class="visually-hidden"
                  type="file"
                  accept="image/jpeg,image/png"
                  :disabled="locked"
                  @change="insertDetailImage"
                />
                <QuillEditor
                  v-if="!loading"
                  @ready="onDetailReady"
                  v-model:content="detailHtml"
                  content-type="html"
                  theme="snow"
                  :toolbar="{
                    container: toolbar,
                    handlers: { image: chooseDetailImage },
                  }"
                  :options="{
                    formats: [
                      'header',
                      'bold',
                      'italic',
                      'underline',
                      'list',
                      'image',
                    ],
                  }"
                  :read-only="locked"
                  @text-change="onDetailChange"
                />
              </div>
            </el-form-item>
            <el-form-item label="使用说明">
              <el-input
                v-model="form.instructions"
                type="textarea"
                :rows="4"
                maxlength="10000"
              />
            </el-form-item>
          </el-tab-pane>
        </el-tabs>
      </el-form>
    </section>
    <template #footer>
      <footer class="product-toolbar product-dialog-footer">
        <el-button :disabled="locked" @click="opened = false">取消</el-button>
        <el-button
          v-if="command.pending.value"
          :loading="command.busy.value"
          @click="retry"
        >
          重试原操作
        </el-button>
        <el-button
          v-else
          type="primary"
          :disabled="
            locked ||
            !!loadError
          "
          @click="save"
        >
          {{ form.id ? '保存修改' : '保存草稿' }}
        </el-button>
      </footer>
    </template>
  </el-dialog>
</template>
<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
import { useAuthStore } from '@/stores/auth'
import {
  getProduct,
  listCategories,
  listFreightTemplateOptions,
  saveProduct,
} from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import { productForm, productPayload } from '../product-form'
import { uploadProductImage } from '@/api/mall-catalog'
import SkuEditor from './SkuEditor.vue'
import ImageUpload from './ImageUpload.vue'
const opened = ref(false)
const categories = ref([])
const freightOptions = ref([])
const tab = ref('basic')
const loading = ref(false)
const loadError = ref('')
useMallToast(loadError)
const formRef = ref(null)
const rules = {
  name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }],
  categoryId: [
    { required: true, message: '请选择商品分类', trigger: 'change' },
  ],
  coverFileId: [
    { required: true, message: '请上传商品主图', trigger: 'change' },
  ],
}
const detailHtml = ref('')
const detailImageInput = ref(null)
let detailEditor
function onDetailReady(editor) {
  detailEditor = editor
}
function chooseDetailImage() {
  detailImageInput.value?.click()
}
async function insertDetailImage(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !detailEditor) return
  const selection = detailEditor.getSelection(true)
  const index = selection ? selection.index : detailEditor.getLength() - 1
  imageBusy.value = true
  command.error.value = ''
  try {
    const uploaded = await uploadProductImage({ file })
    if (!uploaded.previewUrl)
      throw new Error('图片上传成功，但预览地址暂不可用')
    detailEditor.insertEmbed(index, 'image', uploaded.previewUrl, 'api')
    detailEditor.formatText(
      index,
      1,
      'alt',
      `mall-file-id:${uploaded.id}`,
      'silent'
    )
    detailEditor.setSelection(index + 1, 0, 'silent')
    detailChanged = true
  } catch (error) {
    command.error.value =
      error.userMessage || error.message || '详情图片上传失败'
  } finally {
    imageBusy.value = false
  }
}
let detailChanged = false
function onDetailChange({ source }) {
  if (source === 'user') detailChanged = true
}
const marker = '<!--mall-rich-text-->'
const toolbar = [
  [{ header: [2, 3, false] }],
  ['bold', 'italic', 'underline'],
  [{ list: 'ordered' }, { list: 'bullet' }],
  ['clean', 'image'],
]
const auth = useAuthStore(),
  command = useMallCommand()
const imageBusy = ref(false),
  form = ref(productForm())
const productType = computed({
  get: () => form.value.productType || 'physical',
  set: (value) => {
    form.value.productType = value
    if (value === 'virtual') {
      form.value.deliveryMethod = 'virtual'
      form.value.freightTemplateId = null
    } else if (form.value.deliveryMethod === 'virtual') {
      form.value.deliveryMethod = 'express'
    }
  },
})
const previews = ref({}),
  blobs = []
const locked = computed(
  () =>
    loading.value ||
    command.pending.value ||
    imageBusy.value ||
    !auth.hasPermission('mall.products.write')
)
function close(done) {
  if (locked.value) return
  done()
}
async function open(productId) {
  if (!auth.hasPermission('mall.products.write') || locked.value) return
  opened.value = true
  loading.value = true
  loadError.value = ''
  command.error.value = ''
  detailChanged = false
  detailEditor = undefined
  tab.value = 'basic'
  previews.value = {}
  clearBlobs()
  form.value = productForm()
  detailHtml.value = ''
  categories.value = []
  try {
    const product = productId ? await getProduct(productId) : undefined
    if (product?.status === 'archived') throw new Error('归档商品不可编辑')
    form.value = productForm(product)
    form.value.deliveryMethod =
      product?.deliveryMethod ||
      (form.value.productType === 'virtual' ? 'virtual' : 'express')
    form.value.freightTemplateId =
      product?.freightTemplateId ||
      (product &&
      !product.deliveryMethod &&
      form.value.productType === 'physical'
        ? 'default'
        : null)
    freightOptions.value = await listFreightTemplateOptions()
    const description = form.value.description
    detailHtml.value = description.startsWith(marker)
      ? description.slice(marker.length)
      : description
          .split(/\r?\n/)
          .map((line) => {
            const node = document.createElement('span')
            node.textContent = line
            return `<p>${node.innerHTML || '<br>'}</p>`
          })
          .join('')
    if (product?.coverFileId && product.coverUrl)
      previews.value[product.coverFileId] = product.coverUrl
    product?.galleryFileIds?.forEach((id, i) => {
      if (product.galleryUrls?.[i]) previews.value[id] = product.galleryUrls[i]
    })
    const rows = []
    let cursor
    do {
      const data = await listCategories({
        pageSize: 100,
        ...(cursor ? { cursor } : {}),
      })
      rows.push(...data.items)
      cursor = data.nextCursor
    } while (cursor)
    categories.value = rows.map((c) => ({
      ...c,
      label: c.name,
    }))
  } catch (e) {
    loadError.value = e.userMessage || e.message
  } finally {
    loading.value = false
  }
}
function preview(id, file) {
  const url = URL.createObjectURL(file)
  blobs.push(url)
  previews.value[id] = url
}
function clearBlobs() {
  blobs.splice(0).forEach((url) => URL.revokeObjectURL(url))
}
function setCover(id, file) {
  form.value.coverFileId = id
  preview(id, file)
}
function addGallery(id, file) {
  if (!form.value.galleryFileIds.includes(id))
    form.value.galleryFileIds.push(id)
  preview(id, file)
}
function finish(result) {
  if (result) {
    opened.value = false
    emit('saved', result)
  }
}
async function save() {
  if (locked.value) return
  try {
    const valid = await formRef.value?.validate().catch(() => false)
    if (!valid) {
      tab.value = 'basic'
      return
    }
    if (
      form.value.deliveryMethod === 'express' &&
      !form.value.freightTemplateId
    ) {
      tab.value = 'delivery'
      throw new Error('请选择运费模板')
    }
    const editor = detailEditor
    if (editor && detailChanged) {
      const hasContent =
        editor.getText().trim() || editor.root.querySelector('img[src]')
      form.value.description = hasContent
        ? marker + (editor.getSemanticHTML?.() ?? detailHtml.value)
        : ''
    }
    if (form.value.description.length > 100000) {
      tab.value = 'details'
      throw new Error('商品详情内容过长，请精简后保存')
    }
    if (!form.value.name.trim()) tab.value = 'basic'
    finish(
      await command.run(saveProduct, {
        id: form.value.id,
        expectedVersion: form.value.version,
        product: productPayload(form.value),
      })
    )
  } catch (e) {
    command.error.value = e.message
  }
}
async function retry() {
  finish(await command.retry())
}
const emit = defineEmits(['saved'])
defineExpose({ open })
onBeforeUnmount(clearBlobs)
</script>

<style scoped>
.editor-tabs {
  padding: 4px 16px 16px;
}
.basic-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}
.basic-fields > .product-attribute {
  grid-column: 1 / -1;
}
.basic-fields > .product-attribute-warning {
  grid-column: 1 / -1;
}
.product-return-row {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 20px;
  min-height: 32px;
}
.product-return-row__label {
  width: 110px;
  flex: none;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 22px;
}
.product-attribute :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}
.basic-fields :deep(.el-select) {
  width: 100%;
}
.detail-editor {
  width: 100%;
  line-height: normal;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}
.detail-editor :deep(.ql-toolbar.ql-snow) {
  border: 0;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}
.detail-editor :deep(.ql-container.ql-snow) {
  border: 0;
}
.visually-hidden {
  display: none;
}
.detail-editor :deep(.ql-editor) {
  min-height: 260px;
}
.detail-editor :deep(.ql-editor img) {
  max-width: 100%;
}
.asset-fields {
  grid-column: 1 / -1;
  min-width: 0;
  padding-top: 16px;
  border-top: 1px solid var(--app-border-color);
}
.asset-fields :deep(.asset-form-item .el-form-item__error) {
  position: static;
  padding-top: 4px;
}
.asset-content {
  width: 100%;
  line-height: 1.5;
}
.cover-upload-wrap {
  position: relative;
  width: var(--product-image-size);
}
.gallery-list {
  display: flex;
  flex-wrap: nowrap;
  align-items: flex-start;
  gap: 12px;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
  scrollbar-width: thin;
}
.gallery-item {
  position: relative;
  flex: 0 0 var(--product-image-size);
  width: var(--product-image-size);
  height: var(--product-image-size);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.gallery-preview {
  display: block;
  width: 100%;
  height: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--app-radius-md);
  background: var(--el-fill-color-lighter);
}
.asset-hint {
  margin: 8px 0 0;
}
.gallery-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 1;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 1px 4px rgb(31 36 45 / 20%);
}
:global(.product-editor-dialog.el-dialog) {
  height: 90vh;
  height: 90dvh;
  padding: 0;
  display: flex;
  flex-direction: column;
}
:global(.product-editor-dialog .el-dialog__body) {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
@media (max-width: 700px) {
  .basic-fields {
    grid-template-columns: minmax(0, 1fr);
  }
  .editor-tabs {
    padding-inline: 12px;
  }
}
</style>
