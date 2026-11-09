<template>
  <section class="invoice-page">
    <header class="page-heading">
      <div>
        <el-button link @click="router.push('/mall/invoices')"
          >返回发票列表</el-button
        >
        <h2>发票办理详情</h2>
      </div>
      <el-button
        data-test="reload"
        :disabled="loading || command.pending.value"
        @click="load"
      >
        刷新
      </el-button>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="command.error.value"
      :title="command.error.value"
      type="error"
      :closable="false"
    />
    <el-alert
      v-if="notice"
      :title="notice"
      :type="noticeType"
      :closable="false"
    />
    <el-button
      v-if="command.pending.value"
      :loading="command.busy.value"
      @click="retry"
    >
      重试原操作
    </el-button>

    <div v-loading="loading">
      <template v-if="request">
        <el-card class="summary-card">
          <template #header>
            <div class="card-heading">
              <strong>{{ request.requestNo }}</strong>
              <el-tag :type="stateType(request.status)">
                {{ requestStates[request.status] || '待核实' }}
              </el-tag>
            </div>
          </template>
          <dl class="facts">
            <div>
              <dt>关联订单</dt>
              <dd>{{ request.orderId }}</dd>
            </div>
            <div>
              <dt>申请人类型</dt>
              <dd>{{ request.buyerType === 'company' ? '企业' : '个人' }}</dd>
            </div>
            <div>
              <dt>发票需求</dt>
              <dd>
                {{ request.invoiceType === 'manual_special_request' ? '专票需求（人工核实）' : '普通数电票' }}
              </dd>
            </div>
            <div>
              <dt>发票抬头</dt>
              <dd>{{ request.title }}</dd>
            </div>
            <div>
              <dt>纳税人识别号</dt>
              <dd>{{ request.taxNoMasked || '—' }}</dd>
            </div>
            <div>
              <dt>商品金额</dt>
              <dd>¥{{ money(request.requestedGoodsCent) }}</dd>
            </div>
            <div>
              <dt>运费金额</dt>
              <dd>¥{{ money(request.requestedFreightCent) }}</dd>
            </div>
            <div>
              <dt>申请总额</dt>
              <dd>
                ¥{{
                  money(
                    request.requestedGoodsCent + request.requestedFreightCent
                  )
                }}
              </dd>
            </div>
            <div>
              <dt>成功退款后净实付</dt>
              <dd>¥{{ money(request.netPaidCent) }}</dd>
            </div>
            <div>
              <dt>申请版本</dt>
              <dd>{{ request.version }}</dd>
            </div>
            <div>
              <dt>领取人</dt>
              <dd>{{ request.claimedBy || '尚未领取' }}</dd>
            </div>
          </dl>
          <p class="gate-note">
            完整税号和邮箱原文暂不可读取。若税务办理必须使用原文，需等待资料授权门禁开放。
          </p>
        </el-card>

        <el-card v-if="canClaim" class="action-card">
          <template #header>领取开票申请</template>
          <p>
            领取后由当前财务人员办理，蓝票回传与资料补充会校验领取归属及申请版本。
          </p>
          <el-button
            data-test="claim-invoice"
            type="primary"
            :disabled="command.pending.value"
            @click="claim"
          >
            领取办理
          </el-button>
        </el-card>

        <el-card v-if="canAskForInfo" class="action-card">
          <template #header>请买家补充或更正资料</template>
          <el-input
            v-model="infoReason"
            data-test="info-reason"
            type="textarea"
            maxlength="500"
            placeholder="说明需要买家核实的内容，不填写完整税号或邮箱"
          />
          <el-button
            data-test="needs-info"
            :disabled="command.pending.value"
            @click="requestInfo"
          >
            通知买家补充
          </el-button>
        </el-card>

        <el-card
          v-if="canIssueBlue || (canReissueBlue && issueForm.replacementForId)"
          class="action-card"
        >
          <template #header>{{
            issueForm.replacementForId ? '回传替代蓝票' : '回传实际蓝票'
          }}</template>
          <p v-if="issueForm.replacementForId">
            仅当原蓝票已全额红冲后可重开；金额固定为成功退款后的净实付 ¥{{
              money(request.netPaidCent)
            }}。
          </p>
          <p v-else>
            按真实税务票据填写票号和主体，金额固定为申请金额；上传PDF完成私有存储校验后才能提交。
          </p>
          <el-form label-position="top" :disabled="command.pending.value">
            <div class="form-grid">
              <el-form-item label="实际票号"
                ><el-input v-model="issueForm.invoiceNo" maxlength="64"
              /></el-form-item>
              <el-form-item label="开具时间"
                ><el-input v-model="issueForm.issuedAt" type="datetime-local"
              /></el-form-item>
              <el-form-item label="销售主体"
                ><el-input v-model="issueForm.sellerIdentity" maxlength="64"
              /></el-form-item>
              <el-form-item label="票面金额"
                ><el-input :model-value="money(issueAmountCent)" disabled
              /></el-form-item>
            </div>
            <label class="file-label"
              >真实蓝票 PDF
              <input
                data-test="blue-file"
                type="file"
                accept="application/pdf"
                :disabled="uploadBusy"
                @change="chooseBlueFile"
              />
            </label>
            <span v-if="issueForm.fileId" class="file-state"
              >文件已上传并校验（{{ issueForm.fileId }}）</span
            >
            <el-alert
              v-if="uploadError"
              :title="uploadError"
              type="error"
              :closable="false"
            />
            <el-button
              v-if="blueUploadState && uploadError"
              data-test="retry-blue-upload"
              :disabled="uploadBusy"
              @click="uploadBlueState"
              >重试上传/核验</el-button
            >
            <el-input
              v-model="issueForm.reason"
              class="reason"
              maxlength="500"
              placeholder="备注（可选，不包含完整税号或邮箱）"
            />
            <el-button
              data-test="record-blue"
              type="primary"
              :disabled="!issueForm.fileId || command.pending.value"
              @click="recordBlue"
            >
              保存真实蓝票记录
            </el-button>
          </el-form>
        </el-card>

        <el-card v-if="request.invoices?.length" class="chain-card">
          <template #header>真实票据链</template>
          <el-table :data="request.invoices" empty-text="暂无票据">
            <el-table-column prop="invoiceNo" label="票号" min-width="190" />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">{{
                row.kind === 'blue' ? '蓝票' : '红票'
              }}</template>
            </el-table-column>
            <el-table-column label="金额" width="130">
              <template #default="{ row }"
                >¥{{ money(row.totalCent) }}</template
              >
            </el-table-column>
            <el-table-column label="状态" width="130">
              <template #default="{ row }">{{
                invoiceStates[row.status] || '待核实'
              }}</template>
            </el-table-column>
            <el-table-column label="关联票据" width="130">
              <template #default="{ row }">{{
                row.originalInvoiceId || row.replacementForId || '—'
              }}</template>
            </el-table-column>
            <el-table-column label="文件" width="150">
              <template #default="{ row }">
                <el-button
                  link
                  :disabled="!canReadFiles || fileBusy === row.fileId"
                  @click="openInvoiceFile(row.fileId)"
                  >查看 PDF</el-button
                >
              </template>
            </el-table-column>
            <el-table-column label="红冲/补件" min-width="210">
              <template #default="{ row }">
                <el-button
                  v-if="
                    canHandleIssuedInvoice &&
                    row.kind === 'blue' &&
                    ['valid', 'partially_red'].includes(row.status)
                  "
                  link
                  :disabled="command.pending.value"
                  @click="openRedPending(row, 'red_pending')"
                  >登记红冲待办</el-button
                >
                <el-button
                  v-if="
                    canHandleIssuedInvoice &&
                    row.kind === 'blue' &&
                    row.status === 'red_pending'
                  "
                  link
                  :disabled="command.pending.value"
                  @click="openRedPending(row, 'awaiting_counterparty')"
                  >标记待对方确认</el-button
                >
                <el-button
                  v-if="
                    canHandleIssuedInvoice &&
                    row.kind === 'blue' &&
                    ['red_pending', 'awaiting_counterparty'].includes(
                      row.status
                    )
                  "
                  :data-test="`record-red-${row.id}`"
                  link
                  :disabled="command.pending.value"
                  @click="activeRedInvoiceId = row.id"
                  >回传红票</el-button
                >
                <el-button
                  v-if="canHandleIssuedInvoice"
                  link
                  :disabled="command.pending.value"
                  @click="activeFileInvoiceId = row.id"
                  >补交同票文件</el-button
                >
                <el-button
                  v-if="canReissueBlue && canReplace(row)"
                  :data-test="`reissue-blue-${row.id}`"
                  link
                  :disabled="command.pending.value"
                  @click="beginReplacement(row)"
                  >按净额重开</el-button
                >
              </template>
            </el-table-column>
          </el-table>

          <el-card v-if="activeRedInvoice" class="sub-action">
            <template #header
              >回传红票：关联蓝票 {{ activeRedInvoice.invoiceNo }}</template
            >
            <div class="form-grid">
              <el-input
                v-model="redForms[activeRedInvoice.id].invoiceNo"
                placeholder="红票票号"
              />
              <el-input
                v-model="redForms[activeRedInvoice.id].issuedAt"
                type="datetime-local"
              />
              <el-input-number
                v-model="redForms[activeRedInvoice.id].totalCent"
                :min="1"
                :max="redRemaining(activeRedInvoice)"
              />
              <el-input
                v-model="redForms[activeRedInvoice.id].reason"
                placeholder="红冲说明"
              />
            </div>
            <label class="file-label"
              >真实红票 PDF
              <input
                type="file"
                accept="application/pdf"
                :disabled="uploadBusy"
                @change="chooseRedFile(activeRedInvoice.id, $event)"
              />
            </label>
            <el-button
              data-test="save-red"
              :disabled="
                !redForms[activeRedInvoice.id].fileId || command.pending.value
              "
              @click="recordRed(activeRedInvoice.id)"
              >保存实际红票</el-button
            >
          </el-card>

          <el-card v-if="activeFileInvoice" class="sub-action">
            <template #header>补交同一张票据文件</template>
            <p>仅更换文件引用；不新增票号、不重复确认发票金额或绩效消费。</p>
            <label class="file-label"
              >核验后的 PDF
              <input
                type="file"
                accept="application/pdf"
                :disabled="uploadBusy"
                @change="chooseReplacementFile(activeFileInvoice.id, $event)"
              />
            </label>
            <el-input
              v-model="replacementReason"
              maxlength="500"
              placeholder="说明原文件无法使用的原因"
            />
            <el-button
              data-test="replace-file"
              :disabled="!replacementFileId || command.pending.value"
              @click="replaceFile(activeFileInvoice.id)"
              >替换票据文件</el-button
            >
          </el-card>
        </el-card>
        <el-alert
          v-if="request.status === 'unknown'"
          title="实际出票结果待人工核实。请先查证真实票号，不要重复开票。"
          type="warning"
          :closable="false"
        />
      </template>
      <el-empty v-else-if="!loading && !error" description="开票申请暂不可用" />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-invoices'
import { useMallCommand } from '@/composables/useMallCommand'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const request = ref(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
const infoReason = ref('')
const issueForm = reactive({
  invoiceNo: '',
  issuedAt: '',
  sellerIdentity: '',
  fileId: '',
  reason: '',
  replacementForId: '',
})
const redForms = reactive({})
const replacementReason = ref('')
const replacementFileId = ref('')
const uploadBusy = ref(false)
const uploadError = ref('')
const fileBusy = ref('')
const activeRedInvoiceId = ref('')
const activeFileInvoiceId = ref('')
const blueUploadState = ref(null)
const redUploadStates = reactive({})
const replacementUploadState = ref(null)
const command = useMallCommand()
let loadGeneration = 0

const requestStates = {
  submitted: '待领取',
  needs_info: '待买家补充',
  issuing: '财务办理中',
  unknown: '结果待核实',
  delivered: '已回传票据',
  withdrawn: '已撤回',
  closed: '已关闭',
}
const invoiceStates = {
  valid: '有效',
  red_pending: '待红冲',
  awaiting_counterparty: '待对方确认',
  partially_red: '部分红冲',
  fully_red: '已全额红冲',
}
const writer = computed(() => auth.hasPermission('mall.invoices.write'))
const reader = computed(() => auth.hasPermission('mall.invoices.read'))
const claimedByMe = computed(
  () => request.value?.claimedBy === auth.user?.userId
)
const canClaim = computed(
  () =>
    writer.value &&
    request.value &&
    request.value.status === 'submitted' &&
    (!request.value.claimedBy || claimedByMe.value)
)
const canAskForInfo = computed(
  () => writer.value && request.value?.status === 'issuing' && claimedByMe.value
)
const canIssueBlue = computed(
  () => writer.value && request.value?.status === 'issuing' && claimedByMe.value
)
const canHandleIssuedInvoice = computed(() => writer.value && claimedByMe.value)
const canReissueBlue = computed(
  () =>
    writer.value &&
    claimedByMe.value &&
    request.value &&
    ['delivered', 'unknown'].includes(request.value.status) &&
    (request.value.invoices || []).some((invoice) => canReplace(invoice))
)
const canReadFiles = computed(
  () => reader.value && auth.hasPermission('mall.files.read')
)
const issueAmountCent = computed(() =>
  issueForm.replacementForId
    ? Number(request.value?.netPaidCent || 0)
    : Number(request.value?.requestedGoodsCent || 0) +
      Number(request.value?.requestedFreightCent || 0)
)
const activeRedInvoice = computed(
  () =>
    request.value?.invoices?.find(
      (invoice) => invoice.id === activeRedInvoiceId.value
    ) || null
)
const activeFileInvoice = computed(
  () =>
    request.value?.invoices?.find(
      (invoice) => invoice.id === activeFileInvoiceId.value
    ) || null
)

function money(cent) {
  return (Number(cent || 0) / 100).toFixed(2)
}
function stateType(status) {
  if (status === 'delivered') return 'success'
  if (status === 'unknown' || status === 'needs_info') return 'warning'
  if (status === 'withdrawn' || status === 'closed') return 'info'
  return 'primary'
}
function currentAdminId() {
  return auth.user?.userId
}
function canUploadForRequest() {
  return (
    !!request.value &&
    writer.value &&
    request.value.claimedBy === currentAdminId()
  )
}
function ensureRedForm(invoice) {
  if (!redForms[invoice.id]) {
    redForms[invoice.id] = {
      invoiceNo: '',
      issuedAt: '',
      totalCent: redRemaining(invoice),
      fileId: '',
      reason: '',
    }
  }
}
function redRemaining(invoice) {
  const redeemed = (request.value?.invoices || [])
    .filter(
      (row) =>
        row.kind === 'red' &&
        row.originalInvoiceId === invoice.id &&
        row.status === 'valid'
    )
    .reduce((sum, row) => sum + Number(row.totalCent || 0), 0)
  return Math.max(0, Number(invoice.totalCent || 0) - redeemed)
}
function canReplace(invoice) {
  if (!invoice || invoice.kind !== 'blue' || invoice.status !== 'fully_red')
    return false
  return !(request.value?.invoices || []).some(
    (row) => row.kind === 'blue' && row.replacementForId === invoice.id
  )
}
function beginReplacement(invoice) {
  if (!canReissueBlue.value || !canReplace(invoice)) return
  Object.assign(issueForm, {
    invoiceNo: '',
    issuedAt: '',
    sellerIdentity: invoice.sellerIdentity || '',
    fileId: '',
    reason: '',
    replacementForId: invoice.id,
  })
}

async function load() {
  if (command.pending.value) return
  const generation = ++loadGeneration
  const identity = props.id
  loading.value = true
  error.value = ''
  request.value = null
  try {
    const result = await api.getAdminMallInvoiceRequest(identity)
    if (generation === loadGeneration && props.id === identity) {
      request.value = result
      for (const invoice of result.invoices || []) ensureRedForm(invoice)
      if (
        result.status === 'issuing' &&
        result.claimedBy === currentAdminId()
      ) {
        issueForm.fileId = ''
        issueForm.replacementForId = ''
      }
    }
  } catch (failure) {
    if (generation === loadGeneration)
      error.value = failure.userMessage || failure.message || '发票详情读取失败'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function afterCommand(result, message) {
  if (!result) return
  notice.value = message
  noticeType.value = 'success'
  await load()
}
async function claim() {
  if (!canClaim.value || command.pending.value) return
  await afterCommand(
    await command.run(api.claimMallInvoice, {
      id: props.id,
      expectedVersion: request.value.version,
    }),
    '已领取开票申请。'
  )
}
async function requestInfo() {
  if (!canAskForInfo.value || command.pending.value) return
  const reason = infoReason.value.trim()
  if (!reason) {
    error.value = '请填写补充说明'
    return
  }
  await afterCommand(
    await command.run(api.needMallInvoiceInfo, {
      id: props.id,
      expectedVersion: request.value.version,
      reason,
    }),
    '已通知买家补充或更正申请资料。'
  )
}
async function uploadState(state) {
  if (uploadBusy.value) return null
  uploadBusy.value = true
  uploadError.value = ''
  try {
    return await api.uploadInvoicePdf(state)
  } catch (failure) {
    uploadError.value =
      failure.userMessage || failure.message || '发票PDF上传失败'
    return null
  } finally {
    uploadBusy.value = false
  }
}
function stateFor(file) {
  return api.createInvoicePdfUploadState(file, request.value.orderId)
}
async function uploadBlueState() {
  if (!blueUploadState.value || !canUploadForRequest()) return
  const result = await uploadState(blueUploadState.value)
  if (result) issueForm.fileId = result.id || result.fileId
}
async function uploadBlueFile(file) {
  if (
    !(
      canIssueBlue.value ||
      (canReissueBlue.value && issueForm.replacementForId)
    ) ||
    !file
  )
    return
  if (
    file.type !== 'application/pdf' ||
    file.size < 1 ||
    file.size > 10 * 1024 * 1024
  ) {
    uploadError.value = '请选择不超过 10 MB 的 PDF 发票文件'
    return
  }
  blueUploadState.value = stateFor(file)
  issueForm.fileId = ''
  await uploadBlueState()
}
async function chooseBlueFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) await uploadBlueFile(file)
}
async function recordBlue() {
  if (
    !(
      canIssueBlue.value ||
      (canReissueBlue.value && issueForm.replacementForId)
    ) ||
    !issueForm.fileId ||
    command.pending.value
  )
    return
  if (
    !issueForm.invoiceNo.trim() ||
    !issueForm.issuedAt ||
    !issueForm.sellerIdentity.trim()
  ) {
    error.value = '请填写真实票号、开具时间和销售主体'
    return
  }
  const result = await command.run(api.recordMallInvoice, {
    id: props.id,
    expectedVersion: request.value.version,
    invoiceNo: issueForm.invoiceNo.trim(),
    issuedAt: new Date(issueForm.issuedAt).toISOString(),
    sellerIdentity: issueForm.sellerIdentity.trim(),
    totalCent: issueAmountCent.value,
    fileId: issueForm.fileId,
    ...(issueForm.replacementForId
      ? { replacementForId: issueForm.replacementForId }
      : {}),
    ...(issueForm.reason.trim() ? { reason: issueForm.reason.trim() } : {}),
  })
  await afterCommand(
    result,
    issueForm.replacementForId ? '已回传替代蓝票事实。' : '已保存实际蓝票事实。'
  )
  if (result)
    Object.assign(issueForm, {
      invoiceNo: '',
      issuedAt: '',
      sellerIdentity: '',
      fileId: '',
      reason: '',
      replacementForId: '',
    })
}
async function openRedPending(invoice, targetStatus) {
  if (!canHandleIssuedInvoice.value || command.pending.value) return
  const message =
    targetStatus === 'awaiting_counterparty'
      ? '请说明对方确认待办原因'
      : '请说明红冲待办原因'
  const reason = window.prompt(message)
  if (!reason?.trim()) return
  await afterCommand(
    await command.run(api.markMallRedPending, {
      id: invoice.id,
      expectedVersion: invoice.version,
      targetStatus,
      reason: reason.trim(),
    }),
    '已登记红冲待办，尚未确认税务红票完成。'
  )
}
async function uploadRedFile(invoiceId, file) {
  const invoice = request.value?.invoices?.find((row) => row.id === invoiceId)
  if (!invoice || !canHandleIssuedInvoice.value || !file) return
  if (
    file.type !== 'application/pdf' ||
    file.size < 1 ||
    file.size > 10 * 1024 * 1024
  ) {
    uploadError.value = '请选择不超过 10 MB 的 PDF 红票文件'
    return
  }
  ensureRedForm(invoice)
  redUploadStates[invoiceId] = stateFor(file)
  const uploaded = await uploadState(redUploadStates[invoiceId])
  if (uploaded) redForms[invoiceId].fileId = uploaded.id || uploaded.fileId
}
async function chooseRedFile(invoiceId, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) await uploadRedFile(invoiceId, file)
}
async function recordRed(invoiceId) {
  const invoice = request.value?.invoices?.find((row) => row.id === invoiceId)
  const form = redForms[invoiceId]
  if (
    !invoice ||
    !form ||
    !form.fileId ||
    !canHandleIssuedInvoice.value ||
    command.pending.value
  )
    return
  if (
    !form.invoiceNo.trim() ||
    !form.issuedAt ||
    !form.reason.trim() ||
    form.totalCent > redRemaining(invoice)
  ) {
    error.value = '请填写红票信息，并确保金额不超过原票剩余覆盖'
    return
  }
  await afterCommand(
    await command.run(api.recordMallRedInvoice, {
      id: invoice.id,
      expectedVersion: invoice.version,
      invoiceNo: form.invoiceNo.trim(),
      issuedAt: new Date(form.issuedAt).toISOString(),
      totalCent: Number(form.totalCent),
      fileId: form.fileId,
      reason: form.reason.trim(),
    }),
    '已回传真实红票事实。'
  )
}
async function uploadReplacementFile(invoiceId, file) {
  const invoice = request.value?.invoices?.find((row) => row.id === invoiceId)
  if (!invoice || !canHandleIssuedInvoice.value || !file) return
  if (
    file.type !== 'application/pdf' ||
    file.size < 1 ||
    file.size > 10 * 1024 * 1024
  ) {
    uploadError.value = '请选择不超过 10 MB 的 PDF 文件'
    return
  }
  replacementUploadState.value = stateFor(file)
  const uploaded = await uploadState(replacementUploadState.value)
  if (uploaded) replacementFileId.value = uploaded.id || uploaded.fileId
}
async function chooseReplacementFile(invoiceId, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) await uploadReplacementFile(invoiceId, file)
}
async function replaceFile(invoiceId) {
  const invoice = request.value?.invoices?.find((row) => row.id === invoiceId)
  if (
    !invoice ||
    !replacementFileId.value ||
    !replacementReason.value.trim() ||
    !canHandleIssuedInvoice.value
  )
    return
  await afterCommand(
    await command.run(api.replaceMallInvoiceFile, {
      id: invoice.id,
      expectedVersion: invoice.version,
      fileId: replacementFileId.value,
      reason: replacementReason.value.trim(),
    }),
    '已替换同一张发票的文件，票号与金额事实未变。'
  )
}
async function openInvoiceFile(fileId) {
  if (!canReadFiles.value || fileBusy.value) return
  fileBusy.value = fileId
  error.value = ''
  try {
    const result = await api.getAdminMallInvoiceFileAccess(fileId)
    const target = new URL(result.accessUrl)
    if (target.protocol !== 'https:') throw new Error('票据访问地址不安全')
    window.open(target.href, '_blank', 'noopener,noreferrer')
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '票据文件暂不可访问'
  } finally {
    fileBusy.value = ''
  }
}
async function retry() {
  await afterCommand(await command.retry(), '原开票操作已确认。')
}

onMounted(load)
defineExpose({
  load,
  claim,
  requestInfo,
  uploadBlueFile,
  uploadBlueState,
  recordBlue,
  recordRed,
  uploadRedFile,
  replaceFile,
  retry,
  issueForm,
  redForms,
  infoReason,
  request,
  canIssueBlue,
  canAskForInfo,
  beginReplacement,
  canReplace,
})
</script>

<style scoped>
.invoice-page {
  padding: 20px;
}
.page-heading,
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.page-heading {
  margin: 12px 0 20px;
}
.page-heading h2 {
  margin: 8px 0 0;
}
.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(150px, 1fr));
  gap: 14px 24px;
  margin: 0;
}
.facts dt {
  color: #6b7280;
  font-size: 13px;
}
.facts dd {
  margin: 5px 0 0;
  font-weight: 600;
}
.gate-note {
  color: #9a6700;
  background: #fff9e8;
  padding: 10px 12px;
  border-radius: 4px;
}
.action-card,
.chain-card,
.sub-action {
  margin-top: 16px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 12px;
}
.file-label {
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 14px 10px 0;
}
.file-state {
  color: #217346;
  margin-right: 12px;
}
.reason {
  display: block;
  max-width: 640px;
  margin: 12px 0;
}
@media (max-width: 800px) {
  .facts,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
