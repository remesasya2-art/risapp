/**
 * Nomina.jsx — Quién puede retirar en Pacaraima, y quién está de turno.
 *
 * ESTE NOMBRE VA IMPRESO EN UNA CAJA
 *   Es lo único de la nómina que ve el usuario, y es contra lo que el mostrador
 *   compara un documento. Por eso el backend exige nombre y apellido, y por eso
 *   una autorización vencida deja a la persona afuera aunque su ficha siga
 *   activa: enterarse en el mostrador es enterarse con el paquete adentro.
 *
 * CAMBIAR EL TURNO NO CAMBIA NINGUNA CAJA QUE YA ESTE VIAJANDO
 *   El nombre se congela en el envío al cotizar. Designar a otro solo afecta a
 *   las cotizaciones nuevas — porque el mostrador compara la etiqueta contra un
 *   documento, no contra nuestra base.
 *
 * EL CPF NO SE MUESTRA
 *   La lista la lee también el operador, y un listado se comparte en pantalla
 *   mucho más seguido de lo que se cree. El backend directamente no lo baja: acá
 *   se puede cargar y no se puede volver a ver, que es lo correcto.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { BadgeCheck, Plus, Save, UserCheck, Users } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { Area, Aviso, Boton, Campo, Cargando, Interruptor, NoSePudoLeer, Texto, Vacio } from '../../envios/ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from '../../envios/estilos';

const NUEVO = {
  nombre: '', cpf: '', telefono: '', activo: true,
  autorizado_desde: '', autorizado_hasta: '', notas: '',
};

/** `""` no es una fecha: es «sin vencimiento», y eso se manda como null. */
const fecha = (v) => (v ? new Date(`${v}T00:00:00Z`).toISOString() : null);
const soloDia = (v) => (v ? String(v).slice(0, 10) : '');

export default function Nomina() {
  const [nomina, setNomina] = useState([]);
  const [previa, setPrevia] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [editando, setEditando] = useState(null);
  const [creando, setCreando] = useState(false);
  const [designando, setDesignando] = useState(null);
  const [noSeLeyo, setNoSeLeyo] = useState(null);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/retiro');
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setNomina(res.data?.nomina || []);
      setPrevia(res.data?.vista_previa || null);
    } catch (err) {
      if (!vivo.current) return;
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudo leer la nómina.'));
      }
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const designar = async (colaborador_id) => {
    setDesignando(colaborador_id);
    try {
      const res = await api.put('/admin/envios/retiro/turno', { colaborador_id });
      toast.success(`De turno: ${res.data?.de_turno}`);
      setPrevia(res.data?.vista_previa || previa);
      cargar();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo designar.'));
    } finally {
      setDesignando(null);
    }
  };

  if (cargando) return <Cargando texto="Leyendo la nómina…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="la nómina" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  // `retirador_id` es QUIEN SE ESTA USANDO, no quién está designado: cuando nadie
  // lo está, el backend cae a la primera persona vigente y lo dice en
  // `retirador_motivo`. Poniéndole la insignia a esa persona —y ocultándole el
  // botón «Poner de turno», que solo aparece en los que NO están de turno— el
  // panel daba el paso por hecho, mientras la portada decía «ninguna está de
  // turno». Dos pantallas del mismo panel diciendo lo contrario, y sin forma de
  // designar a quien ya figuraba designado.
  const motivo = previa?.retirador_motivo;
  const designado = motivo === 'designado';
  const deTurnoId = designado ? previa?.retirador_id : null;
  const enUso = previa?.retirador_nombre;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <Aviso tono="info" titulo="Mantené dos o tres personas activas">
        Es lo que evita que una licencia médica frene la operación. El super administrador marca
        cuál está de turno; cambiarlo no toca ninguna caja que ya esté viajando, porque el
        nombre se congela en el envío al cotizar.
      </Aviso>

      {motivo && motivo !== 'designado' ? (
        <Aviso tono="alerta"
          titulo={motivo === 'suplente'
            ? 'La persona designada ya no puede retirar'
            : 'Nadie está designado'}>
          {motivo === 'suplente' ? (
            <>Su autorización venció o se dio de baja, así que las cotizaciones salen a
            nombre de <strong>{enUso}</strong>. Designá a alguien vigente.</>
          ) : (
            <>Las cotizaciones nuevas están saliendo a nombre de <strong>{enUso}</strong>,
            que es la primera persona vigente de la lista — no una elección. Poné a alguien
            de turno.</>
          )}
        </Aviso>
      ) : null}

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <h3 style={{ ...titulo, margin: 0 }}><Users size={16} /> Nómina</h3>
        <Boton style={{ marginLeft: 'auto' }} onClick={() => { setCreando(true); setEditando(null); }}>
          <Plus size={14} /> Agregar persona
        </Boton>
      </div>

      {creando ? (
        <Ficha nuevo colaborador={NUEVO}
          onListo={() => { setCreando(false); cargar(); }}
          onCancelar={() => setCreando(false)} />
      ) : null}

      {nomina.length === 0 && !creando ? (
        <Vacio titulo="No hay nadie autorizado">
          Sin al menos una persona vigente, la cotización no tiene a qué nombre rotular.
        </Vacio>
      ) : null}

      {nomina.map((c) => {
        const esDeTurno = c.colaborador_id === deTurnoId;
        return (
          <div key={c.colaborador_id} style={{
            ...tarjeta,
            borderColor: esDeTurno ? COLOR.primario : COLOR.borde,
            borderWidth: esDeTurno ? '2px' : '1px',
            backgroundColor: esDeTurno ? COLOR.primarioSuave : '#fff',
            opacity: c.activo ? 1 : 0.6,
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px',
              flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <p style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: COLOR.texto,
                  display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {c.nombre}
                  {esDeTurno ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px',
                      fontSize: '11px', fontWeight: 700, padding: '3px 9px', borderRadius: '999px',
                      backgroundColor: '#fff', color: COLOR.primarioOscuro,
                      border: `1px solid ${COLOR.primario}` }}>
                      <BadgeCheck size={12} /> de turno
                    </span>
                  ) : null}
                  {!c.activo ? (
                    <span style={{ fontSize: '11px', fontWeight: 700, padding: '3px 9px',
                      borderRadius: '999px', backgroundColor: '#f3f4f6', color: COLOR.suave }}>
                      inactivo
                    </span>
                  ) : null}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
                  {c.autorizado_hasta
                    ? `Autorizado hasta ${soloDia(c.autorizado_hasta)}`
                    : 'Autorización sin vencimiento'}
                  {c.notas ? ` · ${c.notas}` : ''}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                {!esDeTurno && c.activo ? (
                  <Boton variante="secundario" cargando={designando === c.colaborador_id}
                    onClick={() => designar(c.colaborador_id)}>
                    <UserCheck size={14} /> Poner de turno
                  </Boton>
                ) : null}
                <Boton variante="secundario"
                  onClick={() => setEditando(editando === c.colaborador_id ? null : c.colaborador_id)}>
                  {editando === c.colaborador_id ? 'Cerrar' : 'Editar'}
                </Boton>
              </div>
            </div>
            {editando === c.colaborador_id ? (
              <div style={{ marginTop: '18px', paddingTop: '16px',
                borderTop: `1px solid ${COLOR.borde}` }}>
                <Ficha colaborador={c} onListo={() => { setEditando(null); cargar(); }}
                  onCancelar={() => setEditando(null)} />
              </div>
            ) : null}
          </div>
        );
      })}

      <div style={{ ...tarjeta, backgroundColor: '#0f172a', borderColor: '#0f172a' }}>
        <h3 style={{ ...titulo, color: '#fff' }}>La etiqueta con quien está de turno</h3>
        <p style={{ ...bajada, color: '#94a3b8' }}>
          Es la dirección exacta que el usuario va a copiar sobre su caja.
        </p>
        {previa?.disponible ? (
          <pre style={{ margin: 0, padding: '16px', borderRadius: '12px',
            backgroundColor: '#1e293b', color: '#e2e8f0', fontSize: '14px', lineHeight: 1.7,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
            {previa.texto_copiable}
          </pre>
        ) : (
          <Aviso tono="alerta" titulo="Todavía no se puede armar">
            {(previa?.faltantes || ['Falta configuración.']).join(' ')}
          </Aviso>
        )}
      </div>
    </div>
  );
}

function Ficha({ colaborador, nuevo, onListo, onCancelar }) {
  const [datos, setDatos] = useState(() => ({
    ...NUEVO, ...colaborador,
    cpf: '', telefono: '',   // el backend no los baja: se cargan, no se releen
    autorizado_desde: soloDia(colaborador.autorizado_desde),
    autorizado_hasta: soloDia(colaborador.autorizado_hasta),
    notas: colaborador.notas || '',
  }));
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    const cuerpo = {
      nombre: datos.nombre,
      activo: datos.activo,
      autorizado_desde: fecha(datos.autorizado_desde),
      autorizado_hasta: fecha(datos.autorizado_hasta),
      notas: datos.notas || '',
    };
    // El CPF y el teléfono solo se mandan si se escribieron. El backend FUSIONA
    // con lo que hay, así que mandarlos vacíos borraría en silencio los que ya
    // estaban cargados — y esta pantalla nunca los muestra, así que nadie se
    // enteraría.
    if (datos.cpf.trim()) cuerpo.cpf = datos.cpf.trim();
    if (datos.telefono.trim()) cuerpo.telefono = datos.telefono.trim();

    try {
      if (nuevo) {
        await api.post('/admin/envios/retiro/colaboradores', cuerpo);
        toast.success('Persona agregada');
      } else {
        await api.put(`/admin/envios/retiro/colaboradores/${colaborador.colaborador_id}`, cuerpo);
        toast.success('Guardado');
      }
      onListo();
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo guardar.'));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div style={nuevo ? tarjeta : undefined}>
      <div style={grilla('220px')}>
        <Campo etiqueta="Nombre y apellido"
          ayuda="Los dos: es lo que va rotulado en la caja y lo que el mostrador compara contra el documento.">
          <Texto value={datos.nombre}
            onChange={(e) => setDatos((d) => ({ ...d, nombre: e.target.value }))} maxLength={120} />
        </Campo>
        <Campo etiqueta="CPF"
          ayuda={nuevo ? 'Para la autorización ante el transportista. No se muestra en ninguna pantalla del usuario.'
            : 'No se vuelve a mostrar. Dejalo vacío para conservar el que ya está cargado.'}>
          <Texto value={datos.cpf} placeholder={nuevo ? '' : '(sin cambios)'}
            onChange={(e) => setDatos((d) => ({ ...d, cpf: e.target.value }))} maxLength={20} />
        </Campo>
        <Campo etiqueta="Teléfono"
          ayuda={nuevo ? 'Interno.' : 'Dejalo vacío para conservar el que ya está cargado.'}>
          <Texto value={datos.telefono} placeholder={nuevo ? '' : '(sin cambios)'}
            onChange={(e) => setDatos((d) => ({ ...d, telefono: e.target.value }))} maxLength={30} />
        </Campo>
        <Campo etiqueta="Autorizado desde" ayuda="Opcional.">
          <Texto type="date" value={datos.autorizado_desde}
            onChange={(e) => setDatos((d) => ({ ...d, autorizado_desde: e.target.value }))} />
        </Campo>
        <Campo etiqueta="Autorizado hasta"
          ayuda="Vacío = sin vencimiento. Con fecha, ese día deja de poder rotular paquetes aunque siga activo.">
          <Texto type="date" value={datos.autorizado_hasta}
            onChange={(e) => setDatos((d) => ({ ...d, autorizado_hasta: e.target.value }))} />
        </Campo>
      </div>

      <div style={{ marginTop: '14px' }}>
        <Interruptor activo={datos.activo} etiqueta="Activo"
          onChange={(v) => setDatos((d) => ({ ...d, activo: v }))}
          ayuda="Dar de baja no borra la ficha: tiene que seguir existiendo para poder contestar quién retiró el paquete de marzo." />
      </div>

      <div style={{ marginTop: '14px' }}>
        <Campo etiqueta="Notas" ayuda="Internas.">
          <Area value={datos.notas} filas={2} maxLength={500}
            onChange={(e) => setDatos((d) => ({ ...d, notas: e.target.value }))} />
        </Campo>
      </div>

      {error ? <Aviso tono="error" titulo="No se guardó" style={{ marginTop: '14px' }}>{error}</Aviso> : null}

      <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
        <Boton onClick={guardar} cargando={guardando}>
          <Save size={14} /> {nuevo ? 'Agregar' : 'Guardar'}
        </Boton>
        <Boton variante="secundario" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}
