/**
 * contacto.js — El canal de contacto público, traído del servidor.
 *
 * POR QUE NO ESTA ESCRITO ACA
 *
 *   Estaba a mano en seis lugares: el pie de página y cinco párrafos de la
 *   página legal. Este código se compila y se le sirve al navegador de CADA
 *   visitante, así que esa dirección viajaba dentro del bundle — pública,
 *   fácil de raspar para cualquier robot que lea el JS, y sin forma de
 *   cambiarla que no fuera un despliegue.
 *
 *   Ahora sale de `GET /api/contacto`, que la lee de la configuración del
 *   servidor. Se cambia en un solo lugar y los seis se actualizan juntos.
 *
 * SI NO HAY NINGUNA CONFIGURADA
 *
 *   `correo` queda en null y cada pantalla manda al soporte de la aplicación
 *   en vez de mostrar un "escriba a" sin destinatario.
 */
import { useState, useEffect } from 'react';
import api from './api';

export default function useContacto() {
  const [correo, setCorreo] = useState(null);

  useEffect(() => {
    let vigente = true;
    api.get('/contacto')
      .then(({ data }) => { if (vigente) setCorreo(data?.correo || null); })
      .catch(() => { /* Sin contacto configurado se cae al soporte interno. */ });
    return () => { vigente = false; };
  }, []);

  return correo;
}
