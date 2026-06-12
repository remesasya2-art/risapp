import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initMercadoPago } from '@mercadopago/sdk-react'
import './index.css'
import App from './App.jsx'

// Mercado Pago Public Key -- debe configurarse via VITE_MP_PUBLIC_KEY en el archivo .env
const mpPublicKey = import.meta.env.VITE_MP_PUBLIC_KEY;
initMercadoPago(mpPublicKey, { locale: 'pt-BR' });

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
