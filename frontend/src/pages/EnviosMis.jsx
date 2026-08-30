/**
 * EnviosMis.jsx — Los envíos del usuario.
 *
 * LO PRIMERO QUE ALGUIEN QUIERE SABER AL ABRIR ESTA LISTA ES SI TIENE ALGO QUE
 * HACER, y eso lo decide el backend (`hay_algo_que_pagar`), no la pantalla: la
 * regla de qué cuenta como impago vive del lado del servidor y duplicarla acá
 * sería garantizar que un día digan cosas distintas.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, PackagePlus, RefreshCw } from 'lucide-react';
import api from '../utils/api';
import { fmt } from '../utils/format';
import Chrome from '../components/envios/Chrome';
import { Aviso, Boton, Cargando, NoSePudoLeer, Vacio } from '../components/envios/ui';
import { COLOR, esFallaDeLectura, mensajeDeError, tarjeta } from '../components/envios/estilos';
import { PIDE_ALGO, TITULOS, tonoDe } from '../components/envios/estados';

// `fmt` devuelve «0,00» para null, undefined y NaN. En una lista de precios eso
// se lee como «gratis», que es exactamente lo que no hay que decir cuando el
// dato no llegó.
const num = (v) => (v === null || v === undefined || v === '' ? '—' : fmt(v, 2));

export default function EnviosMis() {
  const [datos, setDatos] = useState(null);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    try {
      const res = await api.get('/envios', { params: { pagina } });
      if (mia !== peticion.current) return;
      setNoSeLeyo(null);
      setDatos(res.data);
    } catch (err) {
      if (mia !== peticion.current) return;
      // Sin esto, una lectura fallida dejaba `datos` en null y se pintaba
      // «todavía no mandaste nada» — un cartel que le dice a alguien que no tiene
      // envíos justo cuando no pudimos leerlos.
      setNoSeLeyo(mensajeDeError(err, esFallaDeLectura(err)
        ? 'No pudimos leer tus envíos. Probá de nuevo en un minuto.'
        : 'No se pudieron leer tus envíos.'));
    } finally {
      if (mia === peticion.current) setCargando(false);
    }
  }, [pagina]);

  useEffect(() => {
    (async () => { await cargar(); })();
    return () => { peticion.current += 1; };
  }, [cargar]);

  const envios = datos?.envios || [];

  return (
    <Chrome titulo="Mis envíos" volverA="/">
      <Link to="/envios/nuevo" style={{ textDecoration: 'none' }}>
        <Boton style={{ width: '100%', justifyContent: 'center', padding: '14px' }}>
          <PackagePlus size={16} /> Enviar un paquete
        </Boton>
      </Link>

      {datos?.degradado ? (
        <Aviso tono="alerta" titulo="No pudimos leer la lista completa">
          Lo que ves puede estar incompleto. Probá de nuevo en un minuto — tus envíos están,
          es la lista lo que falló.
          <Boton variante="secundario" style={{ marginTop: '10px' }}
            onClick={() => { setCargando(true); cargar(); }}>
            <RefreshCw size={14} /> Reintentar
          </Boton>
        </Aviso>
      ) : null}

      {cargando && !datos ? <Cargando texto="Buscando tus envíos…" /> : null}

      {noSeLeyo && !datos ? (
        <NoSePudoLeer que="tus envíos" detalle={noSeLeyo}
          onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />
      ) : null}

      {!cargando && !noSeLeyo && !datos?.degradado && envios.length === 0 ? (
        <Vacio titulo="Todavía no mandaste nada">
          Cotizar es gratis y no reserva nada: podés ver el precio antes de decidir.
        </Vacio>
      ) : null}

      {envios.map((e) => <Fila key={e.envio_id} envio={e} />)}

      {datos?.hay_mas || pagina > 1 ? (
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
          <Boton variante="secundario" disabled={pagina <= 1}
            onClick={() => { setCargando(true); setPagina((p) => p - 1); }}>
            Anteriores
          </Boton>
          <Boton variante="secundario" disabled={!datos?.hay_mas}
            onClick={() => { setCargando(true); setPagina((p) => p + 1); }}>
            Siguientes
          </Boton>
        </div>
      ) : null}
    </Chrome>
  );
}

function Fila({ envio }) {
  const tono = tonoDe(envio.estado);
  const pide = PIDE_ALGO[envio.estado];
  return (
    <Link to={`/envios/${envio.envio_id}`} style={{ textDecoration: 'none' }}>
      <div style={{ ...tarjeta, display: 'flex', gap: '12px', alignItems: 'center',
        borderColor: envio.hay_algo_que_pagar ? '#fde68a' : COLOR.borde }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '14px', fontWeight: 700, color: COLOR.texto,
              fontFamily: 'monospace' }}>
              {envio.display_id}
            </span>
            <span style={{ fontSize: '11px', fontWeight: 700, padding: '3px 9px',
              borderRadius: '999px', backgroundColor: tono.fondo, color: tono.texto,
              border: `1px solid ${tono.borde}` }}>
              {TITULOS[envio.estado] || envio.estado}
            </span>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: COLOR.suave }}>
            Para {envio.destino?.destinatario || '—'} · {envio.destino?.ciudad || '—'}
            {envio.destino?.estado ? `, ${envio.destino.estado}` : ''}
          </p>
          {envio.hay_algo_que_pagar ? (
            <p style={{ margin: '6px 0 0 0', fontSize: '13px', fontWeight: 600,
              color: '#92400e' }}>
              Falta pagar {num(envio.a_pagar_ris)} {envio.moneda}
            </p>
          ) : pide ? (
            <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#92400e' }}>{pide}</p>
          ) : null}
        </div>
        <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
          <span style={{ fontSize: '15px', fontWeight: 700, color: COLOR.texto }}>
            {num(envio.total_ris)}
          </span>
          <span style={{ display: 'block', fontSize: '11px', color: COLOR.suave }}>
            {envio.moneda}{envio.es_estimado ? ' · estimado' : ''}
          </span>
        </div>
        <ChevronRight size={18} color={COLOR.suave} />
      </div>
    </Link>
  );
}
