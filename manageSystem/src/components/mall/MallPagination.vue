<template>
  <el-pagination
    v-if="total > 0"
    class="mall-pagination"
    :current-page="currentPage"
    :page-size="pageSize"
    :total="total"
    :disabled="disabled"
    :layout="MALL_PAGINATION_LAYOUT"
    @current-change="emit('change', $event)"
  />
</template>

<script setup>
import { MALL_PAGE_SIZE, MALL_PAGINATION_LAYOUT } from './mall-pagination'

defineProps({
  currentPage: { type: Number, required: true },
  pageSize: { type: Number, default: MALL_PAGE_SIZE },
  total: { type: Number, required: true },
  disabled: Boolean,
})

const emit = defineEmits(['change'])
</script>
