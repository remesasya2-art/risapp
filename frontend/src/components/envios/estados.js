/**
 * estados.js — Cómo se le nombra al usuario cada punto del circuito.
 *
 * LOS TEXTOS SALEN DEL SERVIDOR, NO DE ACA
 *   `/envios/seguimiento/{token}` y el detalle mandan `estado_titulo` y
 *   `estado_detalle` ya escritos: son la misma tabla que usa el aviso por
 *   correo, y duplicarla acá sería garantizar que un día digan cosas distintas.
 *
 *   Lo que sí vive acá es lo VISUAL —el color y si el paso pide algo del
 *   usuario— porque eso no tiene sentido del lado del servidor.
 */
import { COLOR } from './estilos';

/** Los estados en los que la pelota está del lado del usuario. */
export const PIDE_ALGO = {
  esperando_postagem: 'Despachá el paquete y cargá el comprobante.',
  pago_pendiente: 'Hay un cobro pendiente. El paquete espera hasta que se salde.',
};

const VERDE = { fondo: COLOR.okSuave, borde: '#a7f3d0', texto: '#065f46' };
const AZUL = { fondo: COLOR.primarioSuave, borde: '#c7d2fe', texto: '#3730a3' };
const AMBAR = { fondo: COLOR.alertaSuave, borde: '#fde68a', texto: '#92400e' };
const ROJO = { fondo: COLOR.errorSuave, borde: '#fecaca', texto: '#991b1b' };
const GRIS = { fondo: '#f3f4f6', borde: COLOR.borde, texto: COLOR.suave };

export const TONO = {
  cotizado: GRIS,
  esperando_postagem: AMBAR,
  en_transito_origen: AZUL,
  disponible_retiro: AZUL,
  recibido_pacaraima: AZUL,
  repesado: AZUL,
  pago_pendiente: AMBAR,
  en_transito_int: AZUL,
  entregado_transportista: VERDE,
  retenido: AMBAR,
  devuelto: ROJO,
  siniestrado: ROJO,
  cancelado: GRIS,
};

export const tonoDe = (estado) => TONO[estado] || GRIS;

/** Un título de respaldo, solo para cuando el servidor no manda el suyo. */
export const TITULOS = {
  cotizado: 'Cotizado',
  esperando_postagem: 'Esperando el despacho',
  en_transito_origen: 'En camino a la frontera',
  disponible_retiro: 'Esperando en Pacaraima',
  recibido_pacaraima: 'Retirado por nuestro equipo',
  repesado: 'Pesado y listo',
  pago_pendiente: 'Esperando un pago',
  en_transito_int: 'En camino a Santa Elena',
  entregado_transportista: 'Entregado al transportista',
  retenido: 'Retenido',
  devuelto: 'Devuelto al remitente',
  siniestrado: 'Siniestrado',
  cancelado: 'Cancelado',
};
