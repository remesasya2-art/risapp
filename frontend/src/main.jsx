import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initMercadoPago } from '@mercadopago/sdk-react'
import './index.css'
import App from './App.jsx'

// Mercado Pago Public Key (PRODUCTION).
// NOTE: This is the PUBLIC key — safe to expose in frontend bundle by design.
// The secret Access Token stays on the backend (.env).
// If credentials change, update this string.
const MP_PUBLIC_KEY_PROD = 'APP_USR-fb24f412-d600-4fc9-84ee-4065832e4413';

// Allow override via .env when present (e.g. for sandbox testing), but fall
// back to hardcoded production key so deploys without VITE_MP_PUBLIC_KEY
// still work correctly.
const mpPublicKey = import.meta.env.VITE_MP_PUBLIC_KEY || MP_PUBLIC_KEY_PROD;
initMercadoPago(mpPublicKey, { locale: 'pt-BR' });

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
