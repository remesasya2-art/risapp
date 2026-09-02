/**
 * EnviosPanel.jsx — El panel de configuración del módulo de envíos.
 *
 * SIETE PANTALLAS QUE SE CARGAN UNA SOLA VEZ EN LA VIDA DEL SISTEMA
 *   Y en un orden: cada bloque depende de los anteriores. Por eso la portada no
 *   es un resumen decorativo sino la pantalla principal — dice qué falta, en qué
 *   orden, y lleva a cada paso.
 *
 * LO QUE SE ADMINISTRA ACA Y LO QUE NO
 *   Acá va todo lo que un día puede querer cambiarse sin abrir el repositorio:
 *   transportistas, agencias, precios, la nómina de retiro, los textos. Lo que NO
 *   se administra es la mecánica —cómo se calcula un peso volumétrico, qué
 *   transiciones de estado son válidas, cómo se debita un saldo—: eso es lógica,
 *   cambia con un cambio de diseño, y pertenece al repositorio con sus tests.
 *
 * LA PESTAÑA ACTIVA VIVE EN LA URL
 *   Igual que en el resto del panel: recargar, o entrar por un enlace, no te
 *   devuelve a la portada. Importa acá más que en otras pantallas, porque cargar
 *   la configuración es una sesión larga con interrupciones.
 */
import { useSearchParams } from 'react-router-dom';
import {
  Building2, ClipboardCheck, FileText, HardDrive, MapPin, Table2, Tags, Users,
} from 'lucide-react';
import { COLOR } from '../../envios/estilos';
import PuestaEnMarcha from './PuestaEnMarcha';
import PuntoOrigen from './PuntoOrigen';
import Contenido from './Contenido';
import Transportistas from './Transportistas';
import Nomina from './Nomina';
import Precios from './Precios';
import Origenes from './Origenes';
import Matrices from './Matrices';
import Almacen from './Almacen';

const PANTALLAS = [
  { clave: 'inicio', etiqueta: 'Puesta en marcha', Icono: ClipboardCheck },
  { clave: 'config/punto_origen', etiqueta: 'Punto de origen', Icono: MapPin },
  { clave: 'config/contenido', etiqueta: 'Contenido y operación', Icono: FileText },
  { clave: 'transportistas', etiqueta: 'Transportistas y agencias', Icono: Building2 },
  { clave: 'retiro', etiqueta: 'Nómina de retiro', Icono: Users },
  { clave: 'tarifas', etiqueta: 'Precios', Icono: Tags },
  // Los dos van DESPUES de transportistas y agencias, y en este orden entre
  // ellos: la pantalla de matrices cruza las UF de los origenes contra lo
  // cargado, asi que sin origenes no tiene contra que avisar que falta.
  { clave: 'origenes', etiqueta: 'Orígenes de Brasil', Icono: MapPin },
  { clave: 'matrices', etiqueta: 'Precios de referencia', Icono: Table2 },
  { clave: 'almacen', etiqueta: 'Fotos', Icono: HardDrive },
];

/** `config/operacion` y `config/contenido` son la misma pantalla. */
const ALIAS = { 'config/operacion': 'config/contenido' };

/** Las que se pueden nombrar en la URL. Una desconocida vuelve a la portada. */
const VALIDAS = PANTALLAS.map((p) => p.clave);

export default function EnviosPanel() {
  // En la URL, igual que la pestaña del panel: cargar la configuración es una
  // sesión larga con interrupciones, y recargar la página no puede devolverte a
  // la portada cada vez. `replace` para no llenar el historial: el botón «atrás»
  // tiene que salir del panel, no recorrer las siete sub-pantallas.
  const [params, setParams] = useSearchParams();
  const pedida = ALIAS[params.get('envios')] || params.get('envios');
  const actual = VALIDAS.includes(pedida) ? pedida : 'inicio';

  const ir = (destino) => {
    const clave = ALIAS[destino] || destino;
    setParams((previos) => {
      const siguientes = new URLSearchParams(previos);
      siguientes.set('envios', clave);
      return siguientes;
    }, { replace: true });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {PANTALLAS.map((p) => {
          // `Icono` se saca acá y no en los parámetros: sin el plugin de React,
          // eslint no ve que un `<Icono />` en el JSX usa la variable, y un
          // parámetro desestructurado le queda como argumento sin usar.
          const { clave, etiqueta, Icono } = p;
          const activa = actual === clave;
          return (
            <button key={clave} type="button" onClick={() => ir(clave)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '8px 14px', borderRadius: '10px', fontSize: '14px', fontWeight: 600,
                cursor: 'pointer',
                border: `1px solid ${activa ? COLOR.primario : COLOR.borde}`,
                backgroundColor: activa ? COLOR.primarioSuave : '#fff',
                color: activa ? COLOR.primarioOscuro : COLOR.suave }}>
              <Icono size={15} /> {etiqueta}
            </button>
          );
        })}
      </div>

      {actual === 'inicio' ? <PuestaEnMarcha onIr={ir} /> : null}
      {actual === 'config/punto_origen' ? <PuntoOrigen /> : null}
      {actual === 'config/contenido' ? <Contenido /> : null}
      {actual === 'transportistas' ? <Transportistas /> : null}
      {actual === 'retiro' ? <Nomina /> : null}
      {actual === 'tarifas' ? <Precios /> : null}
      {actual === 'origenes' ? <Origenes onIr={ir} /> : null}
      {actual === 'matrices' ? <Matrices /> : null}
      {actual === 'almacen' ? <Almacen /> : null}
    </div>
  );
}
