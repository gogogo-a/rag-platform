<template>
  <div class="register-form-container">
    <div class="form-header">
      <div class="brand-logo">
        <img src="/logo.png" alt="RAG Platform Logo" class="logo-image" />
        <h2 class="form-title gradient-text">RAG 智能问答平台</h2>
      </div>
      <p class="form-subtitle">开始您的智能问答之旅</p>
    </div>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      class="register-form"
      @submit.prevent="handleRegister"
    >
      <el-form-item prop="nickname">
        <el-input
          v-model="form.nickname"
          placeholder="请输入昵称"
          size="large"
          :prefix-icon="User"
        />
      </el-form-item>

      <el-form-item prop="email">
        <el-input
          v-model="form.email"
          placeholder="请输入邮箱"
          size="large"
          :prefix-icon="Message"
        />
      </el-form-item>

      <el-form-item prop="code">
        <el-input
          v-model="form.code"
          placeholder="请输入验证码"
          size="large"
          :prefix-icon="Key"
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

      <el-form-item prop="password">
        <el-input
          v-model="form.password"
          type="password"
          placeholder="请输入密码（至少6位）"
          size="large"
          :prefix-icon="Lock"
          show-password
        />
      </el-form-item>

      <el-form-item prop="confirmPassword">
        <el-input
          v-model="form.confirmPassword"
          type="password"
          placeholder="请再次输入密码"
          size="large"
          :prefix-icon="Lock"
          show-password
          @keyup.enter="handleRegister"
        />
      </el-form-item>

      <el-form-item>
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          @click="handleRegister"
          class="submit-btn neon-border"
        >
          注册
        </el-button>
      </el-form-item>
    </el-form>

    <div class="form-footer">
      <span class="footer-text">已有账户？</span>
      <router-link to="/login" class="footer-link neon-text">立即登录</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { register, sendEmailCode } from '@/api'
import { ElMessage } from 'element-plus'
import { User, Lock, Message, Key } from '@element-plus/icons-vue'

const router = useRouter()

const formRef = ref(null)
const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)

const form = reactive({
  nickname: '',
  email: '',
  code: '',
  password: '',
  confirmPassword: ''
})

// 自定义验证规则：确认密码
const validateConfirmPassword = (rule, value, callback) => {
  if (value === '') {
    callback(new Error('请再次输入密码'))
  } else if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const rules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, max: 20, message: '昵称长度在 2 到 20 个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 6, message: '验证码长度为6位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

// 发送验证码
const handleSendCode = async () => {
  if (!form.email) {
    ElMessage.warning('请先输入邮箱')
    return
  }

  // 简单的邮箱格式验证
  const emailReg = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailReg.test(form.email)) {
    ElMessage.warning('请输入正确的邮箱格式')
    return
  }

  sendingCode.value = true
  try {
    await sendEmailCode({ email: form.email })
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

// 注册
const handleRegister = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      await register({
        nickname: form.nickname,
        email: form.email,
        captcha: form.code,
        password: form.password,
        confirm_password: form.confirmPassword
      })
      
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } catch (error) {
      console.error('注册失败:', error)
      ElMessage.error('注册失败，请检查信息后重试')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.register-form-container {
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

.register-form {
  width: 100%;
}

.register-form .el-form-item {
  margin-bottom: 20px;
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

