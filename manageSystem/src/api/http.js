import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  failedQueue = []
}

// Request interceptor — attach Authorization Bearer token
http.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — handle 401 and token refresh
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Skip token refresh for login requests (they are expected to 401)
    const isAuthRequest = originalRequest.url?.includes('/auth/')
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthRequest) {
      if (isRefreshing) {
        // Queue this request while a refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return http(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      const authStore = useAuthStore()
      try {
        await authStore.refreshAccessToken()
        processQueue(null, authStore.token)
        originalRequest.headers.Authorization = `Bearer ${authStore.token}`
        return http(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        authStore.logout()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    // Unified error handling — map error codes to messages
    if (error.response) {
      const { status, data } = error.response
      const msg = data?.message || data?.detail || error.message
      switch (status) {
        case 400:
          error.userMessage = msg || '请求参数有误'
          break
        case 403:
          error.userMessage = msg || '没有操作权限'
          break
        case 404:
          error.userMessage = msg || '请求的资源不存在'
          break
        case 409:
          error.userMessage = msg || '数据冲突，请刷新后重试'
          break
        case 422:
          error.userMessage = msg || '提交数据校验失败'
          break
        case 429:
          error.userMessage = '请求过于频繁，请稍后重试'
          break
        case 500:
          error.userMessage = '服务器内部错误，请稍后重试'
          break
        default:
          error.userMessage = msg || `请求失败 (${status})`
      }
    } else if (error.code === 'ECONNABORTED') {
      error.userMessage = '请求超时，请检查网络连接'
    } else {
      error.userMessage = '网络连接失败，请检查网络'
    }

    return Promise.reject(error)
  }
)

export default http
