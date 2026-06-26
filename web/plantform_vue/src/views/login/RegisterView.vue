<template>
  <div class="register-view">
    <div class="register-container slide-in-up">
      <div class="register-card card">
        <RegisterForm />
      </div>
    </div>
  </div>
</template>

<script setup>
import RegisterForm from '@/components/login/RegisterForm.vue'
</script>

<style scoped>
.register-view {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.register-container {
  width: 100%;
  max-width: 450px;
}

.register-card {
  padding: 40px;
  background: var(--component-bg);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-color);
  box-shadow: 0 8px 32px var(--shadow-color);
}

.register-card:hover {
  border-color: var(--neon-purple);
  box-shadow: 0 0 30px var(--shadow-color);
}
</style>
