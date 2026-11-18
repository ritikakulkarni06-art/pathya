import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import '@fontsource-variable/space-grotesk'
import '@fontsource-variable/noto-sans-devanagari'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource/atkinson-hyperlegible/400.css'
import '@fontsource/atkinson-hyperlegible/700.css'
import './index.css'
import App from './App'
import { registerSW } from 'virtual:pwa-register'

// When a new build is published, switch to it straight away instead of showing a half-old page.
registerSW({ immediate: true })
// If the page still asks for a file from the previous build, reload once to pick up the new one.
window.addEventListener('vite:preloadError', () => {
  if (sessionStorage.getItem('pathya.reloaded')) return
  sessionStorage.setItem('pathya.reloaded', '1')
  window.location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
