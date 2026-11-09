<template>
  <el-drawer
    v-model="opened"
    title="商品编辑"
    size="min(800px, 95vw)"
    :before-close="close"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <el-alert
      title="先保存草稿，再从列表上架。上架需有效分类、主图、商品详情或使用说明、正价 SKU 和商城配送售后规则。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="command.error.value"
      :title="command.error.value"
      type="error"
      :closable="false"
    />
    <el-form label-position="top" :disabled="locked">
      <el-form-item label="商品名称（必填）">
        <el-input v-model="form.name" maxlength="64" />
      </el-form-item>
      <el-form-item label="分类">
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
        <el-input-number v-model="form.sort" :precision="0" />
      </el-form-item>
      <el-image
        v-if="form.coverFileId && previews[form.coverFileId]"
        :src="previews[form.coverFileId]"
        fit="contain"
        style="width: 120px; height: 120px"
      />
      <ImageUpload
        :key="`cover-${generation}`"
        label="商品主图"
        :value="form.coverFileId || ''"
        :disabled="locked"
        @uploaded="setCover"
        @busy="imageBusy = $event"
      />
      <el-button
        v-if="form.coverFileId"
        :disabled="locked"
        @click="form.coverFileId = null"
      >
        移除主图
      </el-button>
      <ImageUpload
        v-if="form.galleryFileIds.length < 8"
        :key="`gallery-${generation}`"
        label="追加详情图片（最多 8 张）"
        :disabled="locked"
        @uploaded="addGallery"
        @busy="imageBusy = $event"
      />
      <div v-for="(id, index) in form.galleryFileIds" :key="`${id}-${index}`">
        <el-image
          v-if="previews[id]"
          :src="previews[id]"
          fit="contain"
          style="width: 80px; height: 80px"
        />
        详情图片 {{ index + 1 }}（已核验）<el-button
          link
          :disabled="locked"
          @click="form.galleryFileIds.splice(index, 1)"
        >
          移除
        </el-button>
      </div>
      <el-form-item label="商品说明">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="5"
          maxlength="100000"
        />
      </el-form-item>
      <el-form-item label="使用说明">
        <el-input
          v-model="form.instructions"
          type="textarea"
          :rows="4"
          maxlength="10000"
        />
      </el-form-item>
      <SkuEditor v-model:skus="form.skus" :disabled="locked" />
    </el-form>
    <template #footer>
      <el-button :disabled="locked" @click="opened = false">取消</el-button>
      <el-button
        v-if="command.pending.value"
        :loading="command.busy.value"
        @click="retry"
      >
        重试原操作
      </el-button>
      <el-button v-else type="primary" :disabled="imageBusy" @click="save">
        保存草稿 / 修改
      </el-button>
    </template>
  </el-drawer>
</template>
<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { saveProduct } from '@/api/mall-catalog'
import { useMallCommand } from '@/composables/useMallCommand'
import { productForm, productPayload } from '../product-form'
import SkuEditor from './SkuEditor.vue'
import ImageUpload from './ImageUpload.vue'
defineProps({ categories: { type: Array, default: () => [] } })
const emit = defineEmits(['saved'])
const auth = useAuthStore(),
  command = useMallCommand()
const opened = ref(false),
  imageBusy = ref(false),
  form = ref(productForm())
const generation = ref(0),
  previews = ref({}),
  blobs = []
const locked = computed(
  () =>
    command.pending.value ||
    imageBusy.value ||
    !auth.hasPermission('mall.products.write')
)
function open(product) {
  if (locked.value) return
  clearBlobs()
  previews.value = {}
  generation.value++
  form.value = productForm(product)
  command.error.value = ''
  opened.value = true
  if (product?.coverFileId && product.coverUrl)
    previews.value[product.coverFileId] = product.coverUrl
  product?.galleryFileIds?.forEach((id, i) => {
    if (product.galleryUrls?.[i]) previews.value[id] = product.galleryUrls[i]
  })
}
function close(done) {
  if (!locked.value) done()
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
defineExpose({ open })
onBeforeUnmount(clearBlobs)
</script>
