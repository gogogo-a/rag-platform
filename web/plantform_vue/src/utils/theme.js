import { ref } from 'vue'

export const THEME_STORAGE_KEY = 'plantform-theme'
export const THEME_DARK = 'dark'
export const THEME_LIGHT = 'light'

const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined'

const readStoredTheme = () => {
  if (!isBrowser) return THEME_DARK

  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY)
  return storedTheme === THEME_LIGHT ? THEME_LIGHT : THEME_DARK
}

const activeTheme = ref(readStoredTheme())

export const applyTheme = (theme = activeTheme.value) => {
  const normalizedTheme = theme === THEME_LIGHT ? THEME_LIGHT : THEME_DARK
  activeTheme.value = normalizedTheme

  if (!isBrowser) return normalizedTheme

  const root = document.documentElement
  root.classList.toggle('dark', normalizedTheme === THEME_DARK)
  root.classList.toggle('light', normalizedTheme === THEME_LIGHT)
  root.setAttribute('data-theme', normalizedTheme)
  localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme)
  window.dispatchEvent(new CustomEvent('plantform-theme-change', { detail: normalizedTheme }))

  return normalizedTheme
}

export const toggleTheme = () => {
  return applyTheme(activeTheme.value === THEME_DARK ? THEME_LIGHT : THEME_DARK)
}

export const getCurrentTheme = () => activeTheme.value

export const useTheme = () => {
  return {
    activeTheme,
    applyTheme,
    toggleTheme,
    getCurrentTheme
  }
}
