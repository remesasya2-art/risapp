/**
 * ticket.js — El papel que se pega en la caja antes de que salga a Santa Elena.
 *
 * QUE PROBLEMA RESUELVE
 *   La caja viaja sola. En el mostrador de destino alguien la agarra, la mira, y
 *   con lo que dice ese papel decide dos cosas: a quien se la entrega y si le
 *   cobra el flete. Si el papel no lo dice, lo tiene que averiguar por telefono
 *   con la caja en la mano y otras veinte esperando.
 *
 * POR QUE SE LEE DE PARADO
 *   Nadie lee esto sentado. Se lee a un brazo de distancia, con mala luz, a
 *   veces con la caja apoyada en el piso. Por eso el nombre de quien recibe va
 *   en cuerpo 34 y no en 14, y por eso lo que decide si se cobra o no va en una
 *   banda que ocupa un cuarto de la hoja.
 *
 * POR QUE NO USA COLOR PARA DECIR LO IMPORTANTE
 *   Esto se imprime en la impresora que haya. Una banda roja sale gris en blanco
 *   y negro, y gris no distingue nada. Las dos bandas de pago se diferencian por
 *   FORMA —una es solida invertida, la otra es un marco grueso vacio— asi que se
 *   distinguen igual en una laser vieja.
 *
 * POR QUE SE ARMA CON textContent Y NO CON UN TEMPLATE DE STRINGS
 *   El nombre de quien recibe y la direccion los escribio una persona. Meterlos
 *   en un `innerHTML` es dejar que un nombre con `<script>` corra en una ventana
 *   con la sesion del operador. Aca el HTML es una cascara fija y los datos
 *   entran SIEMPRE por `textContent`, que no interpreta nada.
 */

const HOJA = `
  @page { size: A4; margin: 12mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: Arial, Helvetica, sans-serif; color: #000;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .hoja { border: 3px solid #000; padding: 0; }
  .cab {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 8px 14px; border-bottom: 3px solid #000; font-size: 15px;
  }
  .cab b { font-size: 26px; letter-spacing: 1px; }
  .bloque { padding: 14px; border-bottom: 3px solid #000; }
  .rotulo {
    font-size: 13px; letter-spacing: 3px; text-transform: uppercase;
    margin: 0 0 6px 0; font-weight: 700;
  }
  .enorme { font-size: 34px; font-weight: 800; line-height: 1.1; margin: 0;
            word-break: break-word; }
  .grande { font-size: 22px; font-weight: 700; line-height: 1.25; margin: 4px 0 0 0; }
  .medio  { font-size: 18px; line-height: 1.3; margin: 2px 0 0 0; }
  .vacio  { font-style: italic; font-weight: 400; }

  /* Las dos bandas de pago. Se distinguen por FORMA, no por color. */
  .pago { padding: 18px 14px; text-align: center; border-bottom: 3px solid #000; }
  .pago .que { font-size: 30px; font-weight: 800; line-height: 1.15; margin: 0; }
  .pago .detalle { font-size: 16px; margin: 8px 0 0 0; }
  .pago.cobrar { background: #000; color: #fff; }
  .pago.nocobrar { background: #fff; color: #000; box-shadow: inset 0 0 0 6px #000; }

  /* El aviso de que la caja no puede salir. Arriba de todo y del ancho entero. */
  .freno {
    background: #000; color: #fff; text-align: center; padding: 12px;
    font-size: 24px; font-weight: 800; letter-spacing: 1px;
    border-bottom: 3px solid #000;
  }
  .pie { padding: 10px 14px; font-size: 15px; display: flex; gap: 26px;
         flex-wrap: wrap; }
  [hidden] { display: none !important; }
`;

// La cascara. NO lleva un solo dato adentro: todos entran despues por
// textContent. Ver el encabezado del archivo.
const CASCARA = `
  <div class="hoja">
    <div class="freno" id="freno" hidden></div>
    <div class="cab">
      <b id="display"></b>
      <span id="objeto"></span>
    </div>

    <div class="bloque">
      <p class="rotulo">Entregar a</p>
      <p class="enorme" id="nombre"></p>
      <p class="grande" id="documento"></p>
      <p class="grande" id="telefono"></p>
    </div>

    <div class="bloque">
      <p class="rotulo">Agencia de destino</p>
      <p class="grande" id="agencia"></p>
      <p class="medio" id="direccion"></p>
      <p class="medio" id="ciudad"></p>
    </div>

    <div class="pago" id="pago">
      <p class="que" id="pagoQue"></p>
      <p class="detalle" id="pagoDetalle"></p>
    </div>

    <div class="pie">
      <span id="peso"></span>
      <span id="contenido"></span>
    </div>
  </div>
`;

/** Texto, o un guión y en itálica cuando el dato no está. Nunca un renglón en
 *  blanco: un renglón vacío se lee como «acá no dice nada» y manda a preguntar;
 *  «(sin dirección cargada)» se lee como «esto falta» y manda a completarlo. */
function poner(doc, id, texto, faltante) {
  const el = doc.getElementById(id);
  if (!el) return;
  const valor = (texto || '').toString().trim();
  el.textContent = valor || faltante || '—';
  el.classList.toggle('vacio', !valor);
}

/**
 * Abre una ventana con el ticket listo para imprimir.
 * @param t La respuesta de `GET /admin/envios/envios/{id}/ticket`.
 * @returns null si el navegador bloqueó la ventana, para que quien llama avise.
 */
export function imprimirTicket(t) {
  const v = window.open('', '_blank', 'width=800,height=1000');
  if (!v) return null;

  const doc = v.document;
  doc.open();
  // El título es lo que sale en el encabezado de la impresión y en el nombre del
  // PDF si lo guardan. Que diga el envío y no "about:blank".
  doc.write('<!doctype html><html lang="es"><head><meta charset="utf-8">'
    + '<title></title><style></style></head><body></body></html>');
  doc.close();

  doc.querySelector('title').textContent = `Ticket ${t.display_id || t.envio_id || ''}`;
  doc.querySelector('style').textContent = HOJA;
  doc.body.innerHTML = CASCARA;          // cáscara fija, sin un solo dato

  poner(doc, 'display', t.display_id || t.envio_id);
  poner(doc, 'objeto', t.codigo_objeto, '(sin código de objeto)');

  const d = t.destinatario || {};
  poner(doc, 'nombre', d.nombre, '(SIN NOMBRE — NO ENTREGAR)');
  poner(doc, 'documento', d.documento, '(sin documento)');
  poner(doc, 'telefono', d.telefono, '(sin teléfono)');

  const a = t.agencia || {};
  poner(doc, 'agencia', [a.nombre, a.transportista].filter(Boolean).join(' · '),
    '(sin agencia)');
  poner(doc, 'direccion', a.direccion, '(sin dirección cargada — preguntar)');
  poner(doc, 'ciudad', [a.ciudad, a.estado_ve].filter(Boolean).join(', '));

  // Lo que decide qué pasa en el mostrador.
  const pago = t.pago || {};
  const caja = doc.getElementById('pago');
  if (pago.cobrar_al_recibir) {
    caja.className = 'pago cobrar';
    poner(doc, 'pagoQue', 'COBRAR EL FLETE AL ENTREGAR');
    poner(doc, 'pagoDetalle',
      'El flete del tramo final lo paga quien recibe, en el mostrador.');
  } else {
    caja.className = 'pago nocobrar';
    poner(doc, 'pagoQue', 'FLETE YA PAGADO — NO COBRAR NADA');
    // Cobrar de nuevo es cobrar dos veces el mismo tramo, y se lo cobra a
    // alguien que ya pagó. De los dos errores posibles, es el caro.
    poner(doc, 'pagoDetalle', pago.flete_monto_ris
      ? `Remesa por ${pago.flete_monto_ris} RIS, ya acreditada.`
      : 'El remitente pagó el flete por remesa.');
  }

  const p = t.paquete || {};
  poner(doc, 'peso', p.peso_kg
    ? `${p.peso_kg} kg (${p.peso_es_verificado ? 'balanza propia' : 'declarado'})`
    : '', '(sin peso)');
  poner(doc, 'contenido', p.contenido, '(sin contenido declarado)');

  const freno = doc.getElementById('freno');
  if (t.puede_salir === false) {
    freno.hidden = false;
    // El papel se imprime ANTES de cargar la camioneta. Uno que se ve igual con
    // la partida impaga es un papel que ayuda a despachar lo que no se puede.
    freno.textContent = 'NO DESPACHAR — TIENE UNA PARTIDA IMPAGA';
  }

  v.focus();
  // El navegador tiene que haber pintado antes de imprimir, si no sale una hoja
  // en blanco en algunos.
  v.setTimeout(() => v.print(), 250);
  return v;
}
