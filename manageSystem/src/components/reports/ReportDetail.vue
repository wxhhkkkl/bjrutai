<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="报表详情"
    width="800px"
    top="5vh"
  >
    <div v-loading="loading">
      <template v-if="report">
        <!-- Report header -->
        <el-descriptions :column="2" border class="report-meta">
          <el-descriptions-item label="报表编号">{{ report.reportId }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ formatDate(report.generatedAt) }}</el-descriptions-item>
          <el-descriptions-item label="日期范围">
            {{ report.dateRange?.startDate }} ~ {{ report.dateRange?.endDate }}
          </el-descriptions-item>
          <el-descriptions-item label="维度">
            <el-tag
              v-for="dim in report.dimensions"
              :key="dim"
              size="small"
              style="margin-right: 4px"
            >
              {{ dimensionLabel(dim) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Binding section -->
        <div v-if="report.sections?.binding" class="section-block">
          <h4 class="section-title">{{ report.sections.binding.title }}</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item
              v-for="(val, key) in report.sections.binding.summary"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
          <el-table
            v-if="report.sections.binding.details?.length"
            :data="report.sections.binding.details"
            stripe
            size="small"
            class="section-table"
          >
            <el-table-column
              v-for="col in detailColumns(report.sections.binding.details)"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
            />
          </el-table>
        </div>

        <!-- Revenue section -->
        <div v-if="report.sections?.revenue" class="section-block">
          <h4 class="section-title">{{ report.sections.revenue.title }}</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item
              v-for="(val, key) in report.sections.revenue.summary"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
          <el-table
            v-if="report.sections.revenue.details?.length"
            :data="report.sections.revenue.details"
            stripe
            size="small"
            class="section-table"
          >
            <el-table-column
              v-for="col in detailColumns(report.sections.revenue.details)"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
            />
          </el-table>
        </div>

        <!-- Discount section -->
        <div v-if="report.sections?.discount" class="section-block">
          <h4 class="section-title">{{ report.sections.discount.title }}</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item
              v-for="(val, key) in report.sections.discount.summary"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
          <el-table
            v-if="report.sections.discount.details?.length"
            :data="report.sections.discount.details"
            stripe
            size="small"
            class="section-table"
            max-height="300"
          >
            <el-table-column
              v-for="col in detailColumns(report.sections.discount.details)"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
            />
          </el-table>
        </div>

        <!-- Allocation section -->
        <div v-if="report.sections?.allocation" class="section-block">
          <h4 class="section-title">{{ report.sections.allocation.title }}</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item
              v-for="(val, key) in report.sections.allocation.summary"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
          <el-table
            v-if="report.sections.allocation.details?.length"
            :data="report.sections.allocation.details"
            stripe
            size="small"
            class="section-table"
          >
            <el-table-column
              v-for="col in detailColumns(report.sections.allocation.details)"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
            />
          </el-table>
        </div>

        <!-- Performance (settlement) section -->
        <div v-if="report.sections?.performance" class="section-block">
          <h4 class="section-title">{{ report.sections.performance.title }}</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item
              v-for="(val, key) in report.sections.performance.summary"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
          <el-table
            v-if="report.sections.performance.details?.length"
            :data="report.sections.performance.details"
            stripe
            size="small"
            class="section-table"
          >
            <el-table-column
              v-for="col in detailColumns(report.sections.performance.details)"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
            />
          </el-table>
        </div>
      </template>
      <div v-else-if="!loading" class="empty-text">请选择报表查看</div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button type="success" @click="$emit('download', report?.reportId)" v-if="report">
        下载Excel
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

defineEmits(['update:visible', 'download'])

const dimensionLabels = {
  binding: '绑定汇总',
  revenue: '收入汇总',
  discount: '优惠汇总',
  allocation: '分配明细',
  performance: '绩效核算',
}

function dimensionLabel(dim) {
  return dimensionLabels[dim] || dim
}

function detailColumns(details) {
  if (!details || details.length === 0) return []
  return Object.keys(details[0])
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
.report-meta { margin-bottom: 20px; }

.section-block { margin-bottom: 24px; }
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
}
.section-table { margin-top: 12px; }

.empty-text { text-align: center; padding: 40px 0; color: #909399; font-size: 14px; }
</style>
