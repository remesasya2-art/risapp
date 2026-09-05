/**
 * perfil.js — Las reglas de la pantalla «Mi Perfil», fuera del JSX.
 *
 * POR QUE UN MODULO APARTE
 *
 *   Lo mismo que `envioAVenezuela.js` y `envioABrasil.js`: la pantalla dibuja,
 *   esto decide. Una regla metida entre el JSX no se puede probar sin montar un
 *   navegador, y termina probándose a mano una vez y nunca más.
 *
 * LO QUE SE ARREGLA ACA, Y NO ES COSMETICO
 *
 *   1. LA FOTO SE LEIA DE UN CAMPO QUE NO EXISTE. La pantalla miraba
 *      `user.picture`; el modelo del backend declara `profile_picture`, que es
 *      el que lee el panel de administración. `user.picture` es `undefined`
 *      siempre, así que la rama de la foto nunca se ejecutaba. Y cuando se
 *      ejecute, la URL viene de la base: pasa por `rutaDeArchivo`, como todo lo
 *      demás que se abre en esta aplicación. Ponerla cruda en un `src` es el
 *      agujero que `urlDeArchivo.js` vino a cerrar.
 *
 *   2. LA MASCARA DEL CPF ESTABA MAL FORMADA. `***.***.**2-34` mueve un dígito
 *      real al final del tercer grupo y rompe la forma del CPF: no se parece a
 *      un CPF, así que no ayuda a reconocerlo. Se usa `cpfAbreviado`, que es la
 *      misma regla de enmascarado que el flujo de Brasil. Una sola forma de
 *      tapar un CPF en toda la aplicación.
 *
 *   3. LA CONTRASEÑA NUEVA PODIA SER LA MISMA QUE LA VIEJA. Ni la pantalla ni
 *      el servidor lo miraban: el cambio «salía bien» y no cambiaba nada. Quien
 *      cambia su contraseña es alguien que sospecha que le entraron a la
 *      cuenta; darle un cartel verde por no haber hecho nada es peor que no
 *      dejarlo.
 */

import { cpfAbreviado } from './envioABrasil.js';
import { rutaDeArchivo } from './urlDeArchivo.js';
import { validarPassword } from './passwordPolicy.js';

/* ─── Identidad ────────────────────────────────────────────────────────── */

/**
 * La foto de perfil, si se puede mostrar.
 *
 * Hoy NINGUNA ruta del backend escribe este campo, así que en la práctica
 * siempre se cae en las iniciales. No se saca la rama porque el modelo lo
 * declara y el panel de administración ya lo lee: el día que se cargue una
 * foto, esto la muestra —y la muestra pasada por la lista de lo permitido—.
 */
export function fotoDePerfil(user) {
  return rutaDeArchivo(user?.profile_picture) || null;
}

/** El nombre que se muestra. `full_name` es el legal; `name`, el de la cuenta. */
export function nombreVisible(user) {
  return user?.full_name || user?.name || 'Sin nombre';
}

/** El CPF tapado, con la misma regla que el flujo de Brasil. */
export function cpfDelPerfil(user) {
  const bruto = user?.cpf_number;
  return bruto ? cpfAbreviado(bruto) : null;
}

/* ─── El estado de la verificación ─────────────────────────────────────── */

/**
 * Qué decir del estado del KYC, y con qué tono.
 *
 * El tono sale del sistema visual compartido (`Aviso`/paleta `C`) en vez de
 * cuatro colores escritos a mano, que era lo que había: así el verde de acá es
 * el mismo verde que el de los tres flujos de envío.
 */
export function estadoDeVerificacion(estado) {
  switch (estado) {
    case 'verified':
      return { clave: 'verificado', texto: 'Verificado', tono: 'exito' };
    case 'pending':
      return { clave: 'pendiente', texto: 'En revisión', tono: 'alerta' };
    case 'rejected':
      return { clave: 'rechazado', texto: 'Rechazado', tono: 'error' };
    default:
      return { clave: 'sin_verificar', texto: 'Sin verificar', tono: 'neutro' };
  }
}

/** ¿Se le ofrece verificar la identidad? Rechazado también: puede reintentar. */
export function convieneVerificar(user) {
  return estadoDeVerificacion(user?.verification_status).clave !== 'verificado';
}

/* ─── El cambio de contraseña ──────────────────────────────────────────── */

/**
 * Todo lo que impide guardar la contraseña nueva, comprobado ANTES de llamar.
 *
 * Devuelve el mensaje, o null si se puede guardar. El orden importa y es el
 * mismo criterio que en los flujos de envío: primero el problema más concreto.
 * Si la contraseña nueva no cumple la política Y además no coincide con la
 * repetición, decir «no coinciden» lo manda a corregir la repetición de una
 * contraseña que igual iba a ser rechazada.
 *
 * La política sale de `passwordPolicy.js`, que espeja a `validate_password()`
 * del backend. Acá no se escribe ninguna regla nueva.
 */
export function problemaDelCambioDeClave({ actual, nueva, repetida }) {
  if (!actual) return 'Escribí tu contraseña actual.';
  if (!nueva) return 'Escribí la contraseña nueva.';

  // El servidor no mira esto, y es el caso que más engaña: se cambia la
  // contraseña por la misma, sale el cartel de éxito, y la cuenta quedó igual.
  if (nueva === actual) return 'La contraseña nueva tiene que ser distinta de la actual.';

  const problema = validarPassword(nueva);
  if (problema) return problema;

  if (nueva !== repetida) return 'La contraseña nueva y su repetición no coinciden.';
  return null;
}

/* ─── Las notificaciones ───────────────────────────────────────────────── */

/**
 * Por qué no se pueden activar las notificaciones, en una frase que diga qué
 * hacer.
 *
 * Antes había dos mensajes y ninguno cubría el caso más común: el permiso
 * DENEGADO en el navegador. Ahí el interruptor se veía apagado y clickearlo no
 * hacía nada visible —el navegador ya no vuelve a preguntar—, así que el
 * usuario clickeaba y clickeaba sin entender.
 */
export function motivoSinNotificaciones(info) {
  if (!info) return null;
  if (info.isIOS && !info.isPWA) {
    return 'En iPhone o iPad hay que instalar la aplicación primero: en Safari, «Compartir» → «Agregar a inicio».';
  }
  if (info.permission === 'denied') {
    return 'Bloqueaste las notificaciones para este sitio. El navegador no vuelve a preguntar: hay que habilitarlas desde el candado de la barra de direcciones.';
  }
  if (!info.serviceWorker || !info.pushManager || !info.notification) {
    return 'Este navegador no admite notificaciones.';
  }
  return null;
}

/* ─── El rol ───────────────────────────────────────────────────────────── */

/**
 * El panel al que lleva el rol, si lleva a alguno.
 *
 * Estaban los cuatro casos escritos como cuatro bloques de JSX casi iguales,
 * cada uno con su degradado. Acá es una tabla: agregar un rol es una línea, y
 * la pantalla no crece.
 */
const PANELES = {
  socio: {
    titulo: 'Panel de Socio',
    detalle: 'Tus referidos y tus ganancias',
    destino: '/partner',
  },
  socio_gestor: {
    titulo: 'Panel Gestor',
    detalle: 'Procesar envíos de terceros',
    destino: '/gestor',
  },
  admin: {
    titulo: 'Administrador',
    detalle: 'Acceder al panel de administración',
    destino: '/admin',
  },
  super_admin: {
    titulo: 'SuperAdministrador',
    detalle: 'Acceso total al sistema',
    destino: '/admin',
  },
};

export function panelDelRol(rol) {
  return PANELES[rol] || null;
}
