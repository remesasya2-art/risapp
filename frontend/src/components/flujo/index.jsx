/**
 * flujo/index.jsx — Las piezas de los flujos que mueven dinero.
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
import { Check, Info, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react';
import { C } from './estilos';

/* ─── Piezas ───────────────────────────────────────────────────────────── */

function Boton(props) {
  const { children, onClick, tipo = 'secundario', disabled, ancho, testid, iconoDerecha } = props;
  const Icono = props.Icono;
  const paleta = {
    primario: { background: C.marca, color: '#fff', border: `1px solid ${C.marca}` },
    exito: { background: C.exito, color: '#fff', border: `1px solid ${C.exito}` },
    secundario: { background: C.lienzo, color: C.texto, border: `1px solid ${C.lineaFuerte}` },
  }[tipo];

  return (
    <button
      type="button" onClick={onClick} disabled={disabled} data-testid={testid}
      className={`env-tap${tipo === 'primario' ? ' env-pri' : ''}`}
      style={{
        ...paleta, height: '52px', padding: '0 20px', borderRadius: '12px',
        fontWeight: 600, fontSize: '15.5px', cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        gap: '9px', flex: ancho ? 1 : undefined, whiteSpace: 'nowrap',
        opacity: disabled ? 0.5 : 1,
      }}>
      {Icono && !iconoDerecha ? <Icono size={18} /> : null}
      {children}
      {Icono && iconoDerecha ? <Icono size={18} /> : null}
    </button>
  );
}

function Aviso({ tono = 'info', titulo, children, testid }) {
  const [fondo, borde, color, Icono] = {
    info: [C.marcaSuave, C.marcaBorde, C.marca, Info],
    exito: [C.exitoSuave, C.exitoBorde, C.exito, CheckCircle2],
    alerta: [C.alertaSuave, C.alertaBorde, C.alerta, AlertTriangle],
    error: [C.errorSuave, C.errorBorde, C.error, AlertCircle],
  }[tono];
  return (
    <div data-testid={testid} style={{
      display: 'flex', gap: '11px', alignItems: 'flex-start',
      background: fondo, border: `1px solid ${borde}`,
      borderRadius: '12px', padding: '13px 15px',
    }}>
      <Icono size={18} color={color} style={{ flexShrink: 0, marginTop: '1px' }} />
      <div style={{ fontSize: '13.5px', lineHeight: 1.55, color: C.texto }}>
        {titulo ? (
          <strong style={{ display: 'block', color, marginBottom: '2px' }}>{titulo}</strong>
        ) : null}
        {children}
      </div>
    </div>
  );
}

function Progreso({ pasos, paso, alcanzable, irA }) {
  return (
    <ol style={{
      display: 'grid', gridTemplateColumns: `repeat(${pasos.length}, 1fr)`,
      gap: '8px', listStyle: 'none', margin: '0 0 18px 0', padding: 0,
    }}>
      {pasos.map((p) => {
        const hecho = paso > p.numero;
        const actual = paso === p.numero;
        const puede = p.numero <= alcanzable;
        return (
          <li key={p.clave}>
            <button
              type="button" className="env-paso" disabled={!puede}
              onClick={() => puede && irA(p.numero)}
              aria-current={actual ? 'step' : undefined}
              aria-label={`Paso ${p.numero}: ${p.titulo}`}
              style={{
                width: '100%', border: 'none', background: 'none', padding: 0,
                textAlign: 'left', cursor: puede ? 'pointer' : 'default',
              }}>
              <span style={{
                display: 'block', height: '4px', borderRadius: '2px',
                background: actual || hecho ? C.marca : C.linea, marginBottom: '7px',
              }} />
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{
                  width: '18px', height: '18px', borderRadius: '50%', flexShrink: 0,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '10.5px', fontWeight: 700,
                  background: hecho ? C.marca : (actual ? C.marcaSuave : C.linea),
                  color: hecho ? '#fff' : (actual ? C.marca : C.tenue),
                }}>
                  {hecho ? <Check size={11} strokeWidth={3} /> : p.numero}
                </span>
                <span className="env-nom-paso" style={{
                  fontSize: '12.5px', fontWeight: actual ? 700 : 500,
                  color: actual ? C.tinta : C.tenue, whiteSpace: 'nowrap',
                }}>{p.titulo}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Opcion(props) {
  const { elegida, onClick, titulo, detalle, testid } = props;
  const Icono = props.Icono;
  return (
    <button
      type="button" role="radio" aria-checked={elegida} onClick={onClick}
      data-testid={testid} className="env-op env-tap"
      style={{
        display: 'flex', alignItems: 'center', gap: '14px', width: '100%',
        padding: '16px', borderRadius: '14px', textAlign: 'left', cursor: 'pointer',
        border: `1px solid ${elegida ? C.marca : C.linea}`,
        background: elegida ? C.marcaSuave : C.lienzo,
        boxShadow: elegida ? '0 0 0 3px rgba(79,70,229,.10)' : 'none',
      }}>
      <span style={{
        width: '44px', height: '44px', borderRadius: '12px', flexShrink: 0,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: elegida ? C.marca : C.fondo,
      }}>
        <Icono size={21} color={elegida ? '#fff' : C.suave} />
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: 'block', fontSize: '15.5px', fontWeight: 700, color: C.tinta }}>
          {titulo}
        </span>
        <span style={{ display: 'block', fontSize: '13px', color: C.suave, marginTop: '2px' }}>
          {detalle}
        </span>
      </span>
      <span style={{
        width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
        border: `2px solid ${elegida ? C.marca : C.lineaFuerte}`,
        background: elegida ? C.marca : 'transparent',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {elegida ? <Check size={12} color="#fff" strokeWidth={3} /> : null}
      </span>
    </button>
  );
}

export { Boton, Aviso, Progreso, Opcion };
