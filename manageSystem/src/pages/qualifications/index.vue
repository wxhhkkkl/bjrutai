<template>
  <div class="qualifications-page">
    <div class="page-header">
      <h2 class="page-title">资质审核</h2>
      <div class="header-actions">
        <el-button @click="refreshList">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <!-- Status filter tabs -->
    <div class="filter-bar">
      <el-radio-group v-model="statusFilter" @change="handleStatusFilter">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="reviewing">待审核</el-radio-button>
        <el-radio-button value="approved">已通过</el-radio-button>
        <el-radio-button value="rejected">已驳回</el-radio-button>
      </el-radio-group>
    </div>

    <!-- Review table -->
    <div class="table-container" v-loading="store.loading">
      <el-empty v-if="!store.loading && store.reviewList.length === 0" description="暂无审核记录" />
      <el-table v-else :data="store.reviewList" border stripe style="width: 100%">
        <el-table-column label="法人实体" width="180">
          <template #default="{ row }">
            {{ row.legal_entity || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="资质类型" width="120">
          <template #default="{ row }">
            {{ row.qualification_type || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.submitted_at || row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="store.getStatusType(row.status)" size="small">
              {{ store.getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交人" width="120">
          <template #default="{ row }">
            {{ row.submitted_by || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openReview(row)">
              审核
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Review modal -->
    <ReviewModal
      v-model="showReviewModal"
      :qualification-data="currentQualification"
      @success="onReviewSuccess"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useQualificationsStore } from '@/stores/qualifications'
import ReviewModal from '@/components/qualifications/ReviewModal.vue'

const store = useQualificationsStore()

const statusFilter = ref('')
const showReviewModal = ref(false)
const currentQualification = ref(null)

function formatDate(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function handleStatusFilter(val) {
  store.fetchReviewList(val || undefined)
}

function openReview(row) {
  currentQualification.value = { ...row }
  showReviewModal.value = true
}

function onReviewSuccess() {
  currentQualification.value = null
  store.fetchReviewList(statusFilter.value || undefined)
}

function refreshList() {
  store.fetchReviewList(statusFilter.value || undefined)
}

onMounted(() => {
  store.fetchReviewList()
})
</script>

<style scoped>
.qualifications-page { padding: 10px 0; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  background: #fff;
  padding: 12px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}

.table-container {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 16px;
  min-height: 200px;
}
</style>
