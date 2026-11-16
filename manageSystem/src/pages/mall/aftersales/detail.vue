<template>
  <section class="mall-page mall-management-page">
    <header class="page-header">
      <div>
        <el-button link type="primary" @click="router.push('/mall/aftersales')">
          返回售后列表
        </el-button>
        <h2 class="page-title">售后详情</h2>
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
      <template v-if="aftersale">
        <el-card>
          <template #header>
            <div class="card-heading">
              <strong>{{ aftersale.aftersaleNo }}</strong>
              <el-tag>
                {{
                  aftersaleStates[aftersale.status] || '待核实'
                }}
              </el-tag>
            </div>
          </template>
          <dl class="facts">
            <div>
              <dt>关联订单</dt>
              <dd>{{ aftersale.orderId }}</dd>
            </div>
            <div>
              <dt>申请方式</dt>
              <dd>{{ aftersaleMethods[aftersale.method] || '待核实' }}</dd>
            </div>
            <div>
              <dt>商品退款</dt>
              <dd>¥{{ money(aftersale.goodsRefundCent) }}</dd>
            </div>
            <div>
              <dt>运费退款</dt>
              <dd>¥{{ money(aftersale.freightRefundCent) }}</dd>
            </div>
            <div>
              <dt>售后版本</dt>
              <dd>{{ aftersale.version }}</dd>
            </div>
            <div>
              <dt>关联退款</dt>
              <dd>{{ aftersale.refundId || '尚未生成' }}</dd>
            </div>
            <div v-if="aftersale.returnCompany">
              <dt>退货快递公司</dt>
              <dd>{{ courierName(aftersale.returnCompany) }}</dd>
            </div>
            <div v-if="aftersale.returnTrackingNo">
              <dt>退货运单</dt>
              <dd>{{ aftersale.returnTrackingNo }}</dd>
            </div>
            <div v-if="aftersale.receiptResult">
              <dt>验收结果</dt>
              <dd>{{ aftersale.receiptResult }}</dd>
            </div>
            <div v-if="refund">
              <dt>渠道退款状态</dt>
              <dd>{{ refundStates[refund.status] || '待核实' }}</dd>
            </div>
          </dl>
          <p><strong>申请原因：</strong>{{ aftersale.reason || '—' }}</p>
          <p v-if="aftersale.auditReason">
            <strong>处理说明：</strong>{{ aftersale.auditReason }}
          </p>
          <section v-if="aftersale.proofFileIds?.length" class="proofs">
            <strong>申请凭证</strong>
            <div class="proof-gallery">
              <div
                v-for="fileId in aftersale.proofFileIds"
                :key="fileId"
                class="proof-item"
              >
                <button
                  type="button"
                  class="proof-thumb-button"
                  :disabled="
                    !canReadProofs ||
                      proofBusy === fileId ||
                      proofPreviewLoading[fileId] ||
                      !proofPreviewUrls[fileId]
                  "
                  @click="openProof(fileId)"
                >
                  <img
                    v-if="proofPreviewUrls[fileId]"
                    :src="proofPreviewUrls[fileId]"
                    :alt="`售后凭证 ${fileId}`"
                    class="proof-thumb"
                    @error="handleProofImageError(fileId)"
                  />
                  <span v-else class="proof-placeholder">
                    {{
                      proofPreviewLoading[fileId]
                        ? '图片加载中'
                        : proofPreviewErrors[fileId] || `凭证 ${fileId}`
                    }}
                  </span>
                </button>
                <div class="proof-item-actions">
                  <span>凭证 {{ fileId }}</span>
                  <el-button
                    link
                    size="small"
                    :disabled="!canReadProofs || proofBusy === fileId"
                    :loading="proofBusy === fileId"
                    @click="openProof(fileId)"
                  >
                    查看原图
                  </el-button>
                  <el-button
                    v-if="proofPreviewErrors[fileId]"
                    link
                    size="small"
                    :disabled="!canReadProofs || proofPreviewLoading[fileId]"
                    :loading="proofPreviewLoading[fileId]"
                    @click="loadProofPreview(fileId)"
                  >
                    重试
                  </el-button>
                </div>
              </div>
            </div>
            <small v-if="!canReadProofs">凭证访问需要售后读取与商城文件读取权限。</small>
          </section>
        </el-card>

        <el-card class="lines-card">
          <template #header>申请商品明细</template>
          <el-table
            :data="aftersale.items"
            empty-text="仅运费申请，没有商品明细"
          >
            <el-table-column prop="orderItemId" label="订单明细ID" />
            <el-table-column prop="quantity" label="申请数量" width="110" />
            <el-table-column label="商品退款" width="130">
              <template #default="{ row }">
                ¥{{ money(row.goodsRefundCent) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="sellableReceivedQuantity"
              label="可售验收数量"
              width="140"
            />
          </el-table>
        </el-card>

        <ReturnLogistics
          v-if="aftersale.returnTrackingNo"
          :aftersale-id="aftersale.id"
        />

        <el-card
          v-if="aftersale.status === 'submitted' && canReview"
          class="action-card"
        >
          <template #header>审核售后</template>
          <p v-if="aftersale.method === 'refund_only'">
            同意后系统会自动发起退款。
          </p>
          <p v-else>
            退货退款需等买家寄回商品并完成验收后再处理退款。
          </p>
          <el-alert
            v-if="aftersale.method === 'refund_only' && !canExecuteRefund"
            title="当前账号没有发起退款的权限，请联系管理员。"
            type="warning"
            :closable="false"
          />
          <el-input
            v-model="reviewReason"
            data-test="review-reason"
            type="textarea"
            maxlength="500"
            show-word-limit
            placeholder="填写审核说明（必填）"
            :disabled="command.pending.value"
          />
          <div class="actions">
            <el-button
              data-test="reject"
              type="danger"
              plain
              :disabled="command.pending.value"
              :loading="reviewDecision === 'reject' && command.busy.value"
              @click="decide('reject')"
            >
              拒绝申请
            </el-button>
            <el-button
              data-test="approve"
              type="primary"
              :disabled="
                command.pending.value ||
                  (aftersale.method === 'refund_only' && !canExecuteRefund)
              "
              :loading="reviewDecision === 'approve' && command.busy.value"
              @click="decide('approve')"
            >
              {{
                aftersale.method === 'refund_only'
                  ? '同意并发起退款'
                  : '同意退货申请'
              }}
            </el-button>
          </div>
        </el-card>

        <el-card
          v-if="aftersale.status === 'awaiting_receipt' && canReceive"
          class="action-card"
        >
          <template #header>退货验收</template>
          <p>
            只有逐件检查为可再次销售的商品才会增加可售库存；验收结果与退款到账分开。
          </p>
          <el-form label-position="top" :disabled="command.pending.value">
            <el-form-item label="验收结果">
              <el-select
                v-model="receiptForm.result"
                data-test="receipt-result"
              >
                <el-option label="全部合格" value="accepted" />
                <el-option label="部分合格" value="partially_accepted" />
                <el-option label="存在争议" value="disputed" />
              </el-select>
            </el-form-item>
            <div v-if="receiptForm.result !== 'disputed'" class="receipt-lines">
              <div
                v-for="line in aftersale.items"
                :key="line.id"
                class="receipt-line"
              >
                <span>明细 {{ line.orderItemId }}，退回
                  {{ line.quantity }} 件</span>
                <el-input-number
                  v-model="sellable[line.id]"
                  :min="0"
                  :max="line.quantity"
                  :disabled="
                    receiptForm.result === 'accepted' || command.pending.value
                  "
                />
              </div>
            </div>
            <el-form-item label="验收说明">
              <el-input
                v-model="receiptForm.reason"
                maxlength="500"
                placeholder="填写商品状态及可售判断"
              />
            </el-form-item>
            <el-button
              data-test="receive-return"
              type="primary"
              :disabled="command.pending.value"
              @click="receiveReturn"
            >
              保存验收结果
            </el-button>
          </el-form>
        </el-card>

        <el-card
          v-if="
            aftersale.status === 'awaiting_refund' &&
              !aftersale.refundId &&
              canExecuteRefund
          "
          class="action-card"
        >
          <template #header>发起退款</template>
          <p>
            审核已通过。点击后系统会按原支付方式提交退款，到账后订单状态会更新。
          </p>
          <el-button
            data-test="execute-refund"
            type="primary"
            :disabled="command.pending.value"
            @click="executeRefund"
          >
            发起退款
          </el-button>
        </el-card>
        <el-alert
          v-if="
            aftersale.status === 'refunding' &&
              !['unknown', 'abnormal', 'succeeded'].includes(refund?.status)
          "
          class="status-alert"
          title="退款已发起，正在等待支付渠道处理；到账后状态会更新。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="aftersale.status === 'awaiting_refund' && aftersale.refundId"
          class="status-alert"
          title="已有退款请求，请稍后查看结果，不要重复发起。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="aftersale.status === 'disputed'"
          class="status-alert"
          title="此售后需要管理员核实后才能继续。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'unknown'"
          class="status-alert"
          title="退款结果暂时无法确认，请联系管理员核对后再处理。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'abnormal'"
          class="status-alert"
          title="退款处理遇到异常，请联系管理员核实。"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'succeeded'"
          class="status-alert"
          title="退款已成功。"
          type="success"
          :closable="false"
        />
        <el-alert
          v-if="refund?.channelRefundId?.startsWith('LOCAL-SIM-')"
          class="status-alert"
          title="本地模拟退款已完成，没有发生真实资金变动。"
          type="warning"
          :closable="false"
        />
      </template>
      <el-empty v-else-if="!loading && !error" description="售后记录暂不可用" />
    </div>
    <el-dialog
      v-model="proofDialogVisible"
      title="申请凭证预览"
      width="min(900px, 90vw)"
      append-to-body
      @closed="closeProofPreview"
    >
      <el-alert
        v-if="proofDialogError"
        :title="proofDialogError"
        type="error"
        :closable="false"
      />
      <img
        v-else-if="proofDialogUrl"
        :src="proofDialogUrl"
        alt="售后申请凭证原图"
        class="proof-full-image"
        @error="proofDialogError = '图片加载失败，请关闭预览后重试'"
      />
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-aftersales'
import { useMallCommand } from '@/composables/useMallCommand'
import { useMallToast } from '@/composables/useMallToast'
import { aftersaleMethods, aftersaleStates, money } from './aftersale-view'
import ReturnLogistics from './ReturnLogistics.vue'
import { courierName } from '../orders/couriers'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const aftersale = ref(null)
const refund = ref(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
useMallToast(error)
useMallToast(notice, () => noticeType.value)
const reviewReason = ref('')
const reviewDecision = ref('')
const proofBusy = ref('')
const proofPreviewUrls = reactive({})
const proofPreviewErrors = reactive({})
const proofPreviewLoading = reactive({})
const proofDialogVisible = ref(false)
const proofDialogUrl = ref('')
const proofDialogError = ref('')
const receiptForm = reactive({ result: 'accepted', reason: '' })
const sellable = reactive({})
const command = useMallCommand()
let operation = null
let pendingReviewDecision = ''
let loadGeneration = 0

const canReview = computed(() => auth.hasPermission('mall.aftersales.review'))
const canReceive = computed(() => auth.hasPermission('mall.returns.receive'))
const canExecuteRefund = computed(() =>
  auth.hasPermission('mall.refunds.execute')
)
const canReadProofs = computed(
  () =>
    auth.hasPermission('mall.aftersales.read') &&
    auth.hasPermission('mall.files.read')
)
const refundStates = {
  prepared: '等待提交',
  processing: '退款处理中',
  unknown: '状态待确认',
  succeeded: '退款成功',
  closed: '已关闭',
  abnormal: '处理异常',
  rejected_unaccepted: '渠道未受理',
}

async function load() {
  if (command.pending.value) return
  const generation = ++loadGeneration
  const identity = props.id
  loading.value = true
  error.value = ''
  aftersale.value = null
  refund.value = null
  clearProofPreviews()
  proofDialogVisible.value = false
  proofDialogUrl.value = ''
  proofDialogError.value = ''
  try {
    const result = await api.getAdminAftersale(identity)
    if (generation === loadGeneration && props.id === identity) {
      aftersale.value = result
      void loadProofPreviews(identity, result.proofFileIds || [])
      if (result.refundId && auth.hasPermission('mall.refunds.read')) {
        try {
          const refundResult = await api.getAdminMallRefund(result.refundId)
          if (generation === loadGeneration && props.id === identity) {
            refund.value = refundResult
          }
        } catch (failure) {
          if (generation === loadGeneration && props.id === identity) {
            error.value =
              failure.userMessage || failure.message || '退款状态读取失败'
          }
        }
      }
    }
  } catch (failure) {
    if (generation === loadGeneration) {
      error.value = failure.userMessage || failure.message || '售后详情读取失败'
    }
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function finishOperation(result) {
  if (!result) return null
  if (operation === 'refund') {
    notice.value = '已发起退款，正在等待支付渠道处理；到账后状态会更新。'
    noticeType.value = 'warning'
  } else {
    notice.value = '退货验收结果已保存，库存只按可售数量回补。'
    noticeType.value = 'success'
  }
  return load()
}

async function finishReview(result, decision) {
  if (!result) return null
  if (decision === 'approve' && result.status === 'awaiting_refund') {
    if (!canExecuteRefund.value) {
      notice.value = '申请已同意，但当前账号没有发起退款的权限，请联系管理员。'
      noticeType.value = 'warning'
      return load()
    }
    operation = 'refund'
    const refundResult = await command.run(api.executeAftersaleRefund, {
      id: props.id,
      expectedVersion: result.version,
    })
    if (refundResult) return finishOperation(refundResult)
    if (!command.pending.value) await load()
    return null
  }
  notice.value = '审核结果已保存。'
  noticeType.value = 'success'
  return load()
}

function notifyError(message) {
  // Repeated validation failures need to produce feedback each time.
  error.value = ''
  error.value = message
}

async function decide(decision) {
  if (!aftersale.value || !canReview.value || command.pending.value) return
  if (
    decision === 'approve' &&
    aftersale.value.method === 'refund_only' &&
    !canExecuteRefund.value
  ) {
    notifyError('当前账号没有发起退款的权限，请联系管理员')
    return
  }
  const reason = reviewReason.value.trim()
  if (!reason) {
    notifyError('请填写审核说明')
    return
  }
  operation = 'review'
  pendingReviewDecision = decision
  reviewDecision.value = decision
  try {
    const result = await command.run(api.decideAftersale, {
      id: props.id,
      expectedVersion: aftersale.value.version,
      decision,
      reason,
    })
    if (result) {
      await finishReview(result, decision)
      pendingReviewDecision = ''
    } else if (!command.pending.value) {
      pendingReviewDecision = ''
    }
  } finally {
    reviewDecision.value = ''
  }
}

async function receiveReturn() {
  if (!aftersale.value || !canReceive.value || command.pending.value) return
  const reason = receiptForm.reason.trim()
  if (!reason) {
    error.value = '请填写验收说明'
    return
  }
  const sellableItems =
    receiptForm.result === 'disputed'
      ? []
      : aftersale.value.items
          .map((line) => ({
            aftersaleItemId: line.id,
            quantity:
              receiptForm.result === 'accepted'
                ? line.quantity
                : Math.max(
                    0,
                    Math.min(line.quantity, Number(sellable[line.id] || 0))
                  ),
          }))
          .filter((line) => line.quantity > 0)
  operation = 'receipt'
  const result = await command.run(api.receiveAftersaleReturn, {
    id: props.id,
    expectedVersion: aftersale.value.version,
    result: receiptForm.result,
    sellableItems,
    reason,
  })
  await finishOperation(result)
}

async function executeRefund() {
  if (
    !aftersale.value ||
    !canExecuteRefund.value ||
    aftersale.value.status !== 'awaiting_refund' ||
    aftersale.value.refundId ||
    command.pending.value
  ) {
    return
  }
  operation = 'refund'
  const result = await command.run(api.executeAftersaleRefund, {
    id: props.id,
    expectedVersion: aftersale.value.version,
  })
  await finishOperation(result)
}

async function retry() {
  const retryingOperation = operation
  const result = await command.retry()
  if (!result) {
    if (!command.pending.value && retryingOperation === 'review') {
      pendingReviewDecision = ''
    }
    return null
  }
  if (retryingOperation === 'review') {
    const decision = pendingReviewDecision
    pendingReviewDecision = ''
    return finishReview(result, decision)
  }
  return finishOperation(result)
}

function clearProofPreviews() {
  for (const map of [
    proofPreviewUrls,
    proofPreviewErrors,
    proofPreviewLoading,
  ]) {
    Object.keys(map).forEach((key) => delete map[key])
  }
}

async function loadProofPreviews(identity, fileIds) {
  if (!canReadProofs.value) return
  await Promise.all(
    fileIds.map((fileId) => loadProofPreview(fileId, identity))
  )
}

async function loadProofPreview(fileId, identity = props.id) {
  if (!canReadProofs.value || proofPreviewLoading[fileId]) return
  proofPreviewLoading[fileId] = true
  delete proofPreviewErrors[fileId]
  try {
    const result = await api.getAftersaleProofAccess(fileId)
    if (
      props.id !== identity ||
      !aftersale.value?.proofFileIds?.includes(fileId)
    ) {
      return
    }
    const target = new URL(result.accessUrl)
    if (target.protocol !== 'https:') throw new Error('凭证访问地址不安全')
    proofPreviewUrls[fileId] = target.href
  } catch (failure) {
    if (
      props.id === identity &&
      aftersale.value?.proofFileIds?.includes(fileId)
    ) {
      proofPreviewErrors[fileId] =
        failure.userMessage || failure.message || '图片暂不可访问'
    }
  } finally {
    if (props.id === identity) delete proofPreviewLoading[fileId]
  }
}

function handleProofImageError(fileId) {
  delete proofPreviewUrls[fileId]
  proofPreviewErrors[fileId] = '图片加载失败，点击重试'
}

function closeProofPreview() {
  proofDialogUrl.value = ''
  proofDialogError.value = ''
}

async function openProof(fileId) {
  if (!canReadProofs.value || proofBusy.value) return
  const identity = props.id
  proofBusy.value = fileId
  error.value = ''
  proofDialogUrl.value = ''
  proofDialogError.value = ''
  try {
    const result = await api.getAftersaleProofAccess(fileId)
    if (
      props.id !== identity ||
      !aftersale.value?.proofFileIds?.includes(fileId)
    ) {
      return
    }
    const target = new URL(result.accessUrl)
    if (target.protocol !== 'https:') throw new Error('凭证访问地址不安全')
    proofDialogUrl.value = target.href
    proofDialogVisible.value = true
  } catch (failure) {
    if (props.id === identity) {
      error.value = failure.userMessage || failure.message || '凭证暂不可访问'
    }
  } finally {
    proofBusy.value = ''
  }
}

function guard() {
  if (command.pending.value) {
    error.value = '操作结果待确认，请先重试原操作'
    return false
  }
  return true
}

onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
watch(
  () => props.id,
  () => {
    notice.value = ''
    reviewReason.value = ''
    pendingReviewDecision = ''
    receiptForm.result = 'accepted'
    receiptForm.reason = ''
    Object.keys(sellable).forEach((key) => delete sellable[key])
    load()
  }
)
onMounted(load)
</script>

<style scoped>
.card-heading,
.actions,
.receipt-line {
  display: flex;
  align-items: center;
  gap: 12px;
}
.card-heading {
  justify-content: space-between;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin: 0 0 16px;
}
.facts div {
  min-width: 0;
}
.facts dt {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.facts dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}
.proofs,
.actions,
.receipt-lines {
  margin-top: 16px;
}
.proofs {
  display: grid;
  gap: 10px;
}
.proof-gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.proof-item {
  display: grid;
  justify-items: start;
  gap: 6px;
}
.proof-thumb-button {
  display: grid;
  place-items: center;
  width: 112px;
  height: 112px;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.proof-thumb-button:disabled {
  cursor: default;
}
.proof-thumb {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.proof-placeholder {
  padding: 8px;
  font-size: 12px;
  text-align: center;
  overflow-wrap: anywhere;
}
.proof-item-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.proof-full-image {
  display: block;
  max-width: 100%;
  max-height: 75vh;
  margin: 0 auto;
  object-fit: contain;
}
.proofs small {
  color: var(--el-text-color-secondary);
}
.lines-card,
.action-card {
  margin-top: 16px;
}
.action-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
.action-card :deep(.el-card__body > p) {
  line-height: 1.6;
}
.action-card :deep(.el-card__body > .el-button) {
  align-self: flex-start;
}
.action-card :deep(.el-form) {
  display: grid;
  gap: 12px;
}
.action-card :deep(.el-form-item) {
  margin-bottom: 0;
}
.action-card :deep(.actions),
.action-card :deep(.receipt-lines) {
  margin-top: 0;
}
.action-card :deep(.el-form > .el-button) {
  justify-self: start;
}
.status-alert {
  margin: 16px 0;
}
.actions {
  justify-content: flex-end;
}
.receipt-line {
  justify-content: space-between;
  margin-bottom: 12px;
}
</style>
