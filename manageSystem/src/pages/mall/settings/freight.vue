<template>
  <section
    class="mall-page mall-management-page freight-page"
    v-loading="loading"
  >
    <header class="freight-heading page-header">
      <div>
        <h2 class="page-title">运费设置</h2>
      </div>
      <div class="freight-actions">
        <el-button
          v-if="canWrite"
          type="primary"
          :disabled="locked || rows.length >= 101"
          @click="openTemplate()"
          >新增运费模板</el-button
        >
      </div>
    </header>
    <el-table :data="rows" row-key="id" empty-text="暂无运费模板">
      <el-table-column prop="name" label="模板名称" min-width="180" />
      <el-table-column label="运费方式" min-width="140">
        <template #default="{ row }">
          <el-tag
            :type="row.freightMode === 'free' ? 'success' : 'info'"
            effect="light"
          >
            {{ row.freightMode === 'free' ? '包邮' : '固定运费' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="运费（元）" min-width="130" align="right">
        <template #default="{ row }">
          {{ money(row.freightMode === 'free' ? 0 : row.freightCent) }}
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            :disabled="locked"
            @click="openTemplate(row)"
            >编辑</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="opened"
      class="mall-management-overlay"
      :title="dialogTitle"
      width="min(520px, 92vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!command.pending.value"
      :show-close="!command.pending.value"
    >
      <el-form label-position="top" :disabled="locked" @submit.prevent="save">
        <template v-if="draft">
          <el-form-item label="模板名称" required>
            <el-input
              v-model="draft.name"
              maxlength="64"
              :disabled="draft.id === 'default'"
            />
          </el-form-item>
          <el-form-item label="运费方式">
            <el-radio-group v-model="draft.freightMode">
              <el-radio value="free">包邮</el-radio>
              <el-radio value="fixed">固定运费</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item
            v-if="draft.freightMode === 'fixed'"
            label="固定运费（元）"
            required
          >
            <el-input v-model="draft.amount" inputmode="decimal" />
          </el-form-item>
        </template>
        <el-form-item
          :label="
            draft?.id === 'default'
              ? '默认运费模板不配送地区编码'
              : '不配送地区编码'
          "
        >
          <el-input
            v-model="regions"
            type="textarea"
            :rows="3"
            placeholder="6位区县代码，用逗号或空格分隔"
          />
        </el-form-item>
        <div
          v-if="!command.pending.value"
          class="freight-actions dialog-actions"
        >
          <el-button @click="opened = false">取消</el-button>
          <el-button type="primary" native-type="submit">保存</el-button>
        </div>
      </el-form>
      <div v-if="command.pending.value" class="freight-actions dialog-actions">
        <el-button type="primary" :loading="command.busy.value" @click="retry"
          >重试原操作</el-button
        >
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMallSettings, saveMallSettings } from '@/api/mall-settings'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import { useAuthStore } from '@/stores/auth'
import { money, toOptionalCent } from '../product-form'

const auth = useAuthStore()
const command = useMallCommand()
const canWrite = computed(() => auth.hasPermission('mall.settings.write'))
const loading = ref(false)
const settings = ref(null)
const opened = ref(false)
const draft = ref(null)
const regions = ref('')
const error = ref('')
const loadError = ref('')
useMallToast(error)
useMallToast(loadError)
const dialogTitle = ref('')
const locked = computed(
  () =>
    !canWrite.value || loading.value || !settings.value || command.pending.value
)
const rows = computed(() =>
  settings.value
    ? [
        {
          id: 'default',
          name: '默认运费',
          freightMode: settings.value.freightMode,
          freightCent: settings.value.freightCent,
          blockedRegionCodes: settings.value.defaultBlockedRegionCodes || [],
        },
        ...(settings.value.freightTemplates || []),
      ]
    : []
)

async function load() {
  if (loading.value || command.pending.value) return
  loading.value = true
  loadError.value = ''
  try {
    settings.value = await getMallSettings()
  } catch (failure) {
    loadError.value = failure.userMessage || failure.message
  } finally {
    loading.value = false
  }
}

function openDialog(title) {
  dialogTitle.value = title
  error.value = ''
  command.error.value = ''
  opened.value = true
}

function openTemplate(row) {
  if (locked.value || (!row && rows.value.length >= 101)) return
  draft.value = row
    ? { ...row, amount: money(row.freightCent) }
    : {
        id: crypto.randomUUID().replaceAll('-', ''),
        name: '',
        freightMode: 'free',
        amount: '',
      }
  regions.value = (
    row?.id === 'default'
      ? settings.value.defaultBlockedRegionCodes || []
      : row?.blockedRegionCodes || []
  ).join(', ')
  openDialog(row ? '编辑运费模板' : '新增运费模板')
}

function finish(result) {
  if (!result) return
  settings.value = result
  opened.value = false
  ElMessage.success('运费设置已保存')
}

async function retry() {
  finish(await command.retry())
}

async function save() {
  if (locked.value) return
  error.value = ''
  try {
    const { freightTemplates = [], ...current } = settings.value
    const payload = {
      expectedVersion: current.version,
      settings: current,
    }
    const codes = [...new Set(regions.value.split(/[\s,，]+/).filter(Boolean))]
    if (codes.some((code) => !/^\d{6}$/.test(code))) {
      throw new Error('不配送地区须填写6位区县代码')
    }
    if (draft.value) {
      const { id, name: inputName, freightMode, amount } = draft.value
      const name = inputName.trim()
      if (!name) throw new Error('请填写运费模板名称')
      let freightCent = 0
      if (freightMode === 'fixed') {
        try {
          freightCent = toOptionalCent(amount)
        } catch {
          throw new Error('固定运费须为有效的非负金额，最多两位小数')
        }
        if (freightCent === null) throw new Error('请填写固定运费')
      }
      if (id === 'default') {
        Object.assign(current, {
          freightMode,
          freightCent,
          defaultBlockedRegionCodes: codes,
        })
      } else {
        const template = {
          id,
          name,
          freightMode,
          freightCent,
          blockedRegionCodes: codes,
        }
        payload.freightTemplates = freightTemplates.some(
          (item) => item.id === id
        )
          ? freightTemplates.map((item) => (item.id === id ? template : item))
          : [...freightTemplates, template]
      }
    }
    finish(await command.run(saveMallSettings, payload))
  } catch (failure) {
    error.value = failure.message
  }
}

onMounted(load)
</script>

<style scoped>
.freight-heading p,
.readonly-note {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  overflow-wrap: anywhere;
}

.freight-actions {
  display: flex;
  gap: 8px;
}

.freight-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.dialog-actions {
  justify-content: flex-end;
}
</style>
