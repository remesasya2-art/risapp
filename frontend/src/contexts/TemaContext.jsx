/**
 * TemaContext — qué apariencia eligió la persona, y el botón para cambiarla.
 *
 * QUIEN MANDA
 *
 *   1. Lo guardado en la cuenta, si la persona entró y alguna vez eligió.
 *   2. Si no, lo guardado en este aparato (lo que eligió en la portada).
 *   3. Si no, 'auto': lo que diga el aparato.
 *
 *   Cuando alguien entra con una cuenta que nunca eligió y en el aparato ya
 *   había elegido algo, eso se sube a la cuenta. Si no, quien eligió oscuro en
 *   la portada entraría y lo perdería en la computadora del trabajo.
 *
 * QUE PASA SI NO SE PUEDE GUARDAR EN LA CUENTA
 *
 *   El cambio se ve igual y queda en el aparato; se avisa, y nada más. Es una
 *   preferencia: dejar a alguien sin poder cambiar el color porque el
 *   servidor no contestó sería peor que el aviso.
 *
 * LA CUENTA SE LEE UNA VEZ POR SESION, NO CADA VEZ QUE CAMBIA `user`
 *
 *   `setUser` se llama en varios lugares. Si cada llamada volviera a copiar
 *   la elección de la cuenta, lo que la persona acaba de elegir se pisaría
 *   con lo que la cuenta tenía antes, hasta que el servidor contestara.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { useAuth } from './AuthContext';
import {
  alCambiarElAparato, elAparatoPrefiereOscuro, esValida, guardarEnElAparato, leerDelAparato,
} from '../tema/apariencia';

const TemaContext = createContext(null);

export function TemaProvider({ children }) {
  const { user } = useAuth();
  const [apariencia, setApariencia] = useState(leerDelAparato);
  const aparatoOscuro = useSyncExternalStore(alCambiarElAparato, elAparatoPrefiereOscuro);
  const tema = apariencia === 'auto' ? (aparatoOscuro ? 'oscuro' : 'claro') : apariencia;

  // De qué cuenta ya se leyó la elección. Se ajusta durante el render, que
  // es la forma que recomienda React para derivar estado de una prop que
  // cambia: hacerlo en un efecto pinta una vez con el color viejo.
  const cuentaActual = user?.user_id ?? null;
  const [cuentaLeida, setCuentaLeida] = useState(null);
  if (cuentaActual !== cuentaLeida) {
    setCuentaLeida(cuentaActual);
    if (cuentaActual && esValida(user.apariencia)) setApariencia(user.apariencia);
  }

  useEffect(() => {
    document.documentElement.dataset.tema = tema;
  }, [tema]);

  useEffect(() => {
    guardarEnElAparato(apariencia);
  }, [apariencia]);

  // Cuenta que nunca eligió: se le sube lo del aparato, una vez.
  const subida = useRef(null);
  useEffect(() => {
    if (!cuentaActual || subida.current === cuentaActual) return;
    subida.current = cuentaActual;
    if (esValida(user.apariencia)) return;
    const delAparato = leerDelAparato();
    if (delAparato === 'auto') return;
    api.put('/auth/me/apariencia', { apariencia: delAparato }).catch(() => {
      // En silencio: la persona no pidió nada todavía. Se reintenta la
      // próxima vez que entre.
    });
  }, [cuentaActual, user?.apariencia]);

  const elegir = useCallback(async (nueva) => {
    if (!esValida(nueva)) return;
    setApariencia(nueva);
    if (!cuentaActual) return;
    try {
      await api.put('/auth/me/apariencia', { apariencia: nueva });
    } catch {
      toast.error('No pudimos guardarlo en tu cuenta. Quedó guardado en este aparato.');
    }
  }, [cuentaActual]);

  return (
    <TemaContext.Provider value={{ apariencia, tema, elegir }}>
      {children}
    </TemaContext.Provider>
  );
}

export const useTema = () => {
  const contexto = useContext(TemaContext);
  if (!contexto) throw new Error('useTema tiene que usarse dentro de TemaProvider');
  return contexto;
};
