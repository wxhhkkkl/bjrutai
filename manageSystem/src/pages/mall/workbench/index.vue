<template>
  <section class="mall-workbench">
    <header class="page-heading">
      <div>
        <p class="eyebrow">商城管理</p>
        <h2>商城工作台</h2>
        <p class="page-subtitle">只汇总当前账号可查看的待办和已确认资金事实。</p>
      </div>
      <div class="heading-actions">
        <el-button
          v-if="canReadSettings"
          data-test="open-trade-settings"
          @click="router.push('/mall/settings/trade')"
        >
          交易设置
        </el-button>
        <el-button
          data-test="workbench-reload"
          :loading="loading"
          @click="load"
        >
          刷新
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="error"
      data-test="workbench-error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button link type="primary" :disabled="loading" @click="load">
          重新加载
        </el-button>
      </template>
    </el-alert>

    <template v-if="summary">
      <section class="work-section" data-test="workbench-summary">
        <div class="section-heading">
          <div>
            <h3>待处理事项</h3>
            <p>按权限显示；没有对应列表权限时只展示获准的汇总数量。</p>
          </div>
          <el-tag type="info" effect="plain">{{ today }}</el-tag>
        </div>
        <el-empty
          v-if="!visibleTasks.length"
          description="当前账号没有可显示的商城待办"
          :image-size="64"
        />
        <div v-else class="task-grid">
          <article
            v-for="task in visibleTasks"
            :key="task.key"
            class="task-card"
            :class="{ 'task-card--linked': task.route }"
            :data-test="`work-item-${task.key}`"
          >
            <div class="task-card__top">
              <span class="task-card__label">{{ task.label }}</span>
              <span class="task-card__dot" :class="{ 'task-card__dot--alert': Number(summary[task.key]) > 0 }" />
            </div>
            <strong class="task-card__value">{{ count(summary[task.key]) }}</strong>
            <p class="task-card__hint">{{ task.hint }}</p>
            <el-button
              v-if="task.route"
              :data-test="`work-link-${task.key}`"
              link
              type="primary"
              @click="router.push(task.route)"
            >
              查看处理
            </el-button>
            <span v-else class="task-card__scope">当前权限不含对应列表页</span>
          </article>
        </div>
      </section>

      <section v-if="visibleFunds.length" class="work-section">
        <div class="section-heading">
          <div>
            <h3>今日已确认资金</h3>
            <p>按北京时间自然日统计；待核实支付和退款不计入。</p>
          </div>
          <el-button
            v-if="canReadPayments"
            link
            type="primary"
            @click="router.push('/mall/payments')"
          >
            查看支付订单
          </el-button>
        </div>
        <div class="fund-grid">
          <article v-for="fund in visibleFunds" :key="fund.key" class="fund-card">
            <span>{{ fund.label }}</span>
            <strong>{{ money(summary[fund.key]) }}</strong>
            <small>{{ fund.caption }}</small>
          </article>
        </div>
      </section>
    </template>

    <el-skeleton v-else-if="loading" :rows="5" animated />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getMallWorkbench } from '@/api/mall-settings'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const summary = ref(null)
const today = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date())

const canReadSettings = computed(() => auth.hasPermission('mall.settings.read'))
const canReadPayments = computed(() => auth.hasPermission('mall.payments.read'))
const has = (...permissions) => permissions.some((permission) => auth.hasPermission(permission))

const taskDefinitions = [
  {
    key: 'pendingShipment',
    label: '待发货订单',
    hint: '已支付且等待登记发货',
    visible: () => has('mall.orders.read', 'mall.shipments.write'),
    link: () => auth.hasPermission('mall.orders.read'),
    route: '/mall/orders',
  },
  {
    key: 'pendingPlatformReport',
    label: '待登记微信平台发货',
    hint: '本地已出库，员工尚未确认微信后台人工录入',
    visible: () => auth.hasPermission('mall.shipments.write'),
    link: () => auth.hasPermission('mall.orders.read'),
    route: '/mall/orders?pendingPlatformReport=true',
  },
  {
    key: 'pendingAftersale',
    label: '待处理售后',
    hint: '新申请或进入争议处理的售后单',
    visible: () => has('mall.aftersales.read', 'mall.aftersales.review'),
    link: () => auth.hasPermission('mall.aftersales.read'),
    route: '/mall/aftersales',
  },
  {
    key: 'pendingReturnReceipt',
    label: '待验收退货',
    hint: '买家已寄回，等待登记验收结果',
    visible: () => has('mall.aftersales.read', 'mall.returns.receive'),
    link: () => auth.hasPermission('mall.aftersales.read'),
    route: '/mall/aftersales',
  },
  {
    key: 'paymentUnknown',
    label: '待核实支付',
    hint: '支付结果未知且已超过责任提醒时限',
    visible: () => has('mall.payments.read', 'mall.payments.query', 'mall.reconciliations.read'),
    link: () => auth.hasPermission('mall.payments.read'),
    route: '/mall/payments',
  },
  {
    key: 'refundAbnormal',
    label: '异常退款',
    hint: '退款异常或结果未知且已超时',
    visible: () => has('mall.refunds.read', 'mall.refunds.query', 'mall.refunds.execute', 'mall.reconciliations.read'),
    link: () => auth.hasPermission('mall.refunds.read'),
    route: '/mall/refunds',
  },
  {
    key: 'unassigned',
    label: '待核实消费归属',
    hint: '确认后才进入绩效归属基数',
    visible: () => auth.hasPermission('mall.attribution.write'),
    link: () => auth.hasPermission('contributions.read'),
    route: '/contributions',
  },
  {
    key: 'pendingAdjustment',
    label: '待审核绩效调整',
    hint: '提议中或需要人工处理的调整',
    visible: () => auth.hasPermission('performance.settle'),
    link: () => auth.hasPermission('performance.settle'),
    route: '/performance',
  },
  {
    key: 'pendingInvoice',
    label: '待办理发票',
    hint: '开票申请等待处理或补充资料',
    visible: () => has('mall.invoices.read', 'mall.invoices.write'),
    link: () => auth.hasPermission('mall.invoices.read'),
    route: '/mall/invoices',
  },
  {
    key: 'pendingRedInvoice',
    label: '待办理红冲',
    hint: '红字申请或对方确认等待处理',
    visible: () => has('mall.invoices.read', 'mall.invoices.write'),
    link: () => auth.hasPermission('mall.invoices.read'),
    route: '/mall/invoices',
  },
  {
    key: 'lowStock',
    label: '低库存规格',
    hint: '可售库存已达到商品预警线',
    visible: () => has('mall.stock.read', 'mall.stock.write'),
    link: () => auth.hasPermission('mall.products.read'),
    route: '/mall/products',
  },
]

const visibleTasks = computed(() => taskDefinitions
  .filter((task) => task.visible())
  .map((task) => ({ ...task, route: task.link() ? task.route : '' })))

const visibleFunds = computed(() => {
  const funds = []
  if (has('mall.payments.read', 'mall.payments.query', 'mall.reconciliations.read')) {
    funds.push({ key: 'paidTodayCent', label: '今日实收', caption: '成功支付金额' })
  }
  if (has('mall.refunds.read', 'mall.refunds.query', 'mall.refunds.execute', 'mall.reconciliations.read')) {
    funds.push({ key: 'refundedTodayCent', label: '今日退款', caption: '成功退款金额' })
  }
  return funds
})

function count(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '—'
}

function money(value) {
  const number = Number(value)
  return Number.isSafeInteger(number)
    ? `¥${(number / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : '—'
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  summary.value = null
  try {
    summary.value = await getMallWorkbench()
  } catch (failure) {
    error.value = failure.userMessage || failure.message || '商城工作台读取失败，请重试。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mall-workbench { display: grid; gap: 24px; max-width: 1440px; margin: 0 auto; }
.page-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.page-heading { padding: 4px 0 0; }
.eyebrow { margin: 0 0 6px; color: #688277; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2, h3, p { margin-top: 0; }
h2 { margin-bottom: 6px; color: #1d3028; font-size: 24px; }
h3 { margin-bottom: 4px; color: #20342b; font-size: 17px; }
.page-subtitle, .section-heading p { margin-bottom: 0; color: #718078; font-size: 13px; }
.heading-actions { display: flex; gap: 8px; }
.work-section { padding: 22px; border: 1px solid #e6ece8; border-radius: 14px; background: #fff; box-shadow: 0 6px 24px rgba(33, 57, 45, .035); }
.section-heading { margin-bottom: 20px; }
.task-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(205px, 1fr)); gap: 14px; }
.task-card { min-height: 162px; padding: 17px; border: 1px solid #e8eee9; border-radius: 12px; background: linear-gradient(155deg, #fff 0%, #fbfdfb 100%); }
.task-card--linked { transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease; }
.task-card--linked:hover { border-color: #b7d4c4; box-shadow: 0 8px 22px rgba(43, 92, 66, .09); transform: translateY(-2px); }
.task-card__top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.task-card__label { color: #56665d; font-size: 13px; font-weight: 600; }
.task-card__dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5cf; }
.task-card__dot--alert { background: #e59751; box-shadow: 0 0 0 4px #fff4e8; }
.task-card__value { display: block; margin: 14px 0 4px; color: #20342b; font-size: 30px; font-variant-numeric: tabular-nums; line-height: 1.1; }
.task-card__hint { min-height: 32px; margin: 0 0 6px; color: #849088; font-size: 12px; line-height: 1.45; }
.task-card__scope { color: #a1aaa4; font-size: 12px; }
.fund-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.fund-card { display: grid; gap: 8px; padding: 18px 20px; border-radius: 12px; background: #f5f8f5; }
.fund-card span { color: #617168; font-size: 13px; }
.fund-card strong { color: #294d3b; font-size: 25px; font-variant-numeric: tabular-nums; }
.fund-card small { color: #8c9890; }
@media (max-width: 720px) { .page-heading, .section-heading { align-items: flex-start; flex-direction: column; } .work-section { padding: 16px; } .task-grid { grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); } }
</style>
