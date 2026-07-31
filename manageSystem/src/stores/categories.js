import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/api/http'

export const useCategoriesStore = defineStore('categories', () => {
  const categories = ref([])
  const loading = ref(false)

  async function fetchCategories() {
    loading.value = true
    try {
      const res = await http.get('/admin/categories')
      const body = res.data.data || res.data
      categories.value = body.items || []
    } catch {
      categories.value = []
    } finally {
      loading.value = false
    }
  }

  async function createCategory(data) {
    const res = await http.post('/admin/categories', data)
    await fetchCategories()
    return res.data
  }

  async function updateCategory(id, data) {
    const res = await http.put(`/admin/categories/${id}`, data)
    await fetchCategories()
    return res.data
  }

  async function deleteCategory(id) {
    const res = await http.delete(`/admin/categories/${id}`)
    await fetchCategories()
    return res.data
  }

  return { categories, loading, fetchCategories, createCategory, updateCategory, deleteCategory }
})
