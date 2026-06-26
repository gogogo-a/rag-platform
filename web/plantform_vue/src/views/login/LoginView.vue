<template>
  <div class="login-view">
    <div class="login-container slide-in-up">
      <div class="login-card card">
        <LoginForm />
      </div>
    </div>
  </div>
</template>

<script setup>
import LoginForm from '@/components/login/LoginForm.vue'
</script>

<style scoped>
.login-view {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 450px;
}

.login-card {
  padding: 40px;
  background: var(--component-bg);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-color);
  box-shadow: 0 8px 32px var(--shadow-color);
}

.login-card:hover {
  border-color: var(--neon-blue);
  box-shadow: 0 0 30px var(--shadow-color);
}
</style>
