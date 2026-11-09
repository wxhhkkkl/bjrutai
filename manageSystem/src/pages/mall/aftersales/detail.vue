<template>
  <section class="mall-page">
    <header>
      <div>
        <el-button link @click="router.push('/mall/aftersales')">
          返回售后列表
        </el-button>
        <h2>售后详情</h2>
      </div>
      <el-button
        data-test="reload"
        :disabled="command.pending.value || loading"
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
            <el-button
              v-for="fileId in aftersale.proofFileIds"
              :key="fileId"
              link
              :disabled="!canReadProofs || proofBusy === fileId"
              :loading="proofBusy === fileId"
              @click="openProof(fileId)"
            >
              查看凭证 {{ fileId }}
            </el-button>
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

        <el-card
          v-if="aftersale.status === 'submitted' && canReview"
          class="action-card"
        >
          <template #header>审核售后</template>
          <el-input
            v-model="reviewReason"
            data-test="review-reason"
            type="textarea"
            maxlength="500"
            show-word-limit
            placeholder="记录审核结论或拒绝原因"
            :disabled="command.pending.value"
          />
          <div class="actions">
            <el-button
              data-test="reject"
              type="danger"
              plain
              :disabled="command.pending.value"
              @click="decide('reject')"
            >
              拒绝申请
            </el-button>
            <el-button
              data-test="approve"
              type="primary"
              :disabled="command.pending.value"
              @click="decide('approve')"
            >
              同意申请
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
          <template #header>原路退款</template>
          <p>
            退款会排入财务处理队列。队列受理不等于退款到账，只有核实到渠道成功结果才更新订单。
          </p>
          <el-button
            data-test="execute-refund"
            type="primary"
            :disabled="command.pending.value"
            @click="executeRefund"
          >
            发起原路退款
          </el-button>
        </el-card>
        <el-alert
          v-if="aftersale.status === 'refunding'"
          title="退款请求已进入核实流程，待确认渠道结果；当前状态不代表到账。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="aftersale.status === 'awaiting_refund' && aftersale.refundId"
          title="原退款请求已有记录，需在退款资金台账核实或按权限处理后再继续。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="aftersale.status === 'disputed'"
          title="此售后存在超期、验收或渠道异常，保留原占用并等待人工核实。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'unknown'"
          title="退款渠道结果未知，资金和商品数量占用保留。先查证原退款号；如重试，系统会先查原号并只复用该退款号。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'abnormal'"
          title="渠道返回退款异常，资金和商品数量占用保留。需人工核实，不能自动重试。"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="refund?.status === 'succeeded'"
          title="已核实渠道退款成功；该状态来自渠道成功事实，不来自退款受理。"
          type="success"
          :closable="false"
        />
        <el-card v-if="canQueryRefund" class="action-card">
          <template #header>退款渠道查证</template>
          <p>查证只读取原退款号，不会因查不到记录自动发起退款。</p>
          <el-button
            data-test="query-refund"
            :disabled="command.pending.value"
            @click="queueRefundQuery"
          >
            查证原退款号
          </el-button>
        </el-card>
        <el-card v-if="canRetryRefund" class="action-card">
          <template #header>恢复退款请求</template>
          <p>
            系统会先查询原退款号；确认渠道不存在后才用同一退款号重试，处理结果仍待核实。
          </p>
          <el-input
            v-model="retryReason"
            data-test="retry-refund-reason"
            maxlength="500"
            placeholder="填写本次恢复核实说明"
            :disabled="command.pending.value"
          />
          <el-button
            data-test="retry-refund"
            type="warning"
            :disabled="command.pending.value"
            @click="retryRefund"
          >
            同号恢复退款
          </el-button>
        </el-card>
      </template>
      <el-empty v-else-if="!loading && !error" description="售后记录暂不可用" />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import * as api from '@/api/mall-aftersales'
import { useMallCommand } from '@/composables/useMallCommand'
import { aftersaleMethods, aftersaleStates, money } from './aftersale-view'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const auth = useAuthStore()
const aftersale = ref(null)
const refund = ref(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
const reviewReason = ref('')
const retryReason = ref('')
const proofBusy = ref('')
const receiptForm = reactive({ result: 'accepted', reason: '' })
const sellable = reactive({})
const command = useMallCommand()
let operation = null
let loadGeneration = 0

const canReview = computed(() => auth.hasPermission('mall.aftersales.review'))
const canReceive = computed(() => auth.hasPermission('mall.returns.receive'))
const canExecuteRefund = computed(() =>
  auth.hasPermission('mall.refunds.execute')
)
const canQueryRefund = computed(
  () => refund.value && auth.hasPermission('mall.refunds.query')
)
const canRetryRefund = computed(
  () =>
    refund.value &&
    ['prepared', 'unknown', 'processing'].includes(refund.value.status) &&
    canExecuteRefund.value
)
const canReadProofs = computed(
  () =>
    auth.hasPermission('mall.aftersales.read') &&
    auth.hasPermission('mall.files.read')
)
const refundStates = {
  prepared: '待处理',
  processing: '渠道处理中',
  unknown: '结果未知，待查证',
  succeeded: '已核实到账',
  closed: '渠道已关闭，待人工确认',
  abnormal: '渠道异常，资金占用保留',
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
  try {
    const result = await api.getAdminAftersale(identity)
    if (generation === loadGeneration && props.id === identity) {
      aftersale.value = result
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
    notice.value = '退款执行已排队；等待渠道核实结果，当前不代表到账。'
    noticeType.value = 'warning'
  } else if (operation === 'refundQuery') {
    notice.value = '渠道查证已排入队列；请刷新状态，队列受理不代表渠道成功。'
    noticeType.value = 'warning'
  } else if (operation === 'refundRetry') {
    notice.value =
      '同一商户退款号的恢复操作已排队；系统会先查原请求再判断是否重试。'
    noticeType.value = 'warning'
  } else if (operation === 'review') {
    notice.value = '审核结果已保存。'
    noticeType.value = 'success'
  } else {
    notice.value = '退货验收结果已保存，库存只按可售数量回补。'
    noticeType.value = 'success'
  }
  return load()
}

async function decide(decision) {
  if (!aftersale.value || !canReview.value || command.pending.value) return
  const reason = reviewReason.value.trim()
  if (!reason) {
    error.value = '请填写审核说明'
    return
  }
  operation = 'review'
  const result = await command.run(api.decideAftersale, {
    id: props.id,
    expectedVersion: aftersale.value.version,
    decision,
    reason,
  })
  await finishOperation(result)
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

async function queueRefundQuery() {
  if (!refund.value || !canQueryRefund.value || command.pending.value) return
  operation = 'refundQuery'
  await finishOperation(
    await command.run(api.queryAdminMallRefund, {
      id: refund.value.id,
      expectedVersion: refund.value.version,
    })
  )
}

async function retryRefund() {
  if (!refund.value || !canRetryRefund.value || command.pending.value) return
  const reason = retryReason.value.trim()
  if (!reason) {
    error.value = '请填写退款恢复核实说明'
    return
  }
  operation = 'refundRetry'
  await finishOperation(
    await command.run(api.retryAdminMallRefund, {
      id: refund.value.id,
      expectedVersion: refund.value.version,
      reason,
    })
  )
}

async function retry() {
  await finishOperation(await command.retry())
}

async function openProof(fileId) {
  if (!canReadProofs.value || proofBusy.value) return
  const identity = props.id
  proofBusy.value = fileId
  error.value = ''
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
    window.open(target.href, '_blank', 'noopener,noreferrer')
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
    retryReason.value = ''
    receiptForm.result = 'accepted'
    receiptForm.reason = ''
    Object.keys(sellable).forEach((key) => delete sellable[key])
    load()
  }
)
onMounted(load)
</script>

<style scoped>
.mall-page {
  padding: 20px;
}
header,
.card-heading,
.actions,
.receipt-line {
  display: flex;
  align-items: center;
  gap: 12px;
}
header,
.card-heading {
  justify-content: space-between;
}
header {
  margin-bottom: 16px;
}
header h2 {
  margin: 8px 0 0;
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
  color: #909399;
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
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.proofs small {
  color: #909399;
}
.lines-card,
.action-card {
  margin-top: 16px;
}
.actions {
  justify-content: flex-end;
}
.receipt-line {
  justify-content: space-between;
  margin-bottom: 12px;
}
</style>
