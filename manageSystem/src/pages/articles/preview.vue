<template>
  <div class="preview-page">
    <div class="preview-container" v-if="article">
      <h1 class="preview-title">{{ article.title || '无标题' }}</h1>
      <div class="preview-meta">
        <el-tag v-if="article.category" size="small">{{ article.category }}</el-tag>
        <span class="preview-author" v-if="article.author">{{ article.author }}</span>
        <span class="preview-time" v-if="article.publishedAt">{{ formatTime(article.publishedAt) }}</span>
      </div>
      <div class="preview-body" v-html="article.content || '<p style=color:#999>暂无内容</p>'"></div>
    </div>
    <div v-else class="preview-loading">加载中...</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import http from '@/api/http'

const route = useRoute()
const article = ref(null)

onMounted(async () => {
  const id = route.params.id
  try {
    const res = await http.get(`/articles/${id}`)
    article.value = (res.data.data || res.data)
  } catch {
    // Fallback: show basic info
    article.value = {}
  }
})

function formatTime(t) {
  if (!t) return ''
  try { return new Date(t).toLocaleDateString('zh-CN') } catch { return t }
}
</script>

<style scoped>
.preview-page { background: #f5f5f5; min-height: 100vh; padding: 20px 0; }
.preview-container { max-width: 780px; margin: 0 auto; background: #fff; padding: 40px 50px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.preview-title { font-size: 28px; font-weight: 700; color: #303133; margin-bottom: 16px; line-height: 1.4; }
.preview-meta { display: flex; align-items: center; gap: 14px; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #eee; }
.preview-author { color: #606266; font-size: 14px; }
.preview-time { color: #909399; font-size: 13px; }
.preview-body { font-size: 16px; line-height: 1.9; color: #303133; }
.preview-body :deep(img) { max-width: 100%; height: auto; margin: 12px 0; border-radius: 4px; }
.preview-loading { text-align: center; padding: 60px; color: #999; }
</style>
