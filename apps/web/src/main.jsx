import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './index.css'
import App from './App.jsx'

// Pas d'installMockFetch : apps/web parle au vrai backend FastAPI (VITE_API_URL)
// avec le JWT Supabase (voir src/api.js). lucis-dashboard reste la démo mockée.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
