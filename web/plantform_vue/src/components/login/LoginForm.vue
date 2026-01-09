<template>
  <div class="login-form-container">
    <div class="form-header">
      <div class="brand-logo">
        <img src="/logo.png" alt="RAG Platform Logo" class="logo-image" />
        <h2 class="form-title gradient-text">RAG 智能问答平台</h2>
      </div>
      <p class="form-subtitle">登录您的账户</p>
    </div>

    <el-tabs v-model="loginType" class="login-tabs">
      <el-tab-pane label="密码登录" name="password">
        <el-form
          ref="passwordFormRef"
          :model="passwordForm"
          :rules="passwordRules"
          class="login-form"
          @submit.prevent="handlePasswordLogin"
        >
          <el-form-item prop="nickname">
            <el-input
              v-model="passwordForm.nickname"
              placeholder="请输入昵称"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="passwordForm.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handlePasswordLogin"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              @click="handlePasswordLogin"
              class="submit-btn neon-border"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="验证码登录" name="email">
        <el-form
          ref="emailFormRef"
          :model="emailForm"
          :rules="emailRules"
          class="login-form"
          @submit.prevent="handleEmailLogin"
        >
          <el-form-item prop="email">
            <el-input
              v-model="emailForm.email"
              placeholder="请输入邮箱"
              size="large"
              :prefix-icon="Message"
            />
          </el-form-item>

          <el-form-item prop="code">
            <el-input
              v-model="emailForm.code"
              placeholder="请输入验证码"
              size="large"
              :prefix-icon="Key"
              @keyup.enter="handleEmailLogin"
            >
              <template #append>
                <el-button
                  :disabled="countdown > 0"
                  @click="handleSendCode"
                  :loading="sendingCode"
                >
                  {{ countdown > 0 ? `${countdown}秒` : '发送验证码' }}
                </el-button>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              @click="handleEmailLogin"
              class="submit-btn neon-border"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <div class="form-footer">
      <span class="footer-text">还没有账户？</span>
      <router-link to="/register" class="footer-link neon-text">立即注册</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store'
import { sendEmailCode } from '@/api'
import { ElMessage } from 'element-plus'
import { User, Lock, Message, Key } from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()

const loginType = ref('password')
const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)

// 密码登录表单
const passwordFormRef = ref(null)
const passwordForm = reactive({
  nickname: '',
  password: ''
})

const passwordRules = {
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

// 邮箱登录表单
const emailFormRef = ref(null)
const emailForm = reactive({
  email: '',
  code: ''
})

const emailRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 6, message: '验证码长度为6位', trigger: 'blur' }
  ]
}

// 密码登录
const handlePasswordLogin = async () => {
  if (!passwordFormRef.value) return

  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const result = await userStore.login(passwordForm)
      if (result.success) {
        ElMessage.success('登录成功')
        router.push('/chat')
      } else {
        ElMessage.error('登录失败，请检查用户名和密码')
      }
    } catch (error) {
      console.error('登录失败:', error)
    } finally {
      loading.value = false
    }
  })
}

// 邮箱登录
const handleEmailLogin = async () => {
  if (!emailFormRef.value) return

  await emailFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      // 转换字段名以匹配 API 文档
      const result = await userStore.emailLogin({
        email: emailForm.email,
        captcha: emailForm.code
      })
      if (result.success) {
        ElMessage.success('登录成功')
        router.push('/chat')
      } else {
        ElMessage.error('登录失败，请检查邮箱和验证码')
      }
    } catch (error) {
      console.error('登录失败:', error)
    } finally {
      loading.value = false
    }
  })
}

// 发送验证码
const handleSendCode = async () => {
  if (!emailForm.email) {
    ElMessage.warning('请先输入邮箱')
    return
  }

  // 简单的邮箱格式验证
  const emailReg = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailReg.test(emailForm.email)) {
    ElMessage.warning('请输入正确的邮箱格式')
    return
  }

  sendingCode.value = true
  try {
    await sendEmailCode({ email: emailForm.email })
    ElMessage.success('验证码已发送，请查收邮件')
    
    // 开始倒计时
    countdown.value = 60
    const timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(timer)
      }
    }, 1000)
  } catch (error) {
    console.error('发送验证码失败:', error)
  } finally {
    sendingCode.value = false
  }
}
</script>

<style scoped>
.login-form-container {
  width: 100%;
}

.form-header {
  text-align: center;
  margin-bottom: 32px;
}

.brand-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.logo-image {
  width: 64px;
  height: 64px;
  object-fit: contain;
  border-radius: 12px;
  animation: pulse 2s ease-in-out infinite;
}

.form-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0;
}

.form-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.login-tabs {
  margin-bottom: 24px;
}

.login-form {
  width: 100%;
}

.login-form .el-form-item {
  margin-bottom: 24px;
}

.submit-btn {
  width: 100%;
  font-size: 16px;
  font-weight: 600;
  height: 48px;
  border-radius: 24px;
  background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue));
  border: none;
  transition: all 0.3s ease;
}

.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
}

.form-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.footer-text {
  color: var(--text-secondary);
  font-size: 14px;
  margin-right: 8px;
}

.footer-link {
  color: var(--neon-blue);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.footer-link:hover {
  text-shadow: 0 0 10px var(--neon-blue);
}
</style>

