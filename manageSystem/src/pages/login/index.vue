<template>
  <div class="login-container">
    <div class="login-aurora" aria-hidden="true"></div>
    <LoginDragon />
    <div class="login-card-wrapper">
      <h2 class="login-title">北京儒泰分销管理系统</h2>
      <p class="login-subtitle">管理后台</p>
      <el-card class="login-card">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              :prefix-icon="User"
              size="large"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              size="large"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <el-alert
            v-if="errorMsg"
            :title="errorMsg"
            type="error"
            show-icon
            :closable="false"
            style="margin-bottom: 18px"
          />
          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              style="width: 100%"
              @click="handleLogin"
            >
              {{ loading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
    <p class="login-footer">北京儒泰 &copy; {{ currentYear }}</p>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { User, Lock } from '@element-plus/icons-vue'
import LoginDragon from '@/components/LoginDragon.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const currentYear = new Date().getFullYear()

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.login(form.username, form.password)
    const redirect = route.query.redirect || '/'
    await router.push(redirect)
  } catch (err) {
    console.error('Login error:', err)
    errorMsg.value = err.userMessage || err.response?.data?.message || err.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(59, 130, 246, 0.35), transparent 60%),
    radial-gradient(1000px 700px at 110% 120%, rgba(147, 197, 253, 0.28), transparent 55%),
    linear-gradient(135deg, #0f2557 0%, #1e3c72 40%, #2a5298 75%, #163a6b 100%);
  /* 网格层 */
  background-image:
    radial-gradient(1200px 600px at 20% -10%, rgba(59, 130, 246, 0.35), transparent 60%),
    radial-gradient(1000px 700px at 110% 120%, rgba(147, 197, 253, 0.28), transparent 55%),
    linear-gradient(135deg, #0f2557 0%, #1e3c72 40%, #2a5298 75%, #163a6b 100%),
    repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 44px),
    repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 44px);
}

/* 背景极光流动光晕（在网格之上、卡片之下） */
.login-aurora {
  position: absolute;
  inset: -40%;
  z-index: 0;
  background:
    radial-gradient(40% 55% at 25% 30%, rgba(56, 132, 255, 0.42), transparent 70%),
    radial-gradient(45% 60% at 75% 35%, rgba(99, 179, 255, 0.30), transparent 70%),
    radial-gradient(50% 65% at 60% 80%, rgba(37, 99, 235, 0.36), transparent 72%),
    radial-gradient(35% 45% at 15% 75%, rgba(147, 197, 253, 0.22), transparent 65%);
  filter: blur(50px);
  animation: auroraFlow 22s ease-in-out infinite alternate;
  pointer-events: none;
}

/* 漂浮光斑（动态，更精致） */
.login-container::before,
.login-container::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  animation: blobDrift 16s ease-in-out infinite;
  pointer-events: none;
}
.login-container::before {
  width: 460px;
  height: 460px;
  top: -140px;
  left: -100px;
  background: radial-gradient(circle at 30% 30%, rgba(59, 130, 246, 0.55), transparent 62%);
}
.login-container::after {
  width: 520px;
  height: 520px;
  bottom: -160px;
  right: -120px;
  animation-delay: -8s;
  background: radial-gradient(circle at 70% 70%, rgba(147, 197, 253, 0.45), transparent 62%);
}

.login-card-wrapper {
  position: relative;
  z-index: 2;
  width: 400px;
}

.login-title {
  position: relative;
  text-align: center;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #fff;
  text-shadow: 0 2px 18px rgba(2, 12, 44, 0.45), 0 0 40px rgba(59, 130, 246, 0.35);
}
.login-title::after {
  content: '';
  display: block;
  height: 3px;
  border-radius: 2px;
  margin: 12px auto 0;
  background: linear-gradient(90deg, transparent, #93c5fd, #60a5fa, #93c5fd, transparent);
  animation: growBar 0.9s var(--app-ease) 0.25s both;
}

.login-subtitle {
  text-align: center;
  color: rgba(255, 255, 255, 0.75);
  font-size: 14px;
  margin-top: 6px;
  margin-bottom: 28px;
}

.login-card {
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 8px 32px rgba(2, 12, 44, 0.35);
  animation: cardIn 0.6s var(--app-ease) both, cardFloat 6s ease-in-out 0.8s infinite;
}

.login-footer {
  position: fixed;
  bottom: 16px;
  z-index: 3;
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
}
</style>
