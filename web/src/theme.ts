import { useEffect, useState } from 'react'

// Light or dark: the system setting until the person chooses, then their choice, remembered.
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('readyset-theme') ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') } catch { return 'light' }
  })
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])
  useEffect(() => {
    const preference = matchMedia('(prefers-color-scheme: dark)')
    const update = () => {
      try { if (localStorage.getItem('readyset-theme')) return } catch { /* storage may be disabled */ }
      setTheme(preference.matches ? 'dark' : 'light')
    }
    preference.addEventListener('change', update)
    return () => preference.removeEventListener('change', update)
  }, [])
  const toggle = () => setTheme(current => {
    const next = current === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem('readyset-theme', next) } catch { /* storage may be disabled */ }
    return next
  })
  return { theme, toggle }
}
