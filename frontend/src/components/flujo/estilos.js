/**
 * flujo/estilos.js — Los valores del sistema visual de los flujos que mueven dinero.
 *
 * DE DONDE SALE
 *
 *   Estaba escrito adentro de `Send.jsx` —enviar a Venezuela— y se movió acá
 *   tal cual, sin cambiarle un valor, para que el flujo de BTC Lightning use
 *   EXACTAMENTE el mismo y no uno parecido.
 *
 *   El único cambio: `Progreso` recibe sus pasos por propiedad. Antes los
 *   importaba del módulo de Venezuela, y los del flujo BTC son otros.
 *
 * POR QUE COMPARTIRLO Y NO COPIARLO
 *
 *   Dos pantallas que hacen lo mismo —elegir a quién, cuánto, y confirmar—
 *   tienen que verse iguales, y con estilos copiados eso dura hasta el primer
 *   retoque en una sola de las dos. El usuario no ve «dos flujos parecidos»:
 *   ve una aplicación que en una pantalla está cuidada y en la otra no.
 *
 * EL CRITERIO, QUE VIENE DE SEND.JSX
 *
 *   Profesional pero amigable. Esto lo usa alguien desde el teléfono,
 *   probablemente apurado, mandándole plata a su familia. Serio quiere decir
 *   que se entienda de una y que no haya sorpresas; no quiere decir austero.
 *
 *     · Los pasos tienen NOMBRE, no sólo número, y se puede volver tocando uno
 *       ya hecho.
 *     · Los blancos y grises hacen el trabajo; el color aparece sólo donde
 *       significa algo: lo que recibe, un aviso, un error.
 *     · Nada de degradados de fondo: distraen de la cifra, que es lo único que
 *       la persona vino a mirar.
 *
 * EL PREFIJO `env`
 *
 *   Las clases de la hoja de estilos se llaman `env-...` porque nacieron en el
 *   flujo de envíos. Es sólo un espacio de nombres; renombrarlas obligaría a
 *   tocar cada `className` de una pantalla que ya funciona, y eso es riesgo sin
 *   beneficio. Se deja dicho para que nadie lo lea como que esto es «del
 *   módulo de envíos».
 */

/* ─── Sistema visual ───────────────────────────────────────────────────── */

const C = {
  tinta: '#101828', texto: '#344054', suave: '#667085', tenue: '#98A2B3',
  linea: '#E4E7EC', lineaFuerte: '#D0D5DD',
  lienzo: '#FFFFFF', fondo: '#F7F8FA',
  marca: '#4F46E5', marcaSuave: '#EEF0FF', marcaBorde: '#C7CDFF',
  exito: '#067647', exitoSuave: '#ECFDF3', exitoBorde: '#A9EFC5',
  alerta: '#B54708', alertaSuave: '#FFFAEB', alertaBorde: '#FEDF89',
  error: '#B42318', errorSuave: '#FEF3F2', errorBorde: '#FECDCA',
};

const HOJA = `
.env { color: ${C.texto}; font-variant-numeric: tabular-nums lining-nums; }
.env * { box-sizing: border-box; }
.env button { font-family: inherit; }
.env .env-tap { transition: border-color .13s ease, background-color .13s ease, box-shadow .13s ease; }
.env .env-tap:hover:not(:disabled) { border-color: ${C.lineaFuerte}; }
.env .env-op:hover:not([aria-checked="true"]) { border-color: ${C.marcaBorde}; background: ${C.marcaSuave}; }
.env .env-pri:hover:not(:disabled) { background: #4338CA; }
.env .env-campo:focus { border-color: ${C.marca}; box-shadow: 0 0 0 4px rgba(79,70,229,.12); }
.env input:focus { outline: none; }
/* Las flechitas del <input type=number>: al lado de una cifra grande y
   centrada se ven como un control de formulario viejo, y encima invitan a
   cambiar un monto de a uno. Se escribe el número. */
.env input[type=number] { -moz-appearance: textfield; appearance: textfield; }
.env input[type=number]::-webkit-outer-spin-button,
.env input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.env :focus-visible { outline: 2px solid ${C.marca}; outline-offset: 2px; }
.env .env-chip:hover { background: ${C.marcaSuave}; border-color: ${C.marcaBorde}; color: ${C.marca}; }
.env .env-paso:disabled { cursor: default; }
@media (max-width: 560px) {
  .env .env-dos { grid-template-columns: 1fr !important; }
  .env .env-nom-paso { font-size: 11.5px; letter-spacing: -.01em; }
}
@media (max-width: 359px) {
  .env .env-nom-paso { display: none; }
}
`;

const tarjeta = {
  background: C.lienzo, borderRadius: '16px', border: `1px solid ${C.linea}`,
  boxShadow: '0 1px 2px rgba(16,24,40,.04)',
};

const etiqueta = {
  display: 'block', fontSize: '13.5px', fontWeight: 600,
  color: C.texto, marginBottom: '7px',
};

const microEtiqueta = {
  margin: 0, fontSize: '11px', fontWeight: 700, letterSpacing: '.06em',
  textTransform: 'uppercase', color: C.tenue,
};

const campo = {
  width: '100%', padding: '13px 15px', borderRadius: '12px',
  border: `1px solid ${C.lineaFuerte}`, fontSize: '16px', color: C.tinta,
  background: C.lienzo, outline: 'none',
};

const ayuda = { margin: '6px 0 0 0', fontSize: '12px', color: C.suave };


export function iniciales(nombre) {
  const partes = String(nombre || '').trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return '?';
  return (partes[0][0] + (partes[1]?.[0] || '')).toUpperCase();
}

export { C, HOJA, tarjeta, etiqueta, microEtiqueta, campo, ayuda };
