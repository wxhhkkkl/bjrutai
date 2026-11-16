<template>
  <section class="order-logistics" aria-label="物流轨迹" :aria-busy="loading">
    <header class="logistics-header">
      <div class="logistics-title">
        <span class="logistics-icon"><el-icon><Van /></el-icon></span>
        <h4>物流轨迹</h4>
        <el-tag v-if="snapshot?.source === 'fake'" size="small" type="info">模拟数据</el-tag>
      </div>
      <div class="logistics-actions">
        <el-button
          type="primary"
          plain
          size="small"
          :icon="Refresh"
          :loading="loading"
          @click="loadLogistics(true)"
        >更新物流</el-button>
      </div>
    </header>

    <div class="logistics-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-skeleton v-if="loading && !snapshot" :rows="2" animated aria-label="正在读取物流轨迹" />
      <template v-if="snapshot">
        <section class="logistics-map" aria-label="快递100地图轨迹">
          <div class="map-heading">
            <div>
              <h5><el-icon><Location /></el-icon> 快递100地图轨迹</h5>
              <p>地图默认展示 · 由快递100提供</p>
            </div>
            <el-tag v-if="snapshot.mapUrl" size="small" type="success">地图已返回</el-tag>
            <el-tag v-else size="small" type="info">等待地图数据</el-tag>
          </div>
          <iframe
            v-if="snapshot.mapUrl"
            class="map-frame"
            :src="snapshot.mapUrl"
            title="快递100物流地图轨迹"
            referrerpolicy="no-referrer"
          />
          <div v-else class="map-placeholder" role="status">
            <el-icon><Location /></el-icon>
            <p v-if="snapshot.source === 'fake'">当前是模拟物流数据，真实查询返回地图后会在此处直接展示。</p>
            <p v-else-if="snapshot.queryStatus === 'pending'">物流地图查询中，稍后刷新即可查看。</p>
            <p v-else-if="snapshot.queryStatus === 'config_required'">快递100地图查询配置尚未就绪。</p>
            <p v-else-if="snapshot.queryStatus === 'available' || snapshot.queryStatus === 'stale'">本次查询暂未返回地图链接，请确认账号地图轨迹服务及该快递公司的支持情况。</p>
            <p v-else>等待快递100返回地图轨迹。</p>
          </div>
        </section>
        <dl class="logistics-summary">
          <div><dt>当前状态</dt><dd>{{ snapshot.stateName || '暂无状态' }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ snapshot.updatedAt ? time(snapshot.updatedAt) : '暂无更新' }}</dd></div>
          <div v-if="snapshot.estimatedArrivalText">
            <dt>预计送达</dt><dd>{{ snapshot.estimatedArrivalText }}</dd>
          </div>
        </dl>
        <p v-if="queryMessage" class="logistics-notice" role="status">{{ queryMessage }}</p>
        <ol v-if="snapshot.events.length" class="logistics-timeline">
          <li v-for="(event, index) in snapshot.events" :key="index">
            <div class="event-meta">
              <span>{{ event.timeText || time(event.occurredAt) }}</span>
              <span v-if="event.stateName" class="event-state">{{ event.stateName }}</span>
            </div>
            <p>{{ event.description }}</p>
          </li>
        </ol>
        <div v-else-if="!queryMessage" class="logistics-empty">暂无物流轨迹</div>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Location, Refresh, Van } from '@element-plus/icons-vue'
import { getOrderLogistics } from '@/api/mall-orders'
import { time } from './order-view'

const props = defineProps({ orderId: { type: [String, Number], required: true } })
const loading = ref(false)
const snapshot = ref(null)
const error = ref('')
const queryMessage = computed(() => ({
  stale: '当前显示上次查询结果。',
  pending: '物流查询已排队，请稍后更新。',
  config_required: '物流查询配置尚未就绪。',
  verification_failed: '快递100未通过运单信息校验。',
  permission_denied: '快递100暂未授权此查询。',
  service_error: '物流服务暂不可用，请稍后重试。',
}[snapshot.value?.queryStatus] || ''))

onMounted(() => loadLogistics(false))

async function loadLogistics(scheduleRefresh) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    snapshot.value = await getOrderLogistics(props.orderId, scheduleRefresh)
  } catch (failure) {
    error.value = failure.userMessage || '读取物流轨迹失败，请重试。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.order-logistics {
  margin-top: 16px;
  border: 1px solid var(--app-border-color);
  border-radius: var(--app-radius-lg);
  background: var(--el-bg-color);
}

.logistics-header,
.logistics-title,
.logistics-actions,
.event-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.logistics-header {
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--app-border-color);
}

.logistics-title h4 {
  margin: 0;
  font-size: 15px;
  color: var(--app-text-primary);
}

.logistics-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 18px;
}

.logistics-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.logistics-actions a {
  text-decoration: none;
}

.logistics-body {
  display: grid;
  gap: 12px;
  padding: 16px;
}

.logistics-map {
  overflow: hidden;
  border: 1px solid var(--app-border-color);
  border-radius: 10px;
  background: var(--el-bg-color);
}

.map-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--app-border-color);
}

.map-heading h5 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--app-text-primary);
  font-size: 13px;
}

.map-heading h5 .el-icon {
  color: var(--el-color-primary);
}

.map-heading p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.map-frame {
  display: block;
  width: 100%;
  height: clamp(280px, 38vw, 440px);
  border: 0;
  background: var(--el-fill-color-light);
}

.map-placeholder {
  display: grid;
  min-height: 240px;
  place-content: center;
  justify-items: center;
  gap: 8px;
  padding: 24px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.72)),
    repeating-linear-gradient(0deg, transparent 0 39px, var(--app-border-color) 40px),
    repeating-linear-gradient(90deg, transparent 0 39px, var(--app-border-color) 40px),
    var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  text-align: center;
}

.map-placeholder .el-icon {
  color: var(--el-color-primary);
  font-size: 26px;
}

.map-placeholder p {
  max-width: 460px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.logistics-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(160px, 100%), 1fr));
  gap: 12px 20px;
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.logistics-summary dt,
.event-meta,
.logistics-notice,
.logistics-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.logistics-summary dd {
  margin: 4px 0 0;
  color: var(--app-text-primary);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.logistics-timeline {
  margin: 0;
  padding: 4px 0 0 6px;
  list-style: none;
}

.logistics-timeline li {
  position: relative;
  padding: 0 0 16px 16px;
  border-left: 1px solid var(--app-border-color);
}

.logistics-timeline li:last-child {
  padding-bottom: 0;
  border-left-color: transparent;
}

.logistics-timeline li::before {
  position: absolute;
  top: 5px;
  left: -4px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
  content: '';
}

.logistics-timeline li:first-child::before {
  background: var(--el-color-primary);
  box-shadow: 0 0 0 3px var(--el-color-primary-light-8);
}

.event-state {
  color: var(--el-color-primary);
}

.logistics-timeline p {
  margin: 4px 0 0;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.logistics-notice,
.logistics-empty {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}
</style>
