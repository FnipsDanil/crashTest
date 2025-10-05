import ReactDOM from 'react-dom/client'
import { init, backButton, initData, swipeBehavior, viewport } from '@telegram-apps/sdk-react'
import App from './App'
import './i18n'
import './index.css'

init()

// Mount viewport and disable vertical swipes to prevent app collapsing
try {
  // Mount viewport first
  if (viewport.mount.isAvailable()) {
    viewport.mount().then(() => {
      viewport.bindCssVars()
    }).catch(e => console.warn('Viewport mount failed:', e))
  }
  
  // Mount and configure swipe behavior
  if (swipeBehavior.mount.isAvailable()) {
    swipeBehavior.mount()
    
    // Disable vertical swipes to prevent collapsing
    if (swipeBehavior.disableVertical.isAvailable()) {
      swipeBehavior.disableVertical()
    }
  }
} catch (error) {
  console.warn('Failed to configure swipe behavior:', error)
}

// backButton.mount() - REMOVED: interferes with React Router navigation after first game

// Initialize init data for authentication
try {
  initData.restore()
} catch (error) {
  console.warn('Failed to restore init data:', error)
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />)