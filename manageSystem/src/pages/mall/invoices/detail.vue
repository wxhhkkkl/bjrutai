<template>
  <section class="invoice-page mall-management-page">
    <header class="page-heading page-header">
      <div>
        <el-button link type="primary" @click="router.push('/mall/invoices')"
          >返回发票列表</el-button
        >
        <h2 class="page-title">发票办理详情</h2>
      </div>
    </header>
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
        </el-card>

        <el-card
          v-if="billingReleaseUiEnabled && canReleaseBilling"
          class="action-card release-card"
          data-test="billing-release-card"
        >
          <template #header>本申请开票资料</template>
          <p>
            只用于办理当前由你领取的申请。资料仅在本页临时显示，最长 60 秒；离开页面或切换标签后立即清除。请勿截图、复制或另存。
          </p>
          <el-button
            v-if="!billingReleased"
            data-test="release-billing"
            type="primary"
            :disabled="billingReleaseBusy"
            :loading="billingReleaseBusy"
            @click="billingReleaseOpen = true"
          >
            查看本申请开票资料
          </el-button>
          <el-alert
            v-if="billingReleased"
            type="warning"
            :closable="false"
            data-test="billing-release-data"
          >
            <template #title>开票资料（{{ billingSecondsRemaining }} 秒后清除）</template>
            <dl class="released-fields">
              <div><dt>发票抬头</dt><dd>{{ billingReleased.title }}</dd></div>
              <div v-if="billingReleased.taxNo"><dt>纳税人识别号</dt><dd>{{ billingReleased.taxNo }}</dd></div>
              <div><dt>访问审计号</dt><dd>{{ billingReleased.auditId }}</dd></div>
            </dl>
            <el-button data-test="clear-billing-release" @click="billingData.clear()">
              立即清除
            </el-button>
          </el-alert>
        </el-card>

        <el-card v-if="canClaim" class="action-card">
          <template #header>开始处理申请</template>
          <p>
            开始后由当前财务人员负责办理，用于避免重复处理；开具后上传真实发票到本申请，用户即可下载。
          </p>
          <el-button
            data-test="claim-invoice"
            type="primary"
            :disabled="command.pending.value"
            @click="claim"
          >
            开始处理
          </el-button>
        </el-card>

        <el-card v-if="canAskForInfo" class="action-card">
          <template #header>请买家补充或更正资料</template>
          <div class="info-request-form">
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
          </div>
        </el-card>

        <el-card
          v-if="canIssueBlue || (canReissueBlue && issueForm.replacementForId)"
          class="action-card"
        >
          <template #header>{{
            issueForm.replacementForId ? '上传替代发票 PDF' : '上传发票 PDF'
          }}</template>
          <div class="invoice-upload">
            <div class="invoice-upload__file">
              <span class="invoice-upload__icon" aria-hidden="true">
                <el-icon><Document /></el-icon>
              </span>
              <div class="invoice-upload__copy">
                <strong :title="blueUploadState?.file?.name">
                  {{ blueUploadState?.file?.name || '选择发票 PDF' }}
                </strong>
                <span v-if="uploadBusy" role="status">正在上传并校验…</span>
                <span v-else-if="issueForm.fileId" class="invoice-upload__verified" role="status">PDF 已上传并校验</span>
                <span v-else>PDF 格式，最大 10 MB</span>
              </div>
              <label class="invoice-upload__picker" :class="{ 'is-disabled': uploadBusy || command.pending.value }">
                {{ blueUploadState ? '更换文件' : '选择文件' }}
                <input
                  data-test="blue-file"
                  type="file"
                  accept="application/pdf"
                  aria-label="选择发票 PDF"
                  :disabled="uploadBusy || command.pending.value"
                  @change="chooseBlueFile"
                />
              </label>
            </div>
            <div class="invoice-upload__actions">
              <el-button
                v-if="blueUploadState && uploadError"
                data-test="retry-blue-upload"
                :disabled="uploadBusy || command.pending.value"
                @click="uploadBlueState"
              >重试上传/文件校验</el-button>
              <el-button
                data-test="record-blue"
                type="primary"
                :disabled="uploadBusy || !issueForm.fileId || command.pending.value"
                @click="recordBlue"
              >
                确认上传
              </el-button>
            </div>
          </div>
        </el-card>

        <el-card v-if="request.invoices?.length" class="chain-card">
          <template #header>发票记录</template>
          <el-table :data="request.invoices" empty-text="暂无票据">
            <el-table-column label="票号" min-width="190">
              <template #default="{ row }">{{ row.invoiceNo || '详见 PDF' }}</template>
            </el-table-column>
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
                    ['valid', 'pdf_uploaded', 'partially_red'].includes(
                      row.status
                    )
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
                  @click="openRedInvoice(row)"
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

        <div v-if="activeRedInvoice || activeFileInvoice" class="invoice-followups">
          <section v-if="activeRedInvoice" class="invoice-followup invoice-followup--primary">
            <header class="invoice-followup__header">
              <div>
                <h3>回传红票</h3>
                <p>
                  关联蓝票
                  <strong>{{ activeRedInvoice.invoiceNo || '详见 PDF' }}</strong>
                </p>
              </div>
              <span class="invoice-followup__context">
                剩余可红冲 ¥{{ money(redRemaining(activeRedInvoice)) }}
              </span>
            </header>

            <div class="invoice-red-form">
              <label class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>红票票号</span>
                <el-input
                  v-model="redForms[activeRedInvoice.id].invoiceNo"
                  placeholder="请输入红票票号"
                  maxlength="64"
                />
              </label>
              <label class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>开票时间</span>
                <el-input
                  v-model="redForms[activeRedInvoice.id].issuedAt"
                  type="datetime-local"
                  aria-label="开票时间"
                />
              </label>
              <label class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>本次红冲金额（元）</span>
                <el-input-number
                  :model-value="redAmountYuan(activeRedInvoice.id)"
                  :min="0.01"
                  :max="redRemaining(activeRedInvoice) / 100"
                  :step="0.01"
                  :precision="2"
                  controls-position="right"
                  @update:model-value="updateRedAmountYuan(activeRedInvoice.id, $event)"
                />
                <span class="invoice-form-field__hint">
                  最多可红冲 ¥{{ money(redRemaining(activeRedInvoice)) }}
                </span>
              </label>
              <label class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>红冲说明</span>
                <el-input
                  v-model="redForms[activeRedInvoice.id].reason"
                  placeholder="说明本次红冲原因"
                  maxlength="500"
                />
              </label>
            </div>

            <div class="invoice-pdf-field">
              <div class="invoice-form-field__label"><i>*</i>真实红票 PDF</div>
              <div class="invoice-pdf-picker">
                <span class="invoice-pdf-picker__icon" aria-hidden="true">
                  <el-icon><Document /></el-icon>
                </span>
                <span class="invoice-pdf-picker__copy">
                  <strong :title="redUploadStates[activeRedInvoice.id]?.file?.name">
                    {{ redUploadStates[activeRedInvoice.id]?.file?.name || '选择红票 PDF' }}
                  </strong>
                  <span v-if="uploadBusy" role="status">正在上传并校验…</span>
                  <span v-else-if="redForms[activeRedInvoice.id].fileId" class="is-success" role="status">
                    PDF 已上传并校验
                  </span>
                  <span v-else>PDF 格式，单个文件不超过 10 MB</span>
                </span>
                <label class="invoice-pdf-picker__button" :class="{ 'is-disabled': uploadBusy || command.pending.value }">
                  {{ redForms[activeRedInvoice.id].fileId ? '更换文件' : '选择文件' }}
                  <input
                    data-test="red-file"
                    type="file"
                    accept="application/pdf"
                    aria-label="选择真实红票 PDF"
                    :disabled="uploadBusy || command.pending.value"
                    @change="chooseRedFile(activeRedInvoice.id, $event)"
                  />
                </label>
              </div>
            </div>

            <div class="invoice-followup__actions">
              <el-button
                data-test="save-red"
                type="primary"
                :disabled="!redForms[activeRedInvoice.id].fileId || uploadBusy || command.pending.value"
                @click="recordRed(activeRedInvoice.id)"
              >保存实际红票</el-button>
            </div>
          </section>

          <section v-if="activeFileInvoice" class="invoice-followup invoice-followup--secondary">
            <header class="invoice-followup__header">
              <div>
                <h3>补交同一张票据文件</h3>
                <p>仅替换文件引用，不新增票号，也不重复确认发票金额或绩效消费。</p>
              </div>
            </header>
            <div class="invoice-replacement-form">
              <div class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>核验后的 PDF</span>
                <div class="invoice-pdf-picker invoice-pdf-picker--compact">
                  <span class="invoice-pdf-picker__icon" aria-hidden="true">
                    <el-icon><Document /></el-icon>
                  </span>
                  <span class="invoice-pdf-picker__copy">
                    <strong :title="replacementUploadState?.file?.name">
                      {{ replacementUploadState?.file?.name || '选择票据 PDF' }}
                    </strong>
                    <span v-if="uploadBusy" role="status">正在上传并校验…</span>
                    <span v-else-if="replacementFileId" class="is-success" role="status">
                      PDF 已上传并校验
                    </span>
                    <span v-else>PDF 格式，单个文件不超过 10 MB</span>
                  </span>
                  <label class="invoice-pdf-picker__button" :class="{ 'is-disabled': uploadBusy || command.pending.value }">
                    {{ replacementFileId ? '更换文件' : '选择文件' }}
                    <input
                      data-test="replacement-file"
                      type="file"
                      accept="application/pdf"
                      aria-label="选择替换票据 PDF"
                      :disabled="uploadBusy || command.pending.value"
                      @change="chooseReplacementFile(activeFileInvoice.id, $event)"
                    />
                  </label>
                </div>
              </div>
              <label class="invoice-form-field">
                <span class="invoice-form-field__label"><i>*</i>替换原因</span>
                <el-input
                  v-model="replacementReason"
                  maxlength="500"
                  placeholder="说明原文件无法使用的原因"
                />
              </label>
            </div>
            <div class="invoice-followup__actions">
              <el-button
                data-test="replace-file"
                :disabled="!replacementFileId || !replacementReason.trim() || uploadBusy || command.pending.value"
                @click="replaceFile(activeFileInvoice.id)"
              >替换票据文件</el-button>
            </div>
          </section>
        </div>
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
    <el-dialog
      v-model="billingReleaseOpen"
      class="mall-management-overlay"
      title="确认查看本申请开票资料"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!billingReleaseBusy"
    >
      <p>
        仅查看当前开票申请办理所需的抬头及企业税号。后端会重新核验领取人、权限、订单付款/退款状态和用途同意；成功后资料只在本页临时显示 60 秒。
      </p>
      <template #footer>
        <el-button :disabled="billingReleaseBusy" @click="billingReleaseOpen = false">
          返回
        </el-button>
        <el-button
          data-test="confirm-billing-release"
          type="primary"
          :loading="billingReleaseBusy"
          @click="releaseBillingData"
        >
          确认并查看
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { Document } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-invoices'
import { commandKey, useMallCommand } from '@/composables/useMallCommand'
import { useExpiringSensitiveData } from '@/composables/useExpiringSensitiveData'
import { useMallToast } from '@/composables/useMallToast'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const billingReleaseUiEnabled =
  import.meta.env.VITE_MALL_DATA_RELEASE_UI_ENABLED === 'true'
const request = ref(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
const infoReason = ref('')
const issueForm = reactive({
  fileId: '',
  replacementForId: '',
})
const redForms = reactive({})
const replacementReason = ref('')
const replacementFileId = ref('')
const uploadBusy = ref(false)
const uploadError = ref('')
useMallToast(error)
useMallToast(notice, () => noticeType.value)
useMallToast(uploadError)
const fileBusy = ref('')
const activeRedInvoiceId = ref('')
const activeFileInvoiceId = ref('')
const blueUploadState = ref(null)
const redUploadStates = reactive({})
const replacementUploadState = ref(null)
const command = useMallCommand()
const billingData = useExpiringSensitiveData((data) => ({
  title: data.title,
  taxNo: data.taxNo,
  auditId: data.auditId,
}))
const billingReleased = billingData.value
const billingSecondsRemaining = billingData.secondsRemaining
const billingReleaseOpen = ref(false)
const billingReleaseBusy = ref(false)
let loadGeneration = 0

const requestStates = {
  submitted: '待处理',
  needs_info: '待买家补充',
  issuing: '财务办理中',
  unknown: '结果待核实',
  delivered: '已完成（发票已上传）',
  withdrawn: '已撤回',
  closed: '已关闭',
}
const invoiceStates = {
  valid: '已登记（经办人确认）',
  pdf_uploaded: 'PDF 已上传',
  red_pending: '待红冲',
  awaiting_counterparty: '待对方确认',
  partially_red: '部分红冲',
  fully_red: '已全额红冲',
}
const writer = computed(() => auth.hasPermission('mall.invoices.write'))
const reader = computed(() => auth.hasPermission('mall.invoices.read'))
const claimedByMe = computed(() => {
  const claimedBy = request.value?.claimedBy
  const currentAdmin = currentAdminId()
  return (
    claimedBy != null &&
    currentAdmin != null &&
    String(claimedBy) === currentAdmin
  )
})
const canReleaseBilling = computed(
  () =>
    auth.hasPermission('mall.billing.release') &&
    request.value?.status === 'issuing' &&
    claimedByMe.value
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
  const identity = auth.user?.userId
  return identity == null ? null : String(identity)
}
function canUploadForRequest() {
  return (
    !!request.value &&
    writer.value &&
    request.value.claimedBy != null &&
    String(request.value.claimedBy) === currentAdminId()
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
function openRedInvoice(invoice) {
  ensureRedForm(invoice)
  activeRedInvoiceId.value = invoice.id
}
function redAmountYuan(invoiceId) {
  return Number(redForms[invoiceId]?.totalCent || 0) / 100
}
function updateRedAmountYuan(invoiceId, value) {
  const amount = Number(value)
  redForms[invoiceId].totalCent = Number.isFinite(amount)
    ? Math.round(amount * 100)
    : 0
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
    fileId: '',
    replacementForId: invoice.id,
  })
}

async function load() {
  if (command.pending.value) return
  billingData.clear()
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
        result.claimedBy != null &&
        String(result.claimedBy) === currentAdminId()
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
    '已开始处理该申请。'
  )
}
async function releaseBillingData() {
  if (
    !billingReleaseUiEnabled ||
    !canReleaseBilling.value ||
    billingReleaseBusy.value
  )
    return
  const identity = props.id
  const generation = billingData.beginRequest()
  billingReleaseBusy.value = true
  error.value = ''
  try {
    const result = await api.releaseMallBilling(
      {
        id: identity,
        expectedVersion: request.value.version,
        purpose: 'invoice_issue',
        reason: '办理当前领取的开票申请',
      },
      commandKey()
    )
    if (
      billingData.isCurrent(generation) &&
      props.id === identity &&
      document.visibilityState !== 'hidden'
    ) {
      if (!billingData.show(result, generation)) {
        error.value = '资料响应已过期或无效，请重新核实申请后再试。'
      } else {
        billingReleaseOpen.value = false
      }
    }
  } catch {
    if (billingData.isCurrent(generation)) {
      error.value = '暂无法读取本申请资料，请核实领取人、权限、订单状态和用途告知配置。'
    }
  } finally {
    billingReleaseBusy.value = false
  }
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
  const result = await command.run(api.recordMallInvoice, {
    id: props.id,
    expectedVersion: request.value.version,
    totalCent: issueAmountCent.value,
    fileId: issueForm.fileId,
    ...(issueForm.replacementForId
      ? { replacementForId: issueForm.replacementForId }
      : {}),
  })
  await afterCommand(
    result,
    issueForm.replacementForId
      ? '替代发票 PDF 已登记，用户可在申请中下载。'
      : '发票 PDF 已登记，用户可在申请中下载。'
  )
  if (result)
    Object.assign(issueForm, {
      fileId: '',
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

function guardSensitiveNavigation() {
  billingData.clear()
  billingReleaseOpen.value = false
  if (billingReleaseBusy.value) {
    error.value = '安全读取正在完成，请稍后离开本页'
    return false
  }
  return true
}
function onVisibilityChange() {
  if (document.visibilityState === 'hidden') billingReleaseOpen.value = false
}
onBeforeRouteLeave(guardSensitiveNavigation)
onBeforeRouteUpdate(guardSensitiveNavigation)
watch(
  () => props.id,
  () => {
    billingData.clear()
    billingReleaseOpen.value = false
    load()
  }
)
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  load()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  billingData.clear()
})
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
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(150px, 1fr));
  gap: 14px 24px;
  margin: 0;
}
.facts dt {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.facts dd {
  margin: 5px 0 0;
  font-weight: 600;
}
.action-card,
.chain-card,
.sub-action {
  margin-top: 16px;
}
.info-request-form {
  display: grid;
  justify-items: start;
  gap: 12px;
}
.released-fields {
  display: grid;
  gap: 8px;
  margin: 0 0 12px;
}
.released-fields div {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 12px;
}
.released-fields dt {
  color: var(--el-text-color-secondary);
}
.released-fields dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 12px;
}
.invoice-followups {
  margin-top: 20px;
  border-top: 1px solid var(--app-border-color);
}
.invoice-followup {
  min-width: 0;
  padding: 20px 4px;
}
.invoice-followup__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.invoice-followup__header h3 {
  margin: 0;
  padding-left: 12px;
  border-left: 4px solid var(--el-color-primary);
  color: var(--app-text-primary);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}
.invoice-followup__header p {
  margin: 0;
  padding-left: 16px;
  border-left: 1px solid var(--app-border-color);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
.invoice-followup__header strong {
  color: var(--el-color-primary);
  font-weight: 600;
}
.invoice-followup__context {
  flex: 0 0 auto;
  padding-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  white-space: nowrap;
}
.invoice-red-form,
.invoice-replacement-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 28px;
  row-gap: 16px;
}
.invoice-form-field {
  display: grid;
  grid-template-columns: minmax(112px, 150px) minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: center;
  column-gap: 12px;
  row-gap: 5px;
  min-width: 0;
  color: var(--app-text-regular);
  font-size: 13px;
}
.invoice-form-field__label {
  grid-column: 1;
  grid-row: 1;
  color: var(--app-text-regular);
  font-size: 13px;
  line-height: 1.4;
}
.invoice-form-field > :deep(.el-input),
.invoice-form-field > :deep(.el-input-number),
.invoice-form-field > .invoice-pdf-picker {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
}
.invoice-form-field > .invoice-pdf-picker {
  width: 100%;
}
.invoice-form-field__label i {
  margin-right: 3px;
  color: var(--el-color-danger);
  font-style: normal;
}
.invoice-form-field__hint {
  grid-column: 2;
  grid-row: 2;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}
.invoice-form-field :deep(.el-input-number) {
  width: 100%;
}
.invoice-pdf-field {
  display: grid;
  grid-template-columns: minmax(112px, 150px) minmax(0, 1fr);
  align-items: start;
  column-gap: 12px;
  margin-top: 20px;
}
.invoice-pdf-field > .invoice-form-field__label {
  padding-top: 10px;
}
.invoice-pdf-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  min-height: 68px;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--app-radius-md);
  background: #fafbfd;
}
.invoice-pdf-picker__icon {
  display: grid;
  flex: 0 0 40px;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--app-radius-sm);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 20px;
}
.invoice-pdf-picker__copy {
  display: grid;
  flex: 1 1 auto;
  min-width: 0;
  gap: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}
.invoice-pdf-picker__copy strong {
  overflow: hidden;
  color: var(--app-text-primary);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.invoice-pdf-picker__copy .is-success {
  color: var(--el-color-success);
}
.invoice-pdf-picker__button {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 13px;
  border: 1px solid var(--app-border-color);
  border-radius: var(--app-radius-sm);
  background: var(--el-bg-color);
  color: var(--app-text-regular);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: border-color var(--app-dur-fast) var(--app-ease), color var(--app-dur-fast) var(--app-ease);
}
.invoice-pdf-picker__button:hover {
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}
.invoice-pdf-picker__button.is-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.invoice-pdf-picker__button input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}
.invoice-followup__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.invoice-followup--secondary {
  border-top: 1px solid var(--app-border-color);
}
.invoice-followup--secondary .invoice-followup__header {
  margin-bottom: 14px;
}
.invoice-followup--secondary .invoice-pdf-picker {
  margin-top: 0;
}
.invoice-pdf-picker--compact {
  min-height: 48px;
  padding: 6px 8px;
  border-style: solid;
  border-color: var(--app-border-color);
  background: var(--el-bg-color);
}
.invoice-pdf-picker--compact .invoice-pdf-picker__icon {
  flex-basis: 32px;
  width: 32px;
  height: 32px;
  font-size: 17px;
}
.invoice-followup--secondary .invoice-followup__actions {
  margin-top: 12px;
}
.invoice-upload {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.invoice-upload__file {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  flex: 0 1 620px;
  max-width: 100%;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}
.invoice-upload__icon {
  display: grid;
  place-items: center;
  flex: 0 0 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 21px;
}
.invoice-upload__copy {
  display: grid;
  flex: 1 1 130px;
  min-width: 0;
  gap: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.invoice-upload__copy strong {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.invoice-upload__verified { color: var(--el-color-success); }
.invoice-upload__picker {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  cursor: pointer;
}
.invoice-upload__picker:focus-within {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.invoice-upload__picker.is-disabled { opacity: 0.55; cursor: not-allowed; }
.invoice-upload__picker input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}
.invoice-upload__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 8px;
}
.invoice-upload__actions :deep(.el-button + .el-button) { margin-left: 0; }
.file-label {
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 14px 10px 0;
}
.file-state {
  color: var(--el-color-success);
  margin-right: 12px;
}
.reason {
  display: block;
  max-width: 640px;
  margin: 12px 0;
}
@media (max-width: 800px) {
  .facts,
  .form-grid,
  .invoice-red-form,
  .invoice-replacement-form {
    grid-template-columns: 1fr;
  }
  .invoice-followup__context {
    white-space: normal;
    text-align: right;
  }
}
@media (max-width: 560px) {
  .invoice-followup__header {
    flex-direction: column;
    gap: 8px;
  }
  .invoice-followup__context {
    text-align: left;
  }
  .invoice-pdf-picker {
    flex-wrap: wrap;
  }
  .invoice-form-field,
  .invoice-pdf-field {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 7px;
  }
  .invoice-form-field__label,
  .invoice-form-field > :deep(.el-input),
  .invoice-form-field > :deep(.el-input-number),
  .invoice-form-field > .invoice-pdf-picker,
  .invoice-form-field__hint,
  .invoice-pdf-field > .invoice-form-field__label {
    grid-column: 1;
    grid-row: auto;
  }
  .invoice-pdf-field > .invoice-form-field__label {
    padding-top: 0;
  }
  .invoice-form-field__hint {
    margin-top: -3px;
  }
  .invoice-pdf-picker__button {
    margin-left: 52px;
  }
  .invoice-followup__actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
