/**
 * OperacionPanel.jsx — El panel del operador: la cola de Pacaraima.
 *
 * ESTA ES LA PANTALLA QUE SE USA TODOS LOS DIAS
 *   El panel de configuración se carga una vez en la vida del sistema. Este se
 *   abre cada mañana, muchas veces parado en un mostrador. Por eso cada pestaña
 *   tiene UNA acción principal y el paquete avanza de izquierda a derecha.
 *
 * QUIEN ENTRA ACA
 *   El operador y cualquier administrador, **el super administrador incluido**:
 *   pasa por `get_crm_user` y por `get_admin_user`, así que puede hacer todas
 *   las tareas de operador sin excepción. La separación de roles del módulo
 *   corre en el otro sentido — el que viaja a Pacaraima y pesa cajas no puede
 *   cambiar los precios ni la cuenta que recibe los fletes, y esa mitad vive en
 *   la pestaña de configuración, que sí es solo del super administrador.
 *
 *   Un rol `agent` —soporte de chat— ve la cola y puede mover paquetes, pero
 *   **cuatro rutas le contestan 403**: verificar y repesar, que mueven saldo, y
 *   desviar y acreditar el flete, que abren consecuencias que no se deshacen.
 *   La pantalla NO las esconde por rol: prefiere que el error venga del servidor
 *   antes que inventar acá una regla de permisos que después se separe de la de
 *   verdad y deje a alguien mirando un botón que no existe — o peor, sin un
 *   botón que sí le corresponde.
 *
 * LA COLA VIENE AGRUPADA POR EL NOMBRE ROTULADO, Y ESO IMPORTA EN UN SOLO LUGAR
 *   En el mostrador comparan la etiqueta contra un documento. Quien viaja
 *   necesita saber cuáles cajas puede reclamar ÉL — y eso lo dice el nombre
 *   congelado en cada envío, no quién esté de turno hoy. En las demás paradas el
 *   agrupamiento es ruido, así que la lista va plana.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Boxes, ChevronDown, ChevronRight, Clock, RefreshCw, ScanLine,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { fmt } from '../../../utils/format';
import AccionesDeEnvio from './AccionesDeEnvio';
import { Aviso, Boton, Campo, Cargando, NoSePudoLeer, Texto, Vacio, Area } from './ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from './estilos';
import { MOTIVOS_DE_RECHAZO, PARADAS, POR_ESTADO } from './operacion';

const ESTADOS = PARADAS.map((p) => p.estado);

export default function OperacionPanel() {
  const [params, setParams] = useSearchParams();
  const pedido = params.get('cola');
  const estado = ESTADOS.includes(pedido) ? pedido : ESTADOS[0];
  const parada = POR_ESTADO[estado];

  const [cola, setCola] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const [abierto, setAbierto] = useState(null);
  const [ultimo, setUltimo] = useState(null);
  // Los borradores de medidas, por envío. Viven acá y no en la fila: abrir otra
  // caja para comparar desmontaba el formulario y se perdían tres de las cuatro
  // medidas ya tipeadas, sin ningún aviso.
  const [borradores, setBorradores] = useState({});

  // Un NUMERO de petición, no un booleano. Con un `vivo` compartido, cambiar de
  // parada lo ponía en false y el efecto nuevo en true de inmediato: la
  // respuesta vieja llegaba segunda, se encontraba con `vivo === true`, y
  // pintaba la cola de «por verificar» abajo del rótulo «por repesar», con el
  // formulario de repesaje sobre paquetes que todavía viajaban por Brasil.
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    try {
      const res = await api.get('/admin/envios/envios/cola', { params: { estado } });
      if (mia !== peticion.current) return;
      setNoSeLeyo(null);
      setCola(res.data);
    } catch (err) {
      if (mia !== peticion.current) return;
      // La cola degrada con 200 y `degradado: true`, así que casi nunca cae acá
      // por una base caída; sí por un 403 o un 5xx del proxy. Un problema de
      // permisos que se lea como «no hay trabajo» es peor que un error.
      setNoSeLeyo(mensajeDeError(err, esFallaDeLectura(err)
        ? 'La base no contestó.' : 'El servidor rechazó la consulta.'));
    } finally {
      if (mia === peticion.current) setCargando(false);
    }
  }, [estado]);

  useEffect(() => {
    (async () => { await cargar(); })();
    return () => { peticion.current += 1; };
  }, [cargar]);

  const ir = (siguiente) => {
    setCargando(true);
    setAbierto(null);
    setParams((previos) => {
      const p = new URLSearchParams(previos);
      p.set('cola', siguiente);
      return p;
    }, { replace: true });
  };

  const refrescar = (resultado) => {
    if (resultado) {
      setUltimo(resultado);
      // El borrador de ese envío ya se usó: si quedara, la próxima vez que se
      // abra la fila mostraría medidas viejas como si estuvieran sin mandar.
      setBorradores((b) => {
        const copia = { ...b };
        delete copia[resultado.envio.envio_id];
        return copia;
      });
    }
    setCargando(true);
    cargar();
  };
  const grupos = cola?.grupos || [];
  const filas = grupos.flatMap((g) => g.envios);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {PARADAS.map((p) => {
          const activa = p.estado === estado;
          return (
            <button key={p.estado} type="button" onClick={() => ir(p.estado)}
              style={{ padding: '8px 14px', borderRadius: '10px', fontSize: '14px',
                fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${activa ? COLOR.primario : COLOR.borde}`,
                backgroundColor: activa ? COLOR.primarioSuave : '#fff',
                color: activa ? COLOR.primarioOscuro : COLOR.suave }}>
              {p.etiqueta}
            </button>
          );
        })}
      </div>

      <div style={{ ...tarjeta, display: 'flex', gap: '14px', alignItems: 'flex-start',
        flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 300px' }}>
          <h3 style={{ ...titulo, margin: 0 }}>
            <Boxes size={16} /> {parada.etiqueta}
            {cola ? (
              <span style={{ fontWeight: 600, color: COLOR.suave }}>· {cola.total}</span>
            ) : null}
            {parada.mueveSaldo ? (
              <span style={{ fontSize: '11px', fontWeight: 700, padding: '3px 9px',
                borderRadius: '999px', backgroundColor: COLOR.alertaSuave,
                color: '#92400e', border: '1px solid #fde68a' }}>
                mueve saldo
              </span>
            ) : null}
          </h3>
          <p style={{ ...bajada, margin: '6px 0 0 0' }}>{parada.resumen}</p>
        </div>
        <Boton variante="secundario" onClick={refrescar} cargando={cargando}>
          <RefreshCw size={14} /> Actualizar
        </Boton>
      </div>

      {ultimo ? <Resultado resultado={ultimo} onCerrar={() => setUltimo(null)} /> : null}

      {cola?.hay_mas ? (
        <Aviso tono="alerta" titulo="Hay más de los que entran en esta lista">
          Se muestran los {cola.total} más viejos. Resolvé estos y actualizá: si armás el
          viaje solo con lo que ves, las cajas que quedaron afuera siguen consumiendo días de
          guarda.
        </Aviso>
      ) : null}

      {estado === 'disponible_retiro' ? <RetiroPorLote onListo={refrescar} /> : null}

      {cargando && !cola ? <Cargando texto="Leyendo la cola…" /> : null}

      {/*
        «No se pudo leer» reemplaza a la lista, no la acompaña. La cola degrada
        con 200 y `grupos: []`, así que antes se veían las dos cosas juntas: el
        aviso de que la lista podía estar incompleta y, debajo, el cartel
        afirmando que no hay ningún paquete en esta parada.
      */}
      {noSeLeyo || cola?.degradado ? (
        <NoSePudoLeer que="la cola"
          detalle={noSeLeyo || 'El servidor contestó, pero no pudo leer los envíos.'}
          onReintentar={() => refrescar()} reintentando={cargando} />
      ) : null}

      {!cargando && !noSeLeyo && !cola?.degradado && filas.length === 0 ? (
        <Vacio titulo="No hay nada en esta parada">
          Cuando llegue un paquete a este punto del circuito, va a aparecer acá.
        </Vacio>
      ) : null}

      {!cola?.degradado && parada.agrupar
        ? grupos.map((g) => (
          <div key={g.retirador_nombre}>
            <h4 style={{ ...titulo, fontSize: '13px', margin: '4px 0 8px 0',
              color: COLOR.suave, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              A nombre de {g.retirador_nombre} · {g.cuantos}
            </h4>
            {g.envios.map((e) => (
              <Fila key={e.envio_id} envio={e} parada={parada} abierto={abierto}
                setAbierto={setAbierto} onListo={refrescar}
                borrador={borradores[e.envio_id]}
                onBorrador={(m) => setBorradores((b) => ({ ...b, [e.envio_id]: m }))} />
            ))}
          </div>
        ))
        : cola?.degradado ? null : filas.map((e) => (
          <Fila key={e.envio_id} envio={e} parada={parada} abierto={abierto}
            setAbierto={setAbierto} onListo={refrescar}
            borrador={borradores[e.envio_id]}
            onBorrador={(m) => setBorradores((b) => ({ ...b, [e.envio_id]: m }))} />
        ))}
    </div>
  );
}

function Fila({ envio, parada, abierto, setAbierto, onListo, borrador, onBorrador }) {
  const expandido = abierto === envio.envio_id;
  const dias = envio.dias_de_guarda_restantes;
  const apremia = dias !== null && dias !== undefined && dias <= 7;
  // «No puede salir» solo significa algo donde el paquete tendría que estar
  // saliendo. En «por verificar» el paquete está viajando por Brasil y una deuda
  // no frena nada — pintar de rojo la mayoría de esas filas entrena al operador
  // a ignorar el rojo justo antes de la parada donde sí importa.
  const frena = !envio.puede_salir && ['repesado', 'pago_pendiente'].includes(parada.estado);

  return (
    <div style={{ ...tarjeta, padding: 0, overflow: 'hidden', marginBottom: '10px',
      borderColor: frena ? '#fecaca' : COLOR.borde }}>
      <button type="button"
        onClick={() => setAbierto(expandido ? null : envio.envio_id)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '12px',
          padding: '14px 18px', background: 'none', border: 'none', cursor: 'pointer',
          textAlign: 'left', flexWrap: 'wrap' }}>
        {expandido ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span style={{ flex: '1 1 220px', minWidth: 0 }}>
          <span style={{ fontSize: '14px', fontWeight: 700, color: COLOR.texto,
            fontFamily: 'monospace' }}>
            {envio.display_id || envio.envio_id}
          </span>
          <span style={{ display: 'block', fontSize: '12px', color: COLOR.suave }}>
            {envio.codigo_objeto ? `Objeto ${envio.codigo_objeto} · ` : ''}
            {envio.agencia_destino || 'Sin agencia'}
            {envio.estado_ve ? `, ${envio.estado_ve}` : ''}
          </span>
        </span>

        {dias !== null && dias !== undefined ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px',
            fontSize: '12px', fontWeight: 700, padding: '4px 10px', borderRadius: '999px',
            backgroundColor: apremia ? COLOR.errorSuave : '#f3f4f6',
            color: apremia ? '#991b1b' : COLOR.suave }}>
            <Clock size={12} />
            {dias < 0 ? `guarda vencida hace ${-dias} d` : `${dias} d de guarda`}
          </span>
        ) : null}

        {envio.foto_repetida_en ? (
          <span style={{ fontSize: '11px', fontWeight: 700, padding: '4px 10px',
            borderRadius: '999px', backgroundColor: COLOR.errorSuave, color: '#991b1b' }}>
            foto repetida
          </span>
        ) : null}

        {frena ? (
          <span style={{ fontSize: '11px', fontWeight: 700, padding: '4px 10px',
            borderRadius: '999px', backgroundColor: COLOR.errorSuave, color: '#991b1b' }}>
            no puede salir
          </span>
        ) : !envio.puede_salir ? (
          <span style={{ fontSize: '11px', fontWeight: 600, padding: '4px 10px',
            borderRadius: '999px', backgroundColor: '#f3f4f6', color: COLOR.suave }}>
            con partida pendiente
          </span>
        ) : null}
      </button>

      {expandido ? (
        <div style={{ padding: '0 18px 18px 18px', borderTop: `1px solid ${COLOR.borde}` }}>
          {parada.estado === 'en_transito_origen' ? (
            <MarcarDisponible envio={envio} onListo={onListo} />
          ) : null}
          <AccionesDeEnvio envio={envio} parada={parada} borrador={borrador}
            onBorrador={onBorrador} onListo={onListo} />
        </div>
      ) : null}
    </div>
  );
}

function MarcarDisponible({ envio, onListo }) {
  const [dias, setDias] = useState('');
  const [enviando, setEnviando] = useState(false);
  // `Number('45x')` es NaN, y JSON.stringify lo manda como null: Pydantic lo lee
  // como ausente y aplica el default en silencio. Para este campo, en silencio
  // es lo peor que puede pasar.
  const diasValidos = /^\d+$/.test(dias.trim())
    && Number(dias) >= 1 && Number(dias) <= 180;
  const diasMal = dias.trim() !== '' && !diasValidos;

  const marcar = async () => {
    setEnviando(true);
    try {
      const res = await api.post(`/admin/envios/envios/${envio.envio_id}/disponible`,
        diasValidos ? { dias_guarda: Number(dias) } : {});
      // Se muestra la fecha que quedó: para «el parámetro más caro del módulo»,
      // mandar un número y no ver el resultado es pedirle a alguien que confíe.
      const vence = res.data?.guarda_vence_at;
      toast.success(vence
        ? `Disponible. La guarda vence el ${new Date(vence).toLocaleDateString('es-AR')}.`
        : 'Marcado como disponible');
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo marcar.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ paddingTop: '16px' }}>
      <h4 style={titulo}><Clock size={16} /> Llegó al mostrador</h4>
      {!envio.comprobante_verificado ? (
        <Aviso tono="alerta" titulo="Todavía no está verificado" style={{ marginBottom: '12px' }}>
          Verificalo cuando puedas, pero <strong>no esperes a eso para marcarlo</strong>: el
          reloj de guarda responde a que la caja esté físicamente en el mostrador, y si no
          arranca, la agencia la devuelve al remitente sin que nadie lo vea venir.
        </Aviso>
      ) : null}
      <p style={bajada}>
        Esto <strong>arranca el reloj de guarda</strong>, que es el parámetro más caro del
        módulo: pasado el plazo la agencia devuelve el paquete al remitente, con el costo del
        retorno y un usuario que ya pagó.
      </p>
      <div style={grilla('200px')}>
        <Campo etiqueta="Días de guarda"
          ayuda="Vacío = los que están configurados. Solo cambialo si esta agencia dio otro plazo."
          error={diasMal ? 'Un número entero entre 1 y 180.' : null}>
          <Texto inputMode="numeric" value={dias} invalido={diasMal}
            onChange={(e) => setDias(e.target.value)} placeholder="por configuración" />
        </Campo>
      </div>
      <Boton style={{ marginTop: '14px' }} onClick={marcar} cargando={enviando}
        disabled={diasMal}>
        <Clock size={14} /> Marcar disponible
      </Boton>
    </div>
  );
}

/**
 * El retiro por lote.
 *
 * POR CODIGO DE OBJETO, NO POR NUMERO DE ENVIO
 *   Es lo que está impreso en la caja que el operador tiene en la mano. Pedirle
 *   el número de envío sería pedirle que busque cada caja en una pantalla,
 *   parado en un mostrador con treinta cajas.
 *
 * UN CODIGO DESCONOCIDO NO ABORTA EL LOTE
 *   Vuelve en «rechazados» con su motivo. Que una caja no se reconozca no puede
 *   hacerle perder las veintinueve que sí.
 */
function RetiroPorLote({ onListo }) {
  const [texto, setTexto] = useState('');
  const [nota, setNota] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [informe, setInforme] = useState(null);

  // Deduplicados: un escáner que dispara dos veces manda el mismo código, el
  // segundo vuelve rechazado con motivo «estado», y el operador sale a buscar
  // una caja que ya tiene en la mano.
  const codigos = [...new Set(
    texto.split(/[\s,;]+/).map((c) => c.trim().toUpperCase()).filter(Boolean))];
  const leidos = texto.split(/[\s,;]+/).filter(Boolean).length;

  const retirar = async () => {
    setEnviando(true);
    // El informe del lote anterior se va ANTES de mandar: si el segundo falla, el
    // primero quedaba en pantalla y se leía como resultado del segundo.
    setInforme(null);
    try {
      const res = await api.post('/admin/envios/envios/retiro-lote', { codigos, nota });
      setInforme(res.data);
      setTexto('');
      setNota('');
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo retirar el lote.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={tarjeta}>
      <h3 style={titulo}><ScanLine size={16} /> Retirar del mostrador</h3>
      <p style={bajada}>
        Escaneá o pegá los códigos de objeto, uno por línea. Los que no se reconozcan vuelven
        listados con el motivo — <strong>no frenan a los demás</strong>.
      </p>
      <Area value={texto} filas={5} placeholder={'AA123456789BR\nAA987654321BR'}
        onChange={(e) => setTexto(e.target.value)}
        style={{ fontFamily: 'monospace', fontSize: '13px' }} />
      <div style={{ ...grilla('240px'), marginTop: '12px' }}>
        <Campo etiqueta="Nota del lote" ayuda="Opcional. Queda en la bitácora del viaje.">
          <Texto value={nota} maxLength={300} onChange={(e) => setNota(e.target.value)} />
        </Campo>
      </div>
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '14px',
        flexWrap: 'wrap' }}>
        <Boton onClick={retirar} cargando={enviando}
          disabled={codigos.length === 0 || codigos.length > 200}>
          <ScanLine size={14} /> Retirar {codigos.length || ''}
        </Boton>
        <span style={{ fontSize: '12px', color: codigos.length > 200 ? COLOR.error : COLOR.suave }}>
          {codigos.length > 200
            ? `${codigos.length} códigos: el máximo por lote son 200.`
            : `${codigos.length} código(s)`}
          {leidos > codigos.length ? ` · ${leidos - codigos.length} repetido(s), se manda uno solo` : ''}
        </span>
      </div>

      {informe ? (
        <Aviso tono={informe.cuantos_rechazados ? 'alerta' : 'ok'}
          style={{ marginTop: '14px' }}
          titulo={`${informe.cuantos} retirado(s), ${informe.cuantos_rechazados} rechazado(s)`}>
          <p style={{ margin: 0 }}>
            Lote <strong style={{ fontFamily: 'monospace' }}>{informe.lote_id}</strong>.
          </p>
          {informe.cuantos_rechazados ? (
            <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px' }}>
              {(informe.rechazados || []).map((r, i) => (
                <li key={i}>
                  <span style={{ fontFamily: 'monospace' }}>{r.codigo || r.codigo_objeto}</span>
                  {r.display_id ? ` (${r.display_id})` : ''}
                  {': '}
                  {/* `detalle` es la frase; `motivo` es un slug interno. Mostrar
                      el slug pelado le dejaba al operador una lista que decía
                      «estado», «carrera», «desconocido» — y todo el diseño de
                      «un rechazo no frena el lote» se apoya en que el rechazo
                      sea accionable. */}
                  {r.detalle || MOTIVOS_DE_RECHAZO[r.motivo] || r.motivo}
                </li>
              ))}
            </ul>
          ) : null}
        </Aviso>
      ) : null}
    </div>
  );
}


/**
 * Lo que dejó la última acción, arriba y hasta que alguien lo cierre.
 *
 * Un envío recién repesado sale de su parada y su fila se desmonta, así que el
 * dato que decide si el paquete sube a la camioneta se renderizaba en un
 * componente condenado: quedaba un toast de tres segundos que decía «Repesado».
 */
function Resultado({ resultado, onCerrar }) {
  const { envio, tipo, datos } = resultado;
  const puedeSalir = datos?.puede_salir;
  const rama = datos?.rama;
  const ok = tipo === 'repesado' ? puedeSalir : datos?.cobro?.estado === 'pagado';
  return (
    <Aviso tono={ok ? 'ok' : 'alerta'}
      titulo={`${envio.display_id || envio.envio_id} · ${
        tipo === 'repesado'
          ? (rama === 'cobrar' ? 'se cobró la diferencia'
            : rama === 'devolver' ? 'se devolvió la diferencia'
              : 'sin ajuste')
          : (ok ? 'cobro inicial cobrado' : 'cobro inicial pendiente')}`}>
      {tipo === 'repesado' ? (
        <>
          Total final {fmt(datos?.total_final_ris ?? 0, 2)} RIS.{' '}
          {puedeSalir
            ? 'Puede salir de Pacaraima.'
            : 'NO sale de Pacaraima hasta que se pague.'}
        </>
      ) : (
        <>
          {fmt(datos?.cobro?.monto_ris ?? 0, 2)} RIS.{' '}
          {ok ? '' : 'El usuario no tenía saldo; el paquete sigue viajando igual.'}
        </>
      )}
      <button type="button" onClick={onCerrar}
        style={{ display: 'block', marginTop: '8px', border: 'none', background: 'none',
          padding: 0, cursor: 'pointer', fontSize: '12px', textDecoration: 'underline',
          color: 'inherit' }}>
        Entendido
      </button>
    </Aviso>
  );
}
