<template>
  <section class="reconciliation-panel">
    <header class="panel-heading">
      <div>
        <h3>日对账与差异处理</h3>
        <p>按北京时间自然日核对渠道账单和本地成功收退款；处理中、未知记录不计入成功金额。</p>
      </div>
      <el-button
        data-test="reload-reconciliations"
        :loading="loading"
        @click="load"
      >
        刷新
      </el-button>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="notice" :title="notice" :type="noticeType" :closable="false" />

    <el-card v-if="canWrite" class="create-batch">
      <template #header>登记渠道日账单</template>
      <el-form label-position="top" class="batch-form">
        <el-form-item label="业务日期（北京时间）">
          <el-date-picker v-model="createForm.businessDate" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="渠道成功收款（元）">
          <el-input v-model="createForm.expectedPaid" type="number" min="0" step="0.01" />
        </el-form-item>
        <el-form-item label="渠道成功退款（元）">
          <el-input v-model="createForm.expectedRefund" type="number" min="0" step="0.01" />
        </el-form-item>
        <el-form-item label="核对说明">
          <el-input
            v-model="createForm.evidenceNote"
            maxlength="1000"
            placeholder="说明账单来源、商户主体或当日核对范围"
          />
        </el-form-item>
        <el-form-item label="已核验渠道账单">
          <label class="file-picker">
            选择 CSV / XLSX / PDF / JPG / PNG（最多 10 MB）
            <input
              data-test="statement-file"
              type="file"
              accept=".csv,.xlsx,application/pdf,image/jpeg,image/png,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              :disabled="!canUploadEvidence || uploadBusy"
              @change="chooseStatementFile"
            >
          </label>
          <span v-if="statementFileId">已核验文件 #{{ statementFileId }}</span>
          <span v-else class="muted">请上传并完成服务端核验后再登记</span>
        </el-form-item>
        <el-button
          data-test="create-reconciliation"
          type="primary"
          :loading="commandBusy"
          :disabled="!canCreateBatch"
          @click="createBatch"
        >
          创建日对账批次
        </el-button>
      </el-form>
    </el-card>

    <el-table
      v-loading="loading"
      :data="batches"
      empty-text="暂无日对账批次"
      class="batch-table"
    >
      <el-table-column prop="businessDate" label="业务日期" width="130" />
      <el-table-column label="渠道账单收 / 退" min-width="180">
        <template #default="{ row }">
          {{ money(row.expectedPaidCent) }} / {{ money(row.expectedRefundCent) }}
        </template>
      </el-table-column>
      <el-table-column label="本地成功收 / 退" min-width="180">
        <template #default="{ row }">
          {{ money(row.localPaidCent) }} / {{ money(row.localRefundCent) }}
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110">
        <template #default="{ row }">
          <el-tag :type="row.openDifferenceCount ? 'warning' : 'success'">
            {{ row.openDifferenceCount ? `${row.openDifferenceCount} 项待处理` : '无未决差异' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="批次状态" width="110">
        <template #default="{ row }">{{ batchStates[row.status] || row.status }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link @click="openBatch(row)">核对差异</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="selectedBatch" class="batch-detail">
      <template #header>
        <div class="batch-title">
          <strong>{{ selectedBatch.businessDate }} 日对账</strong>
          <span>本地与渠道数据按收款、退款分别核对</span>
        </div>
      </template>
      <div class="amount-comparison">
        <div>
          <span>渠道成功收款</span>
          <strong>{{ money(selectedBatch.expectedPaidCent) }}</strong>
        </div>
        <div>
          <span>本地成功收款</span>
          <strong>{{ money(selectedBatch.localPaidCent) }}</strong>
        </div>
        <div>
          <span>渠道成功退款</span>
          <strong>{{ money(selectedBatch.expectedRefundCent) }}</strong>
        </div>
        <div>
          <span>本地成功退款</span>
          <strong>{{ money(selectedBatch.localRefundCent) }}</strong>
        </div>
      </div>

      <el-form v-if="canWrite && selectedBatch.status !== 'closed'" inline class="difference-form">
        <el-form-item label="差异类型">
          <el-select v-model="differenceForm.differenceType" style="width: 190px">
            <el-option
              v-for="(label, value) in differenceTypes"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="订单号（可空）">
          <el-input v-model="differenceForm.orderId" maxlength="20" />
        </el-form-item>
        <el-form-item label="渠道流水号（可空）">
          <el-input v-model="differenceForm.externalReference" maxlength="128" />
        </el-form-item>
        <el-form-item label="渠道金额（元）">
          <el-input v-model="differenceForm.expectedAmount" type="number" min="0" step="0.01" />
        </el-form-item>
        <el-form-item label="本地金额（元）">
          <el-input v-model="differenceForm.actualAmount" type="number" min="0" step="0.01" />
        </el-form-item>
        <el-form-item label="差异说明">
          <el-input v-model="differenceForm.reason" maxlength="1000" />
        </el-form-item>
        <el-button
          data-test="add-difference"
          :disabled="commandBusy || !canAddDifference"
          @click="createDifference"
        >
          登记差异
        </el-button>
      </el-form>

      <el-table :data="differences" empty-text="该批次没有差异记录">
        <el-table-column label="差异记录" min-width="230">
          <template #default="{ row }">
            <div>{{ differenceTypes[row.differenceType] || '待核实' }}</div>
            <small v-if="row.orderId">订单 #{{ row.orderId }}</small>
            <small v-if="row.externalReference">渠道流水 {{ row.externalReference }}</small>
          </template>
        </el-table-column>
        <el-table-column label="渠道 / 本地金额" width="180" align="right">
          <template #default="{ row }">
            {{ money(row.expectedCent) }} / {{ money(row.actualCent) }}
          </template>
        </el-table-column>
        <el-table-column label="处理状态" width="120">
          <template #default="{ row }">{{ differenceStates[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column label="核对说明" min-width="190">
          <template #default="{ row }">
            <el-input
              v-if="canWrite && row.status !== 'closed'"
              v-model="resolutionNotes[row.id]"
              maxlength="1000"
              placeholder="填写本次处理说明"
            />
            <span v-else>{{ row.resolution || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已核验证据" min-width="200">
          <template #default="{ row }">
            <div class="evidence-list">
              <el-button
                v-for="fileId in row.evidenceFileIds || []"
                :key="fileId"
                link
                :disabled="fileBusy === fileId || !canReadFiles"
                @click="openEvidence(fileId)"
              >
                文件 #{{ fileId }}
              </el-button>
              <span v-if="pendingEvidence[row.id]?.length" class="muted">
                新增 {{ pendingEvidence[row.id].length }} 份
              </span>
              <label
                v-if="canWrite && canUploadEvidence && row.status === 'processing'"
                class="file-picker compact"
              >
                上传处理证据
                <input
                  type="file"
                  accept=".csv,.xlsx,application/pdf,image/jpeg,image/png,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  :disabled="uploadBusy"
                  @change="chooseDifferenceEvidence(row, $event)"
                >
              </label>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="190" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canWrite && row.status === 'open'"
              link
              :disabled="commandBusy || !resolutionNotes[row.id]?.trim()"
              @click="startDifference(row)"
            >
              领取处理
            </el-button>
            <el-button
              v-if="canWrite && row.status === 'processing'"
              data-test="review-difference"
              link
              :disabled="commandBusy || !canSubmitReview(row)"
              @click="reviewDifference(row)"
            >
              提交复核
            </el-button>
            <el-button
              v-if="canWrite && row.status === 'review'"
              link
              :disabled="commandBusy || !hasEvidence(row) || !resolutionNotes[row.id]?.trim()"
              @click="closeDifference(row)"
            >
              关闭差异
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="close-batch">
        <el-input
          v-if="canWrite && selectedBatch.status !== 'closed'"
          v-model="closeReason"
          maxlength="500"
          placeholder="说明本批次核对结论"
        />
        <el-button
          v-if="canWrite && selectedBatch.status !== 'closed'"
          data-test="close-reconciliation"
          type="primary"
          :disabled="commandBusy || selectedBatch.openDifferenceCount > 0 || !closeReason.trim()"
          @click="closeBatch(selectedBatch)"
        >
          关闭日对账
        </el-button>
        <span v-if="selectedBatch.openDifferenceCount > 0" class="muted">
          仍有未决差异，全部关闭后才能关闭批次
        </span>
      </div>
    </el-card>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  addMallDifference,
  closeMallReconciliation,
  createMallReconciliation,
  createReconciliationEvidenceUploadState,
  getAdminMallFileAccess,
  getMallReconciliation,
  listMallDifferences,
  listMallReconciliations,
  updateMallDifference,
  uploadReconciliationEvidence,
} from '@/api/mall-finance'

const batchStates = {
  draft: '待核对',
  processing: '处理中',
  review: '待复核',
  closed: '已关闭',
}
const differenceStates = {
  open: '待领取',
  processing: '处理中',
  review: '待复核',
  closed: '已关闭',
}
const differenceTypes = {
  channel_only: '渠道有、本地无',
  local_only: '本地有、渠道无',
  amount_mismatch: '金额不一致',
  unlinked: '未关联流水',
  duplicate: '重复流水',
  fee_or_settlement_timing: '手续费或结算时差',
}
const auth = useAuthStore()
const canRead = computed(() => auth.hasPermission('mall.reconciliations.read'))
const canWrite = computed(() => auth.hasPermission('mall.reconciliations.write'))
const canReadFiles = computed(() => auth.hasPermission('mall.files.read'))
const canUploadEvidence = computed(() => auth.hasPermission('mall.files.write'))
const batches = ref([])
const selectedBatch = ref(null)
const differences = ref([])
const loading = ref(false)
const commandBusy = ref(false)
const uploadBusy = ref(false)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
const statementFileId = ref('')
const fileBusy = ref('')
const closeReason = ref('')
const pendingEvidence = reactive({})
const resolutionNotes = reactive({})
const createForm = reactive({
  businessDate: '',
  expectedPaid: '0.00',
  expectedRefund: '0.00',
  evidenceNote: '',
})
const differenceForm = reactive({
  orderId: '',
  externalReference: '',
  differenceType: 'amount_mismatch',
  expectedAmount: '0.00',
  actualAmount: '0.00',
  reason: '',
})
const canCreateBatch = computed(
  () =>
    canWrite.value &&
    canUploadEvidence.value &&
    !!statementFileId.value &&
    !!createForm.businessDate &&
    !!createForm.evidenceNote.trim() &&
    toCent(createForm.expectedPaid) != null &&
    toCent(createForm.expectedRefund) != null
)
const canAddDifference = computed(
  () =>
    !!selectedBatch.value &&
    (differenceForm.orderId.trim() || differenceForm.externalReference.trim()) &&
    differenceForm.reason.trim() &&
    toCent(differenceForm.expectedAmount) != null &&
    toCent(differenceForm.actualAmount) != null &&
    (differenceForm.differenceType !== 'unlinked' ||
      differenceForm.externalReference.trim())
)

function money(cent) {
  return `¥${(Number(cent || 0) / 100).toFixed(2)}`
}
function toCent(value) {
  const text = String(value ?? '').trim()
  if (!/^\d{1,13}(?:\.\d{1,2})?$/.test(text)) return null
  const [whole, fraction = ''] = text.split('.')
  return Number(whole) * 100 + Number((fraction + '00').slice(0, 2))
}
function key() {
  return crypto.randomUUID()
}
function notify(message, type = 'success') {
  notice.value = message
  noticeType.value = type
}

async function load() {
  if (!canRead.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await listMallReconciliations({ pageSize: 100 })
    batches.value = result.items || []
    if (selectedBatch.value) {
      const refreshed = batches.value.find((item) => item.id === selectedBatch.value.id)
      if (refreshed) await openBatch(refreshed)
      else if (batches.value.length) await openBatch(batches.value[0])
      else selectedBatch.value = null
    } else if (batches.value.length) {
      await openBatch(batches.value[0])
    }
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '日对账列表读取失败'
  } finally {
    loading.value = false
  }
}

async function openBatch(row) {
  if (!canRead.value || !row?.id) return
  error.value = ''
  try {
    const [detail, result] = await Promise.all([
      getMallReconciliation(row.id),
      listMallDifferences(row.id, { pageSize: 100 }),
    ])
    selectedBatch.value = detail
    differences.value = result.items || []
    for (const difference of differences.value) {
      resolutionNotes[difference.id] ??= ''
      pendingEvidence[difference.id] ??= []
    }
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '对账批次读取失败'
  }
}

async function uploadEvidence(file) {
  if (!canUploadEvidence.value || !file || uploadBusy.value) return null
  uploadBusy.value = true
  error.value = ''
  try {
    const state = createReconciliationEvidenceUploadState(file)
    const result = await uploadReconciliationEvidence(state)
    if (result.status !== 'verified') throw new Error('证据文件尚未通过核验')
    return String(result.id || result.fileId)
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '对账证据上传失败'
    return null
  } finally {
    uploadBusy.value = false
  }
}

async function chooseStatementFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  statementFileId.value = ''
  const fileId = await uploadEvidence(file)
  if (fileId) {
    statementFileId.value = fileId
    notify(`渠道账单已上传并核验（文件 #${fileId}）`)
  }
}

async function chooseDifferenceEvidence(row, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const fileId = await uploadEvidence(file)
  if (fileId) {
    pendingEvidence[row.id] ??= []
    pendingEvidence[row.id].push(fileId)
    notify(`处理证据已核验（文件 #${fileId}）`)
  }
}

async function createBatch() {
  if (!canCreateBatch.value || commandBusy.value) return
  commandBusy.value = true
  error.value = ''
  try {
    const created = await createMallReconciliation(
      {
        businessDate: createForm.businessDate,
        statementFileId: statementFileId.value,
        expectedPaidCent: toCent(createForm.expectedPaid),
        expectedRefundCent: toCent(createForm.expectedRefund),
        evidenceNote: createForm.evidenceNote.trim(),
      },
      key()
    )
    statementFileId.value = ''
    createForm.evidenceNote = ''
    notify('日对账批次已登记')
    await load()
    if (created?.id) {
      const row = batches.value.find((item) => item.id === created.id) || created
      await openBatch(row)
    }
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '日对账批次登记失败'
  } finally {
    commandBusy.value = false
  }
}

async function createDifference() {
  if (!canAddDifference.value || commandBusy.value || !selectedBatch.value) return
  commandBusy.value = true
  error.value = ''
  try {
    await addMallDifference(
      {
        batchId: selectedBatch.value.id,
        ...(differenceForm.orderId.trim() ? { orderId: differenceForm.orderId.trim() } : {}),
        ...(differenceForm.externalReference.trim()
          ? { externalReference: differenceForm.externalReference.trim() }
          : {}),
        differenceType: differenceForm.differenceType,
        expectedCent: toCent(differenceForm.expectedAmount),
        actualCent: toCent(differenceForm.actualAmount),
        assignedTo: auth.user?.userId ? String(auth.user.userId) : null,
        reason: differenceForm.reason.trim(),
      },
      key()
    )
    differenceForm.reason = ''
    notify('差异已登记，请领取后核对')
    await load()
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '差异登记失败'
  } finally {
    commandBusy.value = false
  }
}

async function updateDifference(row, targetStatus, reason, evidenceFileIds = []) {
  if (!canWrite.value || commandBusy.value || !reason?.trim()) return null
  commandBusy.value = true
  error.value = ''
  try {
    const result = await updateMallDifference(
      {
        id: row.id,
        expectedVersion: row.version,
        targetStatus,
        ...(targetStatus === 'processing' && auth.user?.userId
          ? { assignedTo: String(auth.user.userId) }
          : {}),
        reason: reason.trim(),
        evidenceFileIds,
      },
      key()
    )
    notify(
      targetStatus === 'review'
        ? '差异已提交复核'
        : targetStatus === 'closed'
          ? '差异已关闭'
          : '已领取差异处理'
    )
    await load()
    return result
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '差异状态更新失败'
    return null
  } finally {
    commandBusy.value = false
  }
}

function hasEvidence(row) {
  return (row.evidenceFileIds || []).length + (pendingEvidence[row.id] || []).length > 0
}
function canSubmitReview(row) {
  return hasEvidence(row) && !!resolutionNotes[row.id]?.trim()
}
function startDifference(row) {
  return updateDifference(row, 'processing', resolutionNotes[row.id])
}
async function reviewDifference(row) {
  if (!hasEvidence(row)) {
    error.value = '先上传并核验处理证据，再提交复核'
    return null
  }
  if (!resolutionNotes[row.id]?.trim()) {
    error.value = '请填写本次差异处理说明'
    return null
  }
  return updateDifference(
    row,
    'review',
    resolutionNotes[row.id],
    pendingEvidence[row.id] || []
  )
}
async function closeDifference(row) {
  if (!hasEvidence(row)) {
    error.value = '缺少已核验证据，不能关闭差异'
    return null
  }
  return updateDifference(row, 'closed', resolutionNotes[row.id])
}

async function closeBatch(row) {
  if (!canWrite.value || commandBusy.value || !row) return null
  if (Number(row.openDifferenceCount) > 0) {
    error.value = '仍有未决差异，全部关闭后才能关闭日对账'
    return null
  }
  if (!closeReason.value.trim()) {
    error.value = '请填写本批次核对结论'
    return null
  }
  commandBusy.value = true
  error.value = ''
  try {
    const result = await closeMallReconciliation(
      {
        id: row.id,
        expectedVersion: row.version,
        reason: closeReason.value.trim(),
      },
      key()
    )
    closeReason.value = ''
    notify('日对账批次已关闭')
    await load()
    return result
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '日对账批次关闭失败'
    return null
  } finally {
    commandBusy.value = false
  }
}

async function openEvidence(fileId) {
  if (!canReadFiles.value || fileBusy.value) return
  fileBusy.value = fileId
  error.value = ''
  try {
    const result = await getAdminMallFileAccess(fileId)
    const target = new URL(result.accessUrl)
    if (target.protocol !== 'https:') throw new Error('对账文件访问地址不安全')
    window.open(target.href, '_blank', 'noopener,noreferrer')
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '对账证据暂不可访问'
  } finally {
    fileBusy.value = ''
  }
}

onMounted(load)
defineExpose({
  batches,
  selectedBatch,
  differences,
  error,
  load,
  openBatch,
  createBatch,
  createDifference,
  reviewDifference,
  closeDifference,
  closeBatch,
  hasEvidence,
})
</script>

<style scoped>
.reconciliation-panel {
  padding: 4px 0 20px;
}
.panel-heading,
.batch-title,
.close-batch,
.amount-comparison {
  display: flex;
  align-items: center;
  gap: 16px;
}
.panel-heading,
.close-batch {
  justify-content: space-between;
}
.panel-heading {
  margin: 12px 0 18px;
}
.panel-heading h3 {
  margin: 0 0 6px;
}
.panel-heading p,
.batch-title span,
.muted {
  color: #6b7280;
}
.panel-heading p {
  margin: 0;
}
.create-batch,
.batch-detail {
  margin: 16px 0;
}
.batch-form,
.amount-comparison,
.difference-form {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.batch-form .el-form-item {
  width: min(240px, 100%);
}
.batch-form .file-picker {
  display: block;
}
.batch-table {
  margin: 16px 0;
}
.batch-title span {
  font-weight: 400;
  margin-left: 8px;
}
.amount-comparison {
  flex-wrap: wrap;
  margin-bottom: 18px;
  padding: 14px;
  background: #f7f8fa;
  border-radius: 6px;
}
.amount-comparison div {
  display: grid;
  gap: 6px;
  min-width: 150px;
}
.amount-comparison span,
small {
  color: #6b7280;
}
.difference-form {
  padding: 14px 0;
}
.difference-form .el-form-item {
  width: min(190px, 100%);
}
.evidence-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.file-picker {
  color: #409eff;
  cursor: pointer;
}
.file-picker input {
  display: block;
  max-width: 220px;
  margin-top: 5px;
}
.file-picker.compact input {
  width: 190px;
}
.close-batch {
  margin-top: 18px;
}
.close-batch .el-input {
  max-width: 450px;
}
@media (max-width: 720px) {
  .panel-heading,
  .close-batch {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
