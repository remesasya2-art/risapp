import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// ACA SE ARRANCABA EL SDK DE PAGOS CON `VITE_MP_PUBLIC_KEY`, Y SE SACO.
//
// Esa variable es DE COMPILACION: su valor se hornea adentro del paquete
// cuando corre `npm run build`. O sea que la clave pública quedaba escrita en
// el archivo servido, y cambiarla exigía volver a compilar.
//
// QUE PASO POR ESO
//
//   Al cambiar de aplicación en Mercado Pago se actualizó el token del
//   servidor y esta clave quedó con la de la aplicación vieja. La tarjeta se
//   convertía en token bajo una aplicación y se cobraba con las credenciales
//   de otra, así que Mercado Pago contestaba:
//
//       MP API error 400: {'message': 'Invalid credentials'}
//
//   Y al cliente le aparecía «Pago no aprobado. Probá con otra tarjeta»: un
//   mensaje que culpa a su tarjeta cuando el problema era nuestro. Nadie
//   podía pagar con tarjeta, y el síntoma mandaba a buscar el problema en el
//   lugar equivocado.
//
// AHORA LA CLAVE SE PIDE AL SERVIDOR, en `CardPaymentBrick`, a la misma ruta
// que ya la devolvía. Una sola fuente, y cambiarla es cambiar una variable de
// entorno sin recompilar nada.

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
