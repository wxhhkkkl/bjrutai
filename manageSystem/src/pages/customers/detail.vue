<template>
  <div class="page-container">
    <div class="page-header">
      <el-button text @click="$router.push('/customers')">
        <el-icon><ArrowLeft /></el-icon> 返回列表
      </el-button>
      <h2 class="page-title">客户详情</h2>
    </div>

    <el-card v-loading="loading" shadow="never" class="detail-card">
      <el-tabs v-model="activeTab">
        <!-- Profile tab -->
        <el-tab-pane label="基本信息" name="profile">
          <el-form :model="form" label-width="100px" size="small" v-if="customer">
            <el-form-item label="姓名">
              <el-input v-model="form.name" placeholder="客户姓名" :disabled="!editing" />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="form.phone" placeholder="手机号" :disabled="!editing" />
            </el-form-item>
            <el-form-item label="身份证号">
              <el-input v-model="form.idCard" placeholder="身份证号（脱敏展示，修改需填写原因）" :disabled="!editing" maxlength="18" />
            </el-form-item>
            <el-form-item label="医保账户">
              <el-input v-model="form.medicalAccount" placeholder="医保账户（脱敏展示，修改需填写原因）" :disabled="!editing" maxlength="64" />
            </el-form-item>
            <el-form-item label="绑定状态">
              <el-tag :type="bindingStatusType(customer.bindingStatus)" size="small">
                {{ bindingStatusLabel(customer.bindingStatus) }}
              </el-tag>
              <span v-if="customer.boundAt" class="muted">绑定于 {{ formatTime(customer.boundAt) }}</span>
            </el-form-item>
            <el-form-item label="推广员">
              <span>{{ customer.promoterName || '-' }}</span>
              <el-button v-if="canWrite" link type="primary" size="small" style="margin-left: 8px;" @click="openTransfer">
                更改推广员
              </el-button>
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.note" type="textarea" :rows="2" :disabled="!editing" />
            </el-form-item>
            <el-form-item label="家人电话">
              <el-input v-model="form.familyPhone" :disabled="!editing" />
            </el-form-item>

            <el-form-item v-if="editing" label="修改原因">
              <el-input v-model="form.changeReason" placeholder="修改身份证/医保账户/手机号等敏感字段时必须填写" />
            </el-form-item>

            <div class="form-actions">
              <template v-if="!editing">
                <el-button v-if="canWrite" type="primary" size="small" @click="startEdit">编辑</el-button>
              </template>
              <template v-else>
                <el-button size="small" @click="cancelEdit">取消</el-button>
                <el-button type="primary" size="small" :loading="saving" @click="saveProfile">保存</el-button>
              </template>
            </div>
          </el-form>

          <el-descriptions v-if="customer" :column="2" border size="small" style="margin-top: 16px;">
            <el-descriptions-item label="服务次数">{{ customer.serviceCount ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="跟进次数">{{ customer.followupCount ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="所属组织">{{ customer.orgName || '-' }}</el-descriptions-item>
            <el-descriptions-item label="医院ID">{{ customer.rutaiUserId || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- 推广员变更记录 -->
        <el-tab-pane label="推广员变更" name="changeLogs">
          <el-timeline v-if="changeLogItems.length">
            <el-timeline-item
              v-for="log in changeLogItems"
              :key="log.id"
              :timestamp="formatTime(log.createdAt)"
              placement="top"
            >
              <p style="margin: 0;">
                <el-tag :type="log.operationType === 'created' ? 'info' : 'warning'" size="small">
                  {{ log.operationType === 'created' ? '建档' : '推广员变更' }}
                </el-tag>
                <span style="margin-left: 8px;">
                  <template v-if="log.operationType === 'created'">
                    初始推广员：{{ log.newPromoterName || '-' }}
                  </template>
                  <template v-else>
                    {{ log.previousPromoterName || '-' }} → {{ log.newPromoterName || '-' }}
                  </template>
                </span>
              </p>
              <div v-if="log.reason" class="muted">原因：{{ log.reason }}</div>
              <div v-if="log.operatorName" class="muted">操作人：{{ log.operatorName }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无推广员变更记录" />
        </el-tab-pane>

        <!-- Binding history -->
        <el-tab-pane label="绑定历史" name="bindingHistory">
          <el-timeline v-if="bindingItems.length">
            <el-timeline-item
              v-for="log in bindingItems"
              :key="log.id"
              :timestamp="formatTime(log.createdAt)"
              placement="top"
            >
              <p>
                <el-tag :type="bindingReqStatusType(log.status)" size="small">{{ log.status }}</el-tag>
                <span style="margin-left: 8px;">来源: {{ log.sourceType }}</span>
              </p>
              <div v-if="log.changeLogs?.length" style="margin-top: 6px;">
                <div v-for="cl in log.changeLogs" :key="cl.id" style="font-size: 12px; color: #909399;">
                  {{ cl.operationType }} · {{ cl.reason || '无原因' }}
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无绑定历史" />
        </el-tab-pane>

        <!-- 消费记录 -->
        <el-tab-pane label="消费记录" name="contributions">
          <el-table v-loading="contribLoading" :data="contribItems" stripe empty-text="暂无消费记录" size="small">
            <el-table-column prop="title" label="项目" min-width="150" />
            <el-table-column label="消费金额" width="110">
              <template #default="{ row }">¥{{ (Number(row.amountCent || 0) / 100).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="contribStatusType(row.status)" size="small">{{ contribStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatTime(row.occurredAt) }}</template>
            </el-table-column>
          </el-table>
          <div class="load-more" v-if="contribHasMore">
            <el-button text size="small" :loading="contribLoadingMore" @click="loadMoreContribs">加载更多</el-button>
          </div>
        </el-tab-pane>

        <!-- Followups -->
        <el-tab-pane label="跟进记录" name="followups">
          <div class="followup-header">
            <el-button type="primary" size="small" @click="showAddFollowup = true">添加跟进</el-button>
          </div>

          <el-table v-loading="followupLoading" :data="followupItems" stripe empty-text="暂无跟进记录" size="small" style="margin-top: 10px;">
            <el-table-column label="方式" width="70">
              <template #default="{ row }">{{
                { phone: '电话', wechat: '微信', visit: '拜访', other: '其他' }[row.method] || row.method
              }}</template>
            </el-table-column>
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag :type="followupResultType(row.result)" size="small">{{
                  { successful: '成功', failed: '失败', pending: '待定', no_answer: '无应答' }[row.result] || row.result
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
            <el-table-column label="提醒" width="160">
              <template #default="{ row }">
                <span v-if="row.reminderEnabled">{{ formatTime(row.reminderAt) }}</span>
                <span v-else class="no-reminder">无</span>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- Add followup dialog -->
    <el-dialog v-model="showAddFollowup" title="添加跟进" width="460px">
      <el-form :model="followupForm" label-width="70px" size="small">
        <el-form-item label="方式">
          <el-select v-model="followupForm.method" style="width: 100%">
            <el-option label="电话" value="phone" />
            <el-option label="微信" value="wechat" />
            <el-option label="拜访" value="visit" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="followupForm.content" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="提醒时间">
          <el-date-picker
            v-model="followupForm.reminderAt"
            type="datetime"
            placeholder="选择提醒时间"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="showAddFollowup = false">取消</el-button>
        <el-button type="primary" size="small" :loading="addingFollowup" @click="submitFollowup">保存</el-button>
      </template>
    </el-dialog>

    <!-- 更改推广员 -->
    <TransferPromoterDialog
      v-model="showTransfer"
      :customer-id="customerId"
      :customer-name="customer?.name"
      :current-promoter="customer?.promoterName"
      :current-distributor-id="customer?.distributorId"
      :org-id="customer?.orgId"
      @success="handleTransferSuccess"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/api/http'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { adminCustomerApi } from '@/api/customers'
import { useAuthStore } from '@/stores/auth'
import TransferPromoterDialog from '@/components/customers/TransferPromoterDialog.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const customerId = route.params.id
const loading = ref(false)
const customer = ref(null)
const activeTab = ref('profile')
const editing = ref(false)
const saving = ref(false)
const showTransfer = ref(false)

const canWrite = computed(() => authStore.hasPermission('customers.write'))

const form = reactive({
  name: '',
  phone: '',
  idCard: '',
  medicalAccount: '',
  note: '',
  familyPhone: '',
  changeReason: '',
})

// Profile helpers
function bindingStatusLabel(s) {
  return { bound: '已绑定', unbound: '未绑定', pending: '待绑定' }[s] || s
}
function bindingStatusType(s) {
  return { bound: 'success', unbound: 'info', pending: 'warning' }[s] || 'info'
}
function bindingReqStatusType(s) {
  return { pending_match: 'info', matching: 'warning', bound: 'success', unbound: 'info', abnormal: 'danger' }[s] || 'info'
}
function contribStatusType(s) {
  return { paid: 'success', partially_refunded: 'warning', refunded: 'danger', cancelled: 'info' }[s] || 'info'
}
function contribStatusLabel(s) {
  return { paid: '已支付', partially_refunded: '部分退款', refunded: '已退款', cancelled: '已取消' }[s] || s
}
function followupResultType(r) {
  return { successful: 'success', failed: 'danger', pending: 'warning', no_answer: 'info' }[r] || 'info'
}

// 推广员变更记录
const changeLogItems = ref([])

// Binding history
const bindingItems = ref([])

// Contributions
const contribLoading = ref(false)
const contribItems = ref([])
const contribNextCursor = ref(null)
const contribHasMore = ref(false)
const contribLoadingMore = ref(false)

// Followups
const followupLoading = ref(false)
const followupItems = ref([])
const showAddFollowup = ref(false)
const addingFollowup = ref(false)
const followupForm = reactive({ method: 'phone', content: '', reminderAt: null })

onMounted(async () => {
  await loadCustomer()
})

async function loadCustomer() {
  loading.value = true
  try {
    const res = await http.get(`/admin/customers/${customerId}`)
    customer.value = res.data?.data || res.data

    if (customer.value) {
      form.name = customer.value.name || ''
      form.phone = customer.value.phoneMasked || ''
      form.idCard = customer.value.idCardMasked || ''
      form.medicalAccount = customer.value.medicalAccountMasked || ''
      form.note = customer.value.note || ''
      form.familyPhone = customer.value.familyPhone || ''
    }
  } catch (e) {
    ElMessage.error(e.userMessage || '加载客户详情失败')
  } finally {
    loading.value = false
  }
}

function startEdit() { editing.value = true }
function cancelEdit() {
  editing.value = false
  if (customer.value) {
    form.name = customer.value.name || ''
    form.phone = customer.value.phoneMasked || ''
    form.idCard = customer.value.idCardMasked || ''
    form.medicalAccount = customer.value.medicalAccountMasked || ''
    form.note = customer.value.note || ''
    form.familyPhone = customer.value.familyPhone || ''
    form.changeReason = ''
  }
}

async function saveProfile() {
  saving.value = true
  try {
    const body = {
      name: form.name,
      note: form.note,
      familyPhone: form.familyPhone,
    }
    // 仅提交发生变化的字段；敏感字段变化需 changeReason
    if (form.phone !== (customer.value?.phoneMasked || '')) {
      body.phone = form.phone
    }
    if (form.idCard !== (customer.value?.idCardMasked || '')) {
      body.idCard = form.idCard
    }
    if (form.medicalAccount !== (customer.value?.medicalAccountMasked || '')) {
      body.medicalAccount = form.medicalAccount
    }
    const sensitiveChanged = body.phone !== undefined || body.idCard !== undefined || body.medicalAccount !== undefined
    if (sensitiveChanged) {
      if (!form.changeReason) {
        ElMessage.warning('修改身份证/医保账户/手机号等敏感字段必须填写修改原因')
        return
      }
      body.changeReason = form.changeReason
    }

    await adminCustomerApi.update(customerId, body)
    ElMessage.success('保存成功')
    editing.value = false
    await loadCustomer()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.userMessage || '保存失败')
  } finally {
    saving.value = false
  }
}

// 推广员变更
function openTransfer() {
  showTransfer.value = true
}

async function handleTransferSuccess() {
  showTransfer.value = false
  await loadCustomer()
  await loadChangeLogs()
}

// 推广员变更记录 - loaded on tab switch
async function loadChangeLogs() {
  if (changeLogItems.value.length) return
  try {
    const data = await adminCustomerApi.changeLogs(customerId)
    changeLogItems.value = data.items || []
  } catch {
    // Silently ignore
  }
}

// Binding history - loaded on tab switch
async function loadBindingHistory() {
  if (bindingItems.value.length) return
  try {
    const res = await http.get(`/customers/${customerId}/binding-history`)
    const data = res.data?.data || res.data
    bindingItems.value = data.items || []
  } catch {
    // Silently ignore
  }
}

// Contributions - loaded on tab switch
async function loadContributions(cursor = null) {
  if (!cursor && contribItems.value.length) return
  contribLoading.value = !cursor
  try {
    const params = { pageSize: 20 }
    if (cursor) params.cursor = cursor
    const res = await http.get(`/customers/${customerId}/contributions`, { params })
    const data = res.data?.data || res.data
    const newItems = data.items || []

    if (cursor) {
      contribItems.value = [...contribItems.value, ...newItems]
    } else {
      contribItems.value = newItems
    }
    contribNextCursor.value = data.nextCursor
    contribHasMore.value = !!data.hasMore
  } catch {
    // Silently ignore
  } finally {
    contribLoading.value = false
    contribLoadingMore.value = false
  }
}

async function loadMoreContribs() {
  contribLoadingMore.value = true
  await loadContributions(contribNextCursor.value)
}

// Followups - loaded on tab switch
async function loadFollowups() {
  if (followupItems.value.length) return
  followupLoading.value = true
  try {
    const res = await http.get(`/customers/${customerId}/followups`)
    const data = res.data?.data || res.data
    followupItems.value = data.items || []
  } catch {
    // Silently ignore
  } finally {
    followupLoading.value = false
  }
}

async function submitFollowup() {
  addingFollowup.value = true
  try {
    const body = {
      method: followupForm.method,
      content: followupForm.content,
    }
    if (followupForm.reminderAt) {
      body.reminderAt = new Date(followupForm.reminderAt).toISOString()
    }
    await http.post(`/customers/${customerId}/followups`, body)
    ElMessage.success('跟进记录已添加')
    showAddFollowup.value = false
    followupForm.method = 'phone'
    followupForm.content = ''
    followupForm.reminderAt = null
    followupItems.value = []
    await loadFollowups()
  } catch (e) {
    ElMessage.error(e.userMessage || '添加跟进失败')
  } finally {
    addingFollowup.value = false
  }
}

// Tab switch handling
watch(activeTab, (name) => {
  if (name === 'changeLogs') loadChangeLogs()
  if (name === 'bindingHistory') loadBindingHistory()
  if (name === 'contributions') loadContributions()
  if (name === 'followups') loadFollowups()
})

function formatTime(t) {
  if (!t) return '-'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}
</script>

<style scoped>
.detail-card { min-height: 350px; }
.form-actions { margin-top: 16px; }

.followup-header { display: flex; justify-content: flex-end; }
.no-reminder { color: #c0c4cc; }
.muted { color: #909399; font-size: 12px; margin-left: 8px; }

.load-more { text-align: center; padding: 10px 0; }
</style>
