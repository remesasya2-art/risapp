import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, Package, Boxes, 
  RefreshCw, Shield, Activity, Eye, X, ChevronRight, UserCog, Gift, Briefcase, KeyRound, Trash2, MessageSquare, CheckCircle, Clock, Phone, Mail, Send, Download, Image, Upload, AlertCircle, Zap, BookOpen, Star, Wallet, ScrollText, ShieldCheck, SlidersHorizontal, Menu
, AlertTriangle, BarChart3, Receipt, Landmark, Archive } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { confirmar } from '../components/flujo/confirmar.js';
import OrdenesPorProcesar from '../components/admin/OrdenesPorProcesar';
import DiferenciasPago from '../components/admin/DiferenciasPago';
import Reportes from '../components/admin/Reportes';
import ReconciliacionLedger from '../components/admin/ReconciliacionLedger';
import SeguridadFinanciera from '../components/admin/SeguridadFinanciera';
import CobrosSinAcreditar from '../components/admin/CobrosSinAcreditar';
import HojaDeMercadoPago from '../components/admin/HojaDeMercadoPago';
import LibroMayor from '../components/admin/LibroMayor';
import RecursosHumanos from '../components/admin/RecursosHumanos';
import LibroAuditoria from '../components/admin/LibroAuditoria';
import Errores from '../components/admin/Errores';
import Nucleo from '../components/admin/Nucleo';
import Uso from '../components/admin/Uso';
import Configuracion from '../components/admin/Configuracion';
import Respaldo from '../components/admin/Respaldo';
import RecargasVES from '../components/admin/RecargasVES';
import Retiros from '../components/admin/Retiros';
import ListaNegra from '../components/admin/ListaNegra';
import { fmt } from '../utils/format';
import MesaDeAyuda from '../components/admin/MesaDeAyuda';
import { WipeButton } from '../components/common/WipeButton';
import { RestoreButton } from '../components/common/RestoreButton';
import ErrorBoundary from '../components/common/ErrorBoundary';
import CampanaDelEquipo from '../components/CampanaDelEquipo';
import { RateHistoryButton } from '../components/common/RateHistoryButton';
import { BcvRatesCard } from '../components/common/BcvRatesCard';
import KycPanel from '../components/admin/KycPanel';
import { StatusBadge } from '../components/dashboard/TransactionItem';
import BtcAdminHistorial from '../components/admin/BtcAdminHistorial';
import BtcAdminConfig from '../components/admin/BtcAdminConfig';
import TasasBtcSection from '../components/admin/TasasBtcSection';
import TasasCriptoSection from '../components/admin/TasasCriptoSection';
import CreditsAdminPanel from '../components/admin/CreditsAdminPanel';
import EnviosPanel from '../components/admin/envios/EnviosPanel';
import OperacionPanel from '../components/admin/envios/OperacionPanel';
import { abrirArchivo, bajarArchivo, rutaDeArchivo, sePuedeAbrir } from '../utils/urlDeArchivo';


// Función para enmascarar el CPF (solo muestra últimos 3 dígitos)
const maskCPF = (cpf) => {
  if (!cpf) return '';
  const cleanCPF = cpf.replace(/\D/g, '');
  if (cleanCPF.length < 3) return cpf;
  const lastThree = cleanCPF.slice(-3);
  return `***.***.**${lastThree.charAt(0)}-${lastThree.slice(1)}`;
};

const CRM_KEYS = ['users', 'kyc', 'blacklist', 'chat', 'support'];

const CRM_SUBTABS = [
  { key: 'users', label: 'Usuarios', icon: Users },
  { key: 'kyc', label: 'KYC', icon: Shield },
  { key: 'blacklist', label: 'Lista negra', icon: Shield },
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'support', label: 'Soporte', icon: MessageSquare },
  { key: 'ratings', label: 'Calificaciones', icon: Star },
];

const TABS = [
  { key: 'overview', label: 'Resumen', icon: Activity },
  // Qué usa la gente. `superAdminOnly`: es el cuadro de mando del negocio
  // —altas, embudo, funciones más usadas—, no una tarea que se delegue.
  { key: 'uso', label: 'Uso', icon: BarChart3, superAdminOnly: true },
  { key: 'ordenes', label: 'Órdenes por procesar', icon: CheckCircle },
  { key: 'diferencias', label: 'Diferencias de pago', icon: AlertCircle, superAdminOnly: true },
  { key: 'reportes', label: 'Reportes', icon: Download },
  // Antes del Libro mayor a propósito: acá están las cuatro respuestas, allá
  // el detalle contable de cada una. Sólo del super administrador, igual que
  // las rutas que consulta (`get_super_admin` en el backend).
  { key: 'seguridad', label: 'Seguridad financiera', icon: ShieldCheck, superAdminOnly: true },
  // Al lado de Seguridad financiera porque es la misma clase de pregunta —una
  // sobre el dinero que hay que ir a buscar, no sobre la operación del día— y
  // porque consulta la misma puerta del backend (`get_super_admin`). Va después
  // y no antes: aquélla se carga sola y contesta de una, ésta hay que pulsarla
  // y le pregunta a Mercado Pago pago por pago.
  { key: 'cobros', label: 'Cobros sin acreditar', icon: Search, superAdminOnly: true },
  // La hoja que alimenta Mercado Pago sola: una fila por aviso que llega, se
  // haya podido acreditar o no. SIN `superAdminOnly`, igual que la ruta que
  // consulta (`get_admin_user`): quien atiende a un cliente que dice «pagué y
  // no me aparece» tiene que poder mirarlo en el momento, y no hay dinero que
  // mover acá —es de sólo lectura y no muestra datos del pagador—.
  { key: 'hoja_mp', label: 'Pagos de Mercado Pago', icon: Receipt },
  { key: 'ledger', label: 'Libro mayor', icon: BookOpen },
  { key: 'withdrawals', label: 'Retiros', icon: ArrowUpRight },
  { key: 'recharges', label: 'Recargas VES', icon: ArrowDownLeft },
  { key: 'crm', label: 'CRM', icon: UserCog },
  { key: 'rates', label: 'Tasas', icon: TrendingUp },
  // Sólo del super administrador, igual que las dos rutas que consulta: la
  // lista de órdenes (`/btc/operador/pendientes`) y marcarlas como enviadas
  // (`/admin/btc/marcar-enviado`). Visible para un `admin`, mostraba la lista
  // pero el botón de pagar le contestaba 403.
  { key: 'btc', label: 'BTC Lightning', icon: Zap, superAdminOnly: true },
  { key: 'credits', label: 'Créditos Cripto', icon: Wallet, superAdminOnly: true },
  // La cola de Pacaraima. SIN `superAdminOnly`: la usa el operador todos los
  // dias y el super administrador tambien puede hacer cualquier tarea de
  // operador —pasa por `get_crm_user` y por `get_admin_user`, asi que ninguna
  // ruta lo rechaza—. La separacion de roles va en el otro sentido: el que viaja
  // y pesa cajas no puede cambiar los precios ni la cuenta que recibe los
  // fletes.
  { key: 'operacion', label: 'Cola de envíos', icon: Boxes },
  // La configuracion, en cambio, si es solo del super administrador: cambia
  // precios, la cuenta que recibe los fletes y a nombre de quien se rotulan las
  // cajas.
  { key: 'envios', label: 'Config. de envíos', icon: Package, superAdminOnly: true },
  // Recursos Humanos y el libro de auditoría son SÓLO del super administrador,
  // igual que en el backend (`get_super_admin`). Dar de alta a alguien con
  // permisos, y leer quién hizo qué, no son cosas que se deleguen: si se
  // pudieran delegar, quien las tuviera podría darse a sí mismo el resto.
  { key: 'rrhh', label: 'Recursos Humanos', icon: UserCog, superAdminOnly: true },
  { key: 'auditoria', label: 'Auditoría', icon: ScrollText, superAdminOnly: true },
  // Los errores del servidor. Sólo super administrador, como la auditoría: una
  // línea trae la ruta, el usuario que lo sufrió y el texto de una excepción.
  { key: 'errores', label: 'Errores', icon: AlertTriangle, superAdminOnly: true },
  // Los números configurables del panel. `superAdminOnly` por el mismo motivo
  // que Recursos Humanos: uno de esos números decide cuánta plata se le regala
  // a cada cuenta que se registra, y quien pudiera cambiarlo podría subirlo,
  // cobrar y bajarlo otra vez. El backend lo exige igual (`get_super_admin`).
  { key: 'configuracion', label: 'Configuración', icon: SlidersHorizontal, superAdminOnly: true },
  // El respaldo de la base: se baja un archivo con los datos de todos los
  // clientes. Sólo super administrador; el backend lo exige igual.
  { key: 'respaldo', label: 'Respaldo de la base', icon: Archive, superAdminOnly: true },
  // El laboratorio del núcleo de cuentas: la arquitectura de fintech que se
  // construye mientras se resuelve lo legal. SOLO super administrador, y
  // además el servidor contesta 404 a todo mientras «Núcleo de cuentas» esté
  // en 0 en Configuración. Los clientes no tienen ninguna puerta a esto. Ver
  // components/admin/Nucleo.jsx.
  { key: 'nucleo', label: 'Núcleo (laboratorio)', icon: Landmark, superAdminOnly: true },
];

// LOS SEIS GRUPOS DEL PANEL
//
//   Antes esto era una tira plana de dieciocho pestañas que envolvía en tres
//   filas, ordenadas por el momento en que se fueron agregando. El propio
//   archivo lo estaba peleando a mano: había comentarios pidiendo que una
//   pestaña quedara «antes del Libro mayor a propósito» y otra «al lado de
//   Seguridad financiera», que es agrupar sin tener con qué.
//
//   El criterio no es el tema, es QUE VINISTE A HACER:
//
//     Operación      trabajo que espera a que alguien lo haga
//     Clientes       la gente y lo que manda
//     Encomiendas    las cajas y lo que cuesta mandarlas
//     Contabilidad   dinero que ya se movió, para cuadrarlo o explicarlo
//     Administración lo que cambia cómo se comporta el sistema
//
//   `hijas` son claves de `TABS` y `CRM_SUBTABS`, no secciones nuevas: los
//   nombres internos no cambian, así que los enlaces con `?tab=` y el salto de
//   la campana del equipo siguen andando igual.
const GRUPOS = [
  { key: 'g_resumen', label: 'Resumen', icon: Activity, hijas: ['overview', 'uso'] },
  { key: 'g_operacion', label: 'Operación', icon: CheckCircle,
    hijas: ['ordenes', 'withdrawals', 'recharges', 'diferencias', 'hoja_mp',
            'btc', 'credits', 'rates'] },
  { key: 'g_clientes', label: 'Clientes', icon: UserCog,
    hijas: ['users', 'kyc', 'blacklist', 'chat', 'support', 'ratings'] },
  { key: 'g_envios', label: 'Encomiendas', icon: Boxes,
    hijas: ['operacion', 'envios'] },
  { key: 'g_cuentas', label: 'Contabilidad', icon: BookOpen,
    hijas: ['ledger', 'seguridad', 'cobros', 'reportes'] },
  { key: 'g_admin', label: 'Administración', icon: SlidersHorizontal,
    hijas: ['configuracion', 'respaldo', 'rrhh', 'auditoria', 'errores', 'nucleo'] },
];

// La ficha de cada sección, venga de donde venga. `crm` no entra: era el
// contenedor de las subpestañas y ahora ese trabajo lo hace el grupo.
const POR_CLAVE = Object.fromEntries(
  [...TABS.filter((t) => t.key !== 'crm'), ...CRM_SUBTABS].map((s) => [s.key, s]));

// El número que dice cuánto espera en una pestaña.
//
// Se pinta SOLO si hay algo. Un «0» permanente en nueve pestañas es ruido que
// se aprende a no mirar, y entonces el 3 de al lado tampoco se mira.
function Pendiente({ cuantos, activa }) {
  if (!cuantos) return null;
  return (
    <span
      style={{
        minWidth: '20px', height: '20px', padding: '0 6px', borderRadius: '9999px',
        fontSize: '11px', fontWeight: 700, display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center',
        backgroundColor: activa ? 'rgba(255,255,255,0.28)' : '#fee2e2',
        color: activa ? '#ffffff' : '#b91c1c',
      }}
      data-testid="pendiente"
    >
      {cuantos > 99 ? '99+' : cuantos}
    </span>
  );
}

// Cómo se llama cada rol en pantalla.
//
// La columna hacía `role === 'super_admin' ? 'Administrador' : 'Usuario'`, o
// sea que un `admin` y un `agent` —gente que aprueba KYC y mueve saldos— se
// veían idénticos a un cliente. Comprobado corriéndolo antes de tocarlo.
const NOMBRE_DEL_ROL = {
  super_admin: 'Administrador',
  admin: 'Colaborador',
  agent: 'Agente',
  user: 'Usuario',
};

const COLOR_DEL_ROL = {
  super_admin: { fondo: '#fee2e2', letra: '#b91c1c' },
  admin:       { fondo: '#ffedd5', letra: '#c2410c' },
  agent:       { fondo: '#e0e7ff', letra: '#4338ca' },
  user:        { fondo: '#f3f4f6', letra: '#6b7280' },
};

// Por qué esta cuenta no puede entrar, si no puede. Lo decide el servidor en
// `services/estado_de_la_cuenta.py`; acá sólo se le pone nombre y color.
const NOMBRE_DEL_ESTADO = {
  borrada: 'Borrada',
  vetada: 'En lista negra',
  suspendida: 'Suspendida',
};

const COLOR_DEL_ESTADO = {
  borrada:    { fondo: '#e5e7eb', letra: '#4b5563' },
  vetada:     { fondo: '#fee2e2', letra: '#b91c1c' },
  suspendida: { fondo: '#fef3c7', letra: '#b45309' },
};

const PRIORITY_COLORS = { baja: '#6b7280', normal: '#2563eb', alta: '#d97706', urgente: '#dc2626' };

export default function AdminPanel() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { rates, refreshRates } = useRate();
const [searchParams, setSearchParams] = useSearchParams();
  const VALID_TAB_KEYS = [...TABS.map((t) => t.key), ...CRM_SUBTABS.map((s) => s.key)];
  const defaultTab = user?.role === 'agent' ? 'chat' : 'overview';
  const tabFromUrl = searchParams.get('tab');
  const [activeTab, setActiveTabState] = useState(VALID_TAB_KEYS.includes(tabFromUrl) ? tabFromUrl : defaultTab);

  // Mantiene la pestaña activa reflejada en la URL (?tab=...) para que recargar
  // la pagina, o entrar por un enlace directo, no te devuelva siempre al Resumen.
  const setActiveTab = (key) => {
    setActiveTabState(key);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', key);
      return next;
    }, { replace: true });
  };

  // Salta al Libro mayor con una vista ya abierta. La pantalla de Seguridad
  // financiera da el veredicto; el detalle contable vive allá, y sin esto
  // habría que volver a buscarlo a mano.
  const irAlLibro = (vista) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', 'ledger');
      next.set('vista', vista);
      return next;
    }, { replace: true });
    setActiveTabState('ledger');
  };

  const isAgent = user?.role === 'agent';
  useEffect(() => {
    // 'operacion' entra en la lista: un agente puede VER la cola de envíos. Las
    // acciones que mueven saldo (verificar, repesar, desviar, acreditar flete)
    // piden `get_admin_user` y le van a devolver 403 desde el servidor, que es
    // donde tiene que estar la regla.
    if (isAgent && !['chat', 'support', 'users', 'kyc', 'blacklist', 'operacion'].includes(activeTab)) setActiveTab('chat');
  }, [isAgent]);
  const [loading, setLoading] = useState(true);
  // EL BOTON DE REFRESCAR, Y POR QUE ES UN NUMERO
  //
  //   Este botón llamaba sólo a `loadData`, que conoce CINCO pestañas
  //   (`overview`, `users`, `kyc`, `support`, `ratings`). El panel tiene
  //   veintidós. En las otras diecisiete el botón giraba un segundo y NO PEDIA
  //   NADA — comprobado en el navegador mirando la red: de siete pestañas
  //   probadas, seis no hacían un solo pedido.
  //
  //   Ahora el número se le pone de `key` al `<main>` que envuelve todas las
  //   secciones. Cambiarlo hace que React vuelva a montar la que estés viendo,
  //   y cada sección vuelve a pedir sus datos sola, igual que cuando entrás.
  //
  //   Se eligió así sobre las dos alternativas obvias:
  //
  //     Recargar la página entera anda, pero parpadea y borra lo que hubiera
  //     escrito sin guardar en un formulario.
  //
  //     Que cada sección se suscriba a un aviso de recarga obliga a tocar los
  //     veinticuatro componentes, y el día que alguien agregue la pestaña
  //     veintitrés y se olvide, el botón vuelve a mentir en esa pestaña: el
  //     mismo defecto de hoy con ropa nueva. Esta línea no se puede
  //     desactualizar.
  //
  //   Lo que sí cuesta: volver a montar cierra lo que estuviera abierto dentro
  //   de la sección. Es lo que significa refrescar.
  const [recarga, setRecarga] = useState(0);

  // EL MENU EN EL TELEFONO
  //
  //   En pantalla ancha el menú va fijo al costado y todo queda a un clic. En
  //   el teléfono no entra, así que se pliega detrás de un botón y se abre
  //   encima del contenido.
  //
  //   No es un invento para el panel: `pages/Dashboard.jsx` —la aplicación del
  //   cliente— ya funciona exactamente así desde antes. El panel era el único
  //   que no seguía ese patrón.
  //
  //   El corte va en 1024 y no en los 768 del Dashboard a propósito: acá el
  //   menú tiene veinte secciones y el contenido son tablas anchas. En una
  //   tableta de 800 los dos juntos quedan apretados, y prefiero el menú
  //   plegado antes que una tabla que se corta.
  const [esAncho, setEsAncho] = useState(window.innerWidth >= 1024);
  const [menuAbierto, setMenuAbierto] = useState(false);

  useEffect(() => {
    const alRedimensionar = () => {
      const ancho = window.innerWidth >= 1024;
      setEsAncho(ancho);
      // Al volver a pantalla ancha el menú se muestra fijo: dejar abierto el
      // de teléfono taparía el contenido con una copia del mismo menú.
      if (ancho) setMenuAbierto(false);
    };
    window.addEventListener('resize', alRedimensionar);
    return () => window.removeEventListener('resize', alRedimensionar);
  }, []);

  // Elegir una sección cierra el menú del teléfono. Sin esto queda tapando lo
  // que la persona acaba de pedir.
  // QUE GRUPOS ESTAN DESPLEGADOS
  //
  //   Arrancan TODOS CERRADOS. Es una decisión del dueño del proyecto y va
  //   anotada porque la primera versión hacía lo contrario: los abría todos,
  //   con el argumento de que el menú existe para ver las veinte secciones sin
  //   tocar nada.
  //
  //   Lo que ese argumento no miraba: veinte renglones abiertos no se leen de
  //   un vistazo, se recorren. Con los grupos cerrados, el menú entero son
  //   SEIS renglones que entran juntos en cualquier pantalla —teléfono
  //   incluido—, y se despliega el que se necesita. Eso es lo que hace que
  //   agrupar sirva de algo en vez de ser sólo un título encima de una lista
  //   igual de larga.
  //
  //   Cada grupo se abre y se cierra por su cuenta: se pueden tener dos
  //   abiertos a la vez. Cerrar los otros al abrir uno es la otra forma
  //   posible, y se descartó porque obliga a reabrir el de al lado cada vez
  //   que se va y se vuelve.
  //
  //   El grupo de la sección abierta se despliega solo y no se puede cerrar:
  //   esconder justo lo que estás mirando deja el menú sin poder indicar dónde
  //   estás parada.
  const [desplegados, setDesplegados] = useState(() => new Set());

  const desplegar = (clave) => setDesplegados((antes) => {
    const ahora = new Set(antes);
    if (ahora.has(clave)) ahora.delete(clave); else ahora.add(clave);
    return ahora;
  });

  const irA = (clave) => {
    setActiveTab(clave);
    if (!esAncho) setMenuAbierto(false);
  };

  const refrescarTodo = () => {
    loadData();                      // las pestañas que se dibujan acá mismo
    setRecarga((n) => n + 1);        // y las que son un componente aparte
  };
  // Cuánto trabajo espera en cada pestaña, y cuántos usuarios hay.
  //
  // Antes esto se calculaba descargando CUATRO LISTAS COMPLETAS y midiendo su
  // largo acá. «Usuarios totales» mentía pasados los 1000 y «Recargas
  // pendientes» pasadas las 100, porque las rutas cortan ahí. Ahora lo cuenta
  // la base. Ver `backend/services/pendientes.py`.
  const [pendientes, setPendientes] = useState({});
  const [usuariosTotales, setUsuariosTotales] = useState(null);
  // El banco que el operador elige a mano para una recarga que nacio sin el.
  const [users, setUsers] = useState([]);

  const [newRate, setNewRate] = useState('');
  const [newRateVesToRis, setNewRateVesToRis] = useState('');
  const [newRateBrlToRis, setNewRateBrlToRis] = useState('');
  const [selectedUser, setSelectedUser] = useState(null);
  const [userHistory, setUserHistory] = useState(null);
  const [loadingUser, setLoadingUser] = useState(false);
  const [resumenDeCuentas, setResumenDeCuentas] = useState(null);
  // La salud de la aplicación (si la base responde, si está el candado del
  // CPF). Sólo la ve el super administrador: la ruta lo exige, y si contesta
  // 403 la tira no se dibuja.
  const [saludDeLaApp, setSaludDeLaApp] = useState(null);
  // Los CPF repetidos (dos cuentas con el mismo documento). Sólo el super
  // administrador los ve y los resuelve; liberar el CPF de una cuenta lleva
  // motivo y queda en la auditoría.
  const [cpfRepetidos, setCpfRepetidos] = useState(null);
  const [motivoDeLiberacion, setMotivoDeLiberacion] = useState({});      // user_id → motivo escrito
  const [liberando, setLiberando] = useState(false);
  const cargarCpfRepetidos = useCallback(() => {
    if (user?.role !== 'super_admin') return;
    api.get('/admin/cpf-repetidos').then((r) => setCpfRepetidos(r.data)).catch(() => {});
  }, [user?.role]);
  useEffect(() => { cargarCpfRepetidos(); }, [cargarCpfRepetidos]);
  const liberarCpf = async (userId) => {
    const motivo = (motivoDeLiberacion[userId] || '').trim();
    if (!motivo) return toast.error('Escribí el motivo: se le saca un documento de identidad a una cuenta');
    setLiberando(true);
    try {
      const r = await api.post(`/admin/users/${userId}/cpf/liberar`, { motivo });
      toast.success(r.data.quedan_repetidos === 0 ? 'CPF liberado · no quedan repetidos y el candado quedó creado' : `CPF liberado · quedan ${r.data.quedan_repetidos} repetidos`);
      setMotivoDeLiberacion((m) => ({ ...m, [userId]: '' }));
      cargarCpfRepetidos();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo liberar'); }
    finally { setLiberando(false); }
  };
  useEffect(() => {
    if (user?.role !== 'super_admin') return;
    let vigente = true;
    api.get('/admin/salud').then((r) => { if (vigente) setSaludDeLaApp(r.data); }).catch(() => {});
    return () => { vigente = false; };
  }, [user?.role]);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [selectedUserForRole, setSelectedUserForRole] = useState(null);
  const [assigningRole, setAssigningRole] = useState(false);
  const [bajandoFicha, setBajandoFicha] = useState(false);
  // Partner/Gestor management states
  const [partnerSearchQuery, setPartnerSearchQuery] = useState('');
  // Support requests state
  const [supportRequests, setSupportRequests] = useState([]);
  const [supportFilter, setSupportFilter] = useState('pending'); // 'pending', 'resolved', 'all'
  const [supportSearch, setSupportSearch] = useState('');
  const [supportAssignFilter, setSupportAssignFilter] = useState('all');
  const [replyingTo, setReplyingTo] = useState(null);
  const [supportReplyText, setSupportReplyText] = useState('');
  const [sendingReply, setSendingReply] = useState(false);
  // Chat state
  const [agentRatings, setAgentRatings] = useState(null);
  /* El chat de soporte vivía acá: veinte piezas de estado, las cargas, el
     claim/release y las respuestas rápidas, todo mezclado con el resto
     del panel. Se fue entero a `components/admin/MesaDeAyuda.jsx`. Lo
     que queda abajo es lo que TAMBIEN usan otras pestañas. */
  const [accountingBanks, setAccountingBanks] = useState([]);
  // Modal para rechazar recarga VES

  // === BTC Orders State ===
  const [btcOrdenesP, setBtcOrdenesP] = useState([]);
  const [comprobanteByOrden, setComprobanteByOrden] = useState({});
  const [btcSubTab, setBtcSubTab] = useState('pendientes'); // pendientes | historial | configuracion
  const [loadingBtcOrdenes, setLoadingBtcOrdenes] = useState(false);
  const [marcandoBtc, setMarcandoBtc] = useState(null);

  useEffect(() => { loadData(); }, [activeTab]);

  useEffect(() => {
    api.get('/admin/accounting/banks').then(res => setAccountingBanks(res.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
  }, []);

  // Un solo pedido para las nueve secciones. El servidor devuelve únicamente
  // los contadores de las que ESTE usuario puede abrir: un contador es
  // información, y «hay 14 retiros pendientes» le dice a quien no puede verlos
  // cuánto dinero está esperando salir.
  const cargarPendientes = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/pendientes');
      setPendientes(data?.pendientes || {});
      setUsuariosTotales(data?.usuarios ?? null);
    } catch {
      // Es un adorno del panel: si no se puede contar, las pestañas quedan sin
      // número y se sigue trabajando igual.
    }
  }, []);

  // Cada minuto, Y CADA VEZ QUE SE CAMBIA DE PESTAÑA.
  //
  // Faltaba lo segundo, y se notaba: el operador entraba a una sección,
  // resolvía lo que había, y el número de la pestaña seguía ahí hasta que el
  // reloj de sesenta segundos volviera a pasar. Parecía un contador pegado.
  //
  // Un pedido más por pestaña es barato: `/admin/pendientes` son unos
  // `count_documents` con índice, y se dispara cuando la persona cambia de
  // sección —no en un bucle—.
  useEffect(() => {
    cargarPendientes();
    const reloj = setInterval(cargarPendientes, 60000);
    return () => clearInterval(reloj);
  }, [cargarPendientes, activeTab]);

  // CRM no tiene trabajo propio: es la puerta a KYC, Soporte y las demás. Su
  // número es la suma de lo que hay adentro, o la pestaña se ve vacía mientras
  // hay ocho KYC esperando a un clic de distancia.
  // Las mismas reglas de siempre, en un solo lugar en vez de repartidas entre
  // la tira de arriba y la de las subpestañas.
  const puedeVerSeccion = (clave) => {
    if (isAgent) {
      return ['chat', 'support', 'users', 'kyc', 'blacklist', 'operacion']
        .includes(clave);
    }
    if (clave === 'ratings') return user?.role === 'super_admin';
    return !POR_CLAVE[clave]?.superAdminOnly || user?.role === 'super_admin';
  };

  const gruposVisibles = GRUPOS
    .map((g) => ({ ...g, hijas: g.hijas.filter(puedeVerSeccion) }))
    .filter((g) => g.hijas.length > 0);

  const grupoActivo = gruposVisibles.find((g) => g.hijas.includes(activeTab))
    || gruposVisibles[0];

  // EL CONTADOR SUBE AL GRUPO, Y NO ES UN ADORNO
  //
  //   El número que dice cuánto espera vivía en la pestaña de cada sección, y
  //   eso se hizo a propósito: quien entra al panel tiene que ver DESDE AFUERA
  //   dónde hay cola. Al agrupar, ese número queda un nivel más adentro.
  //
  //   Así que el grupo muestra la suma y cada sección conserva el suyo:
  //   «Operación 7» se ve de entrada, y al abrirlo se ve que son 4 de Órdenes
  //   y 3 de Retiros. Sin esto, agrupar escondería justo la señal que dice por
  //   dónde empezar.
  const pendientesDe = (clave) => pendientes[clave] || 0;

  const pendientesDelGrupo = (grupo) =>
    grupo.hijas.reduce((suma, clave) => suma + pendientesDe(clave), 0);

  const loadData = async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case 'overview':
          await cargarPendientes();
          break;
        case 'users':
          const usersRes = await api.get('/admin/users');
          setUsers(usersRes.data?.users || []);
          setResumenDeCuentas(usersRes.data?.resumen || null);
          break;
        case 'kyc':
          // Handled fully by <KycPanel/> (it fetches its own data via /admin/kyc/list)
          break;
        case 'support':
          const supportRes = await api.get('/admin/support-requests');
          setSupportRequests(supportRes.data?.requests || []);
          break;
        case 'ratings':
          const ratingsRes = await api.get('/admin/agent-ratings');
          setAgentRatings(ratingsRes.data?.agents || []);
          break;
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Después de aprobar o rechazar un KYC, los contadores se ponen al día solos
  // (el KycPanel lleva su propia lista).
  const refreshKycStats = cargarPendientes;

  const handleSetAgent = async (u) => {
    const makeAgent = u.role !== 'agent';
    if (!await confirmar({
      titulo: makeAgent
        ? `¿Convertir a ${u.name || u.email} en agente de soporte?`
        : `¿Quitarle el rol de agente a ${u.name || u.email}?`,
      detalle: makeAgent
        ? 'Va a poder ver y responder los tickets de soporte.'
        : 'Deja de ver los tickets de soporte.',
      accion: makeAgent ? 'Convertir en agente' : 'Quitar el rol',
      tono: makeAgent ? undefined : 'peligro',
    })) return;
    try {
      await api.post(`/admin/users/${u.user_id}/set-agent`, { is_agent: makeAgent });
      toast.success(makeAgent ? 'Ahora es agente de soporte' : 'Rol de agente quitado');
      loadData();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo cambiar el rol');
    }
  };

  const handleBanUser = async (u) => {
    if (!u?.email) { toast.error('Este usuario no tiene correo'); return; }
    if (!await confirmar({
      titulo: `¿Agregar a ${u.name || u.email} a la lista negra?`,
      detalle: `El correo ${u.email} no va a poder registrarse de nuevo NI ENTRAR con la cuenta que ya tiene. La cuenta sigue visible acá, marcada.`,
      accion: 'Agregar a la lista negra',
      tono: 'peligro',
    })) return;
    try {
      await api.post('/admin/blacklist', { type: 'email', value: u.email, reason: 'Agregado desde Usuarios' });
      toast.success('Usuario agregado a la lista negra');
      // Se marca la fila, no se la esconde. Antes acá se agregaba el correo
      // a un conjunto que el filtro usaba para sacarla de la tabla.
      setUsers((prev) => prev.map((x) =>
        x.user_id === u.user_id ? { ...x, estado: 'vetada' } : x));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo agregar a la lista negra');
    }
  };

  const handleChangeRole = async (newRole) => {
    if (!selectedUserForRole) return;
    setAssigningRole(true);
    try {
      const response = await api.post('/admin/change-role', {
        user_id: selectedUserForRole.user_id,
        new_role: newRole
      });
      toast.success(response.data.message);
      setShowRoleModal(false);
      setSelectedUserForRole(null);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al cambiar rol');
    } finally {
      setAssigningRole(false);
    }
  };

  const handleResetPassword = async (userId, userName) => {
    if (!confirm(`¿Restablecer contraseña de ${userName}? Se enviará una contraseña temporal por email.`)) return;
    
    try {
      const response = await api.post('/admin/reset-password', { user_id: userId });
      toast.success(
        <div>
          <p><strong>{response.data.message}</strong></p>
          <p style={{fontSize: '12px', marginTop: '4px'}}>
            Contraseña temporal: <code style={{background: '#f3f4f6', padding: '2px 6px', borderRadius: '4px'}}>{response.data.temp_password}</code>
          </p>
          {response.data.email_sent && <p style={{fontSize: '11px', color: '#6b7280'}}>Email enviado al usuario</p>}
        </div>,
        { duration: 10000 }
      );
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al restablecer contraseña');
    }
  };

  const handleUpdateRate = async () => {
    if (!newRate || parseFloat(newRate) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        ris_to_ves: parseFloat(newRate)
      }); 
      toast.success('Tasa RIS → VES actualizada'); 
      refreshRates(); 
      setNewRate(''); 
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  const handleUpdateRateVesToRis = async () => {
    if (!newRateVesToRis || parseFloat(newRateVesToRis) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        ves_to_ris_rate: parseFloat(newRateVesToRis)
      }); 
      toast.success('Tasa VES → RIS actualizada'); 
      refreshRates(); 
      setNewRateVesToRis('');
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  const handleUpdateRateBrlToRis = async () => {
    if (!newRateBrlToRis || parseFloat(newRateBrlToRis) <= 0) { toast.error('Ingresa una tasa válida'); return; }
    try { 
      await api.post('/admin/rates', { 
        brl_to_ris: parseFloat(newRateBrlToRis)
      }); 
      toast.success('Tasa BRL → RIS actualizada'); 
      refreshRates(); 
      setNewRateBrlToRis('');
    } 
    catch { toast.error('Error al actualizar tasa'); }
  };

  // Cargar historial completo de un usuario
  const loadUserHistory = async (userId) => {
    setLoadingUser(true);
    try {
      const response = await api.get(`/admin/users/${userId}/complete`);
      const data = response.data;
      setUserHistory({
        user: {
          ...data.profile,
          cpf: data.profile?.cpf_number || data.kyc?.cpf_number,
          cpf_number: data.profile?.cpf_number || data.kyc?.cpf_number,
          full_name: data.profile?.full_name || data.profile?.name,
          phone_number: data.profile?.phone_number || data.kyc?.phone_number,
          document_number: data.profile?.document_number || data.kyc?.document_number,
          verification_status: data.profile?.verification_status || data.kyc?.status,
          email: data.profile?.email,
          role: data.profile?.role,
          created_at: data.profile?.created_at,
          last_login: data.profile?.last_login,
          email_verified: data.profile?.email_verified,
          gestor_code: data.profile?.gestor_code,
          referral_code: data.profile?.referral_code,
          balance_ris: data.profile?.balance_ris,
          balance_ris_terceros: data.profile?.balance_ris_terceros,
        },
        stats: {
          total_recharged: data.stats?.total_recharged_ris || 0,
          total_withdrawn: data.stats?.total_withdrawn_ris || 0,
          total_ves_sent: data.stats?.total_ves_sent || 0,
        },
        recharges: (data.recharges || []).map(tx => ({
          ...tx,
          type: 'recharge',
          amount_output: tx.amount_ris,
          amount_ves: tx.amount_brl,
        })),
        withdrawals: (data.withdrawals || []).map(tx => ({
          ...tx,
          type: 'withdrawal',
          amount_input: tx.amount_ris,
          amount_output: tx.amount_ves,
          beneficiary_name: tx.beneficiary?.full_name,
          beneficiary_bank: tx.beneficiary?.bank,
        })),
        beneficiaries: data.beneficiaries || [],
      });
      const selectedUserData = users.find(u => u.user_id === userId);
      setSelectedUser(selectedUserData);
    } catch (error) {
      toast.error('Error al cargar historial del usuario');
      console.error(error);
    } finally {
      setLoadingUser(false);
    }
  };

  const closeUserModal = () => {
    setSelectedUser(null);
    setUserHistory(null);
  };

  // Filtrar usuarios por búsqueda.
  //
  // ACA SE ESCONDIA A QUIEN ESTUVIERA EN LA LISTA NEGRA, Y ESO ESTABA MAL.
  //
  // El filtro tenía además `!bannedEmails.has(...)`: vetabas a alguien y
  // desaparecía de la tabla. No lo veías, no le mirabas el saldo, no lo
  // sacabas de la lista desde acá. Y desde que el login también los frena,
  // quedaba una cuenta sobre la que acabás de actuar y que ya no podés mirar.
  //
  // Ahora se muestran, marcados con su estado. El estado lo decide el
  // servidor en un solo lugar (`services/estado_de_la_cuenta.py`), no esta
  // pantalla: si lo dedujera acá, volvería a discrepar con el número del
  // Resumen, que es de donde salió todo esto.
  const filteredUsers = users.filter(u =>
    userSearchQuery === '' ||
    u.name?.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
    u.email?.toLowerCase().includes(userSearchQuery.toLowerCase())
  );

  const supportCounts = {
    pending: supportRequests.filter((r) => r.status === 'pending').length,
    resolved: supportRequests.filter((r) => r.status === 'resolved').length,
    all: supportRequests.length,
  };

  const filteredSupport = supportRequests.filter((req) => {
    if (supportFilter !== 'all' && req.status !== supportFilter) return false;
    if (supportAssignFilter === 'mine' && req.assigned_to !== user?.user_id) return false;
    if (supportAssignFilter === 'unassigned' && req.assigned_to) return false;
    const q = supportSearch.trim().toLowerCase();
    if (!q) return true;
    return (req.subject || '').toLowerCase().includes(q) || (req.email || '').toLowerCase().includes(q) || (req.message || '').toLowerCase().includes(q);
  });

  const loadSupportRequests = async () => {
    try {
      const res = await api.get('/admin/support-requests');
      setSupportRequests(res.data?.requests || []);
    } catch (e) { /* silencioso */ }
  };

  const claimRequest = async (req) => {
    try {
      const res = await api.post(`/admin/support-requests/${req.support_id}/claim`);
      if (res.data?.success) {
        toast.success(res.data?.already_mine ? 'Ya atendías este caso' : 'Tomaste este caso');
      } else {
        toast.error(`Ya lo atiende ${res.data?.assigned_to_name || 'otro operador'}`);
      }
      loadSupportRequests();
    } catch (e) {
      toast.error('No se pudo tomar el caso');
    }
  };

  const releaseRequest = async (req) => {
    try {
      await api.post(`/admin/support-requests/${req.support_id}/release`);
      toast.success('Caso liberado');
      loadSupportRequests();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo liberar');
    }
  };

  const setSupportPriority = async (req, priority) => {
    try {
      await api.post(`/admin/support-requests/${req.support_id}/priority`, { priority });
      setSupportRequests((prev) => prev.map((r) => (r.support_id === req.support_id ? { ...r, priority } : r)));
    } catch (e) {
      toast.error('No se pudo cambiar la prioridad');
    }
  };

  useEffect(() => {
    if (activeTab !== 'support') return;
    const t = setInterval(() => { loadSupportRequests(); }, 6000);
    return () => clearInterval(t);
  }, [activeTab]);

  const sendSupportReply = async (req) => {
    const text = supportReplyText.trim();
    if (!text) { toast.error('Escribe una respuesta'); return; }
    setSendingReply(true);
    try {
      const res = await api.post(`/admin/support-requests/${req.support_id}/reply`, { message: text });
      if (res.data?.email_sent) {
        toast.success('Respuesta enviada por correo');
      } else {
        toast.error(res.data?.message || 'Respuesta guardada, pero el correo no se envió');
      }
      setReplyingTo(null);
      setSupportReplyText('');
      loadData();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo enviar la respuesta');
    } finally {
      setSendingReply(false);
    }
  };

  const pageStyle = { minHeight: '100vh', background: '#f8f9fc', fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' };
  const cardStyle = { backgroundColor: '#ffffff', borderRadius: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #e5e7eb' };
  const btnPrimary = { backgroundColor: '#6366f1', color: 'white', borderRadius: '12px', padding: '10px 20px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px' };
  const btnSuccess = { backgroundColor: '#16a34a', color: 'white', borderRadius: '10px', padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '13px' };
  const btnSecondary = { backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '12px', padding: '10px 20px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px' };


  // === BTC Orders Functions ===
  const fetchBtcOrdenesPendientes = async () => {
    try {
      setLoadingBtcOrdenes(true);
      const res = await api.get('/btc/operador/pendientes');
      setBtcOrdenesP(res.data.ordenes || []);
    } catch (e) {
      toast.error('Error cargando órdenes BTC');
      setBtcOrdenesP([]);
    } finally {
      setLoadingBtcOrdenes(false);
    }
  };

  // Las órdenes BTC se cargan al abrir la pestaña.
  //
  // Este efecto estaba escrito DENTRO de `handleMarcarBtcEnviado`, después de
  // su propio `finally`, por una llave mal puesta. Dos consecuencias, las dos
  // en producción:
  //
  //   1. Al abrir la pestaña BTC no se registraba ningún efecto, así que la
  //      lista salía vacía. La única forma de ver las órdenes era el botón de
  //      refrescar. Una orden pendiente que nadie ve es una persona esperando.
  //   2. Marcar una orden como enviada llamaba a `useEffect` dentro de una
  //      función async: «Invalid hook call», y la pantalla se caía justo
  //      después de haber mandado la plata.
  //
  // Nada fallaba al compilar y el linter lo marcaba entre otros 150 avisos.
  useEffect(() => {
    if (activeTab === 'btc') {
      fetchBtcOrdenesPendientes();
    }
    // `fetchBtcOrdenesPendientes` se redefine en cada render y ponerla en las
    // dependencias volvería a pedir las órdenes todo el tiempo. Lo que tiene
    // que disparar la carga es cambiar de pestaña, y eso es `activeTab`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleComprobanteSelect = (remesa_id, file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setComprobanteByOrden((prev) => ({ ...prev, [remesa_id]: reader.result }));
    reader.readAsDataURL(file);
  };

  const handleMarcarBtcEnviado = async (remesa_id) => {
    if (!await confirmar({
      titulo: '¿Ya le hiciste la transferencia al beneficiario?',
      detalle: 'Al confirmar, la orden queda como enviada y el usuario recibe el aviso.',
      accion: 'Sí, ya la hice',
    })) return;
    try {
      setMarcandoBtc(remesa_id);
      await api.post('/admin/btc/marcar-enviado', { remesa_id, comprobante: comprobanteByOrden[remesa_id] || null });
      toast.success('Orden marcada como enviada exitosamente');
      setComprobanteByOrden((prev) => { const c = { ...prev }; delete c[remesa_id]; return c; });
      fetchBtcOrdenesPendientes();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error al marcar como enviado');
    } finally {
      setMarcandoBtc(null);
    }
  };

  return (
    <div style={pageStyle} data-testid="admin-panel">
      {/* Header */}
      <header style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e5e7eb', position: 'sticky', top: 0, zIndex: 40 }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '64px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              {!esAncho && (
                <button onClick={() => setMenuAbierto((a) => !a)}
                  data-testid="boton-menu"
                  style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Menu style={{ width: '20px', height: '20px', color: '#374151' }} />
                </button>
              )}
              <button onClick={() => navigate('/')} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="back-button">
                <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
              </button>
              <div>
                <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Panel de Control</h1>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{user?.role === 'super_admin' ? 'Super Admin' : user?.role === 'agent' ? 'Agente' : 'Admin'}</p>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {/* Lo que el equipo tiene que atender. Hasta ahora esta campana no
                  existía acá: para enterarse de un KYC nuevo había que salirse
                  del panel a una pantalla de cliente. */}
              <CampanaDelEquipo onIrA={setActiveTab} />
              <RestoreButton userRole={user?.role} onSuccess={loadData} size="sm"
                soloIcono={!esAncho} />
              <button onClick={refrescarTodo} title="Actualizar esta sección" style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="refresh-button">
                <RefreshCw style={{ width: '20px', height: '20px', color: '#374151', animation: loading ? 'spin 1s linear infinite' : 'none' }} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* El menú de las secciones: fijo al costado en pantalla ancha, y
          plegado detrás del botón del encabezado en el teléfono. */}
      <div style={{ display: 'flex', alignItems: 'flex-start', maxWidth: '1440px', margin: '0 auto' }}>
        {/* La sombra que tapa el contenido mientras el menú está abierto. Se
            toca y se cierra: en un teléfono es más fácil que buscar la X. */}
        {!esAncho && menuAbierto && (
          <div onClick={() => setMenuAbierto(false)}
            style={{ position: 'fixed', inset: '64px 0 0 0', zIndex: 45,
                     backgroundColor: 'rgba(17,24,39,0.45)' }} />
        )}
        <aside style={{
          width: '236px', flexShrink: 0, backgroundColor: '#ffffff',
          borderRight: '1px solid #e5e7eb', padding: '18px 12px',
          overflowY: 'auto',
          ...(esAncho ? {
            minHeight: 'calc(100vh - 64px)', position: 'sticky', top: '64px',
            maxHeight: 'calc(100vh - 64px)',
          } : {
            position: 'fixed', top: '64px', bottom: 0, left: 0, zIndex: 50,
            boxShadow: '2px 0 16px rgba(0,0,0,0.12)',
            transform: menuAbierto ? 'translateX(0)' : 'translateX(-100%)',
            transition: 'transform 0.2s ease',
          }),
        }}>
          {gruposVisibles.map((grupo) => {
            // El grupo de la sección abierta no se pliega, aunque se haya
            // pedido: el menú tiene que poder mostrar dónde estás parada.
            const tieneLoAbierto = grupo.hijas.includes(activeTab);
            const abierto = tieneLoAbierto || desplegados.has(grupo.key);
            return (
            <div key={grupo.key} style={{
              marginBottom: '10px', paddingBottom: '10px',
              // La línea entre grupos. Antes la separación era sólo aire, y el
              // aire no se lee como una división: los títulos en gris chiquito
              // se veían como espacio sobrante y el menú parecía una lista
              // larga y plana de veinte cosas sueltas.
              borderBottom: '1px solid #f1f2f6',
            }}>
              <button onClick={() => desplegar(grupo.key)}
                data-testid={`grupo-${grupo.key}`}
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px', width: '100%',
                  padding: '7px 10px', marginBottom: '3px', borderRadius: '8px',
                  border: 'none', backgroundColor: 'transparent', cursor: 'pointer',
                  fontSize: '11.5px', fontWeight: 800, color: '#111827',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>
                <grupo.icon style={{ width: '14px', height: '14px', color: '#6366f1' }} />
                <span style={{ flex: 1, textAlign: 'left' }}>{grupo.label}</span>
                <Pendiente cuantos={pendientesDelGrupo(grupo)} activa={false} />
                <ChevronRight style={{
                  width: '14px', height: '14px', color: '#c2c6d0',
                  transform: abierto ? 'rotate(90deg)' : 'none',
                  transition: 'transform 0.15s',
                }} />
              </button>
              {abierto && grupo.hijas.map((clave) => {
                const s = POR_CLAVE[clave];
                if (!s) return null;
                const activa = activeTab === clave;
                return (
                  <button key={clave} onClick={() => irA(clave)}
                    data-testid={`tab-${clave}`}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '9px', width: '100%',
                      padding: '8px 10px', marginBottom: '2px', borderRadius: '9px',
                      border: 'none', cursor: 'pointer', textAlign: 'left',
                      fontSize: '13.5px', fontWeight: activa ? 600 : 500,
                      backgroundColor: activa ? '#eef2ff' : 'transparent',
                      color: activa ? '#4338ca' : '#4b5563',
                    }}
                  >
                    <s.icon style={{ width: '16px', height: '16px', flexShrink: 0 }} />
                    <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden',
                                   textOverflow: 'ellipsis' }}>{s.label}</span>
                    <Pendiente cuantos={pendientesDe(clave)} activa={false} />
                  </button>
                );
              })}
            </div>
          );})}
        </aside>

      <main key={recarga} style={{ flex: 1, minWidth: 0, padding: esAncho ? '24px' : '16px' }}>
        {/* Overview Tab */}
        {activeTab === 'ordenes' && (
          <OrdenesPorProcesar />
        )}

        {activeTab === 'diferencias' && user?.role === 'super_admin' && (
          <DiferenciasPago />
        )}

        {activeTab === 'reportes' && (
          <Reportes />
        )}
        {activeTab === 'seguridad' && user?.role === 'super_admin' && (
          <SeguridadFinanciera irAlLibro={irAlLibro} />
        )}

        {activeTab === 'cobros' && user?.role === 'super_admin' && (
          <CobrosSinAcreditar />
        )}

        {activeTab === 'hoja_mp' && (
          <ErrorBoundary clave="hoja_mp" donde="Pagos de Mercado Pago">
            <HojaDeMercadoPago />
          </ErrorBoundary>
        )}

        {activeTab === 'ledger' && (
          <LibroMayor vistaInicial={searchParams.get('vista')} />
        )}
        {activeTab === 'rrhh' && (
          <ErrorBoundary clave="rrhh" donde="Recursos Humanos">
            <RecursosHumanos />
          </ErrorBoundary>
        )}
        {activeTab === 'auditoria' && (
          <ErrorBoundary clave="auditoria" donde="Libro de auditoría">
            <LibroAuditoria />
          </ErrorBoundary>
        )}
        {activeTab === 'errores' && (
          <ErrorBoundary clave="errores" donde="Errores del servidor">
            <Errores />
          </ErrorBoundary>
        )}
        {activeTab === 'nucleo' && (
          <ErrorBoundary clave="nucleo" donde="Núcleo de cuentas">
            <Nucleo />
          </ErrorBoundary>
        )}
        {activeTab === 'configuracion' && (
          <ErrorBoundary clave="configuracion" donde="Configuración">
            <Configuracion />
          </ErrorBoundary>
        )}
        {activeTab === 'respaldo' && (
          <ErrorBoundary clave="respaldo" donde="Respaldo de la base">
            <Respaldo />
          </ErrorBoundary>
        )}
        {activeTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {saludDeLaApp ? (
              <div style={{ ...cardStyle, padding: '12px 16px', display: 'flex', flexWrap: 'wrap', gap: '8px 18px', alignItems: 'center', borderLeft: `4px solid ${saludDeLaApp.ok ? '#16a34a' : '#dc2626'}` }} data-testid="salud-de-la-app">
                <strong style={{ fontSize: '14px', color: saludDeLaApp.ok ? '#166534' : '#991b1b' }}>Salud de la aplicación · {saludDeLaApp.ok ? 'sana' : 'NO SANA'}</strong>
                {saludDeLaApp.comprobaciones.map((c) => (
                  <span key={c.nombre} style={{ fontSize: '13px', color: c.ok ? '#374151' : '#b91c1c' }} data-testid={`salud-de-la-app-${c.ok ? 'ok' : 'falla'}`}>
                    {c.ok ? '✓' : '✗'} <strong>{c.nombre.replaceAll('_', ' ')}</strong>: {c.detalle}
                  </span>
                ))}
                <span style={{ fontSize: '12px', color: '#6b7280', marginLeft: 'auto' }}>el reloj revisa cada {Math.round(saludDeLaApp.vigilancia.cada_segundos / 60)} min y avisa al equipo cuando cambia</span>
              </div>
            ) : null}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              {[
                { icon: ArrowUpRight, value: pendientes.withdrawals ?? 0, label: 'Retiros pendientes', bg: '#fef3c7', iconColor: '#d97706' },
                { icon: ArrowDownLeft, value: pendientes.recharges ?? 0, label: 'Recargas pendientes', bg: '#dcfce7', iconColor: '#16a34a' },
                { icon: Users, value: usuariosTotales ?? 0, label: 'Usuarios activos', bg: '#dbeafe', iconColor: '#2563eb' },
                { icon: Shield, value: pendientes.kyc ?? 0, label: 'KYC pendientes', bg: '#f3e8ff', iconColor: '#9333ea' },
              ].map((item, i) => (
                <div key={i} style={{ ...cardStyle, padding: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ width: '44px', height: '44px', borderRadius: '14px', backgroundColor: item.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <item.icon style={{ width: '22px', height: '22px', color: item.iconColor }} />
                    </div>
                    <span style={{ fontSize: '28px', fontWeight: '700', color: '#111827' }}>{item.value}</span>
                  </div>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>{item.label}</p>
                </div>
              ))}
            </div>
            
            {/* Maintenance Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
              <div style={{ ...cardStyle, padding: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#fefce8', border: '1px solid #fef08a' }}>
                <div>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: '600', color: '#854d0e' }}>Reparar Imágenes</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#a16207' }}>Convierte URLs de Twilio a base64 para que se vean correctamente</p>
                </div>
                <button
                  onClick={async () => {
                    try {
                      toast('Procesando imágenes... puede tardar unos segundos');
                      const res = await api.post('/admin/fix-media-urls');
                      toast.success(`Imágenes convertidas: ${res.data.transactions_fixed}`);
                      if (res.data.errors?.length > 0) {
                        toast.error(`Errores: ${res.data.errors.length}`);
                      }
                      loadData();
                    } catch (e) {
                      toast.error('Error al corregir imágenes');
                    }
                  }}
                  style={{ padding: '12px 20px', borderRadius: '12px', border: 'none', backgroundColor: '#ca8a04', color: 'white', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}
                  data-testid="fix-media-btn"
                >
                  Reparar Imágenes
                </button>
              </div>
            </div>
            
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 16px 0' }}>Tasa actual</h3>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
                <div>
                  <p style={{ fontSize: '32px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {fmt(rates?.ris_to_ves) || '0.00'} VES</p>
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    Última actualización: {rates?.updated_at
                      ? new Date(rates.updated_at).toLocaleString('es-VE', { timeZone: 'America/Caracas', dateStyle: 'short', timeStyle: 'medium' })
                      : '—'}
                  </p>
                </div>
                {/* «Historial» vivía en la tarjeta de la tasa automática, que se
                    eliminó con la tasa nocturna. Se esconde solo para quien no
                    es super administrador: la ruta es sólo suya. */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <RateHistoryButton userRole={user?.role} />
                  <button onClick={() => setActiveTab('rates')} style={btnPrimary}>Modificar</button>
                </div>
              </div>
            </div>

            <BcvRatesCard />
          </div>
        )}

        {activeTab === 'uso' && (
          <ErrorBoundary clave="uso" donde="Uso de la aplicación">
            <Uso />
          </ErrorBoundary>
        )}

        {/* Withdrawals Tab */}
        {activeTab === 'withdrawals' && (
          <Retiros
            accountingBanks={accountingBanks}
            user={user}
            onProcesada={loadData}
          />
        )}

        {/* Recharges Tab */}
        {/* Recharges VES Tab */}
        {activeTab === 'recharges' && (
          <RecargasVES
            accountingBanks={accountingBanks}
            user={user}
            onProcesada={loadData}
          />
        )}

        {/* Partners Tab - Socios y Gestores */}
        {activeTab === 'users' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {cpfRepetidos && (cpfRepetidos.repetidos.length > 0 || !cpfRepetidos.candado) ? (
              <div style={{ ...cardStyle, padding: '16px', borderLeft: '4px solid #dc2626' }} data-testid="cpf-repetidos">
                <h3 style={{ margin: '0 0 6px', fontSize: '15px', color: '#991b1b' }}>CPF repetidos: {cpfRepetidos.repetidos.length} documento{cpfRepetidos.repetidos.length === 1 ? '' : 's'} con más de una cuenta</h3>
                <p style={{ margin: '0 0 12px', fontSize: '13px', color: '#6b7280', lineHeight: 1.5 }}>
                  Mientras haya repetidos no se puede crear el candado que impide registrar dos cuentas con el mismo CPF{cpfRepetidos.candado ? '' : ' (hoy falta)'}. Mirá las dos cuentas, decidí cuál es la buena, y liberá el CPF de la otra: no se borra ni se le toca el saldo, sólo pierde el documento, con tu motivo asentado en la auditoría.
                </p>
                {cpfRepetidos.repetidos.map((r) => (
                  <div key={r.cpf} style={{ border: '1px solid #fecaca', borderRadius: '10px', padding: '10px 12px', marginBottom: '10px' }} data-testid="cpf-repetido">
                    <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: '13px', marginBottom: '6px' }}>CPF {r.cpf}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '10px' }}>
                      {r.cuentas.map((c) => (
                        <div key={c.user_id} style={{ background: '#fafafa', borderRadius: '8px', padding: '10px', fontSize: '13px' }} data-testid="cpf-repetido-cuenta">
                          <div><strong>{c.nombre || '(sin nombre)'}</strong> · {c.email}</div>
                          <div style={{ color: '#6b7280', fontSize: '12px' }}>creada {c.creada ? new Date(c.creada).toLocaleDateString('es-AR') : '—'} · último ingreso {c.ultimo_ingreso ? new Date(c.ultimo_ingreso).toLocaleDateString('es-AR') : 'nunca'} · verificación {c.verificacion || '—'} · saldo RIS {c.saldo_ris.toLocaleString('es-AR', { minimumFractionDigits: 2 })}{c.vetada ? ' · VETADA' : ''}{c.borrada ? ' · BORRADA' : ''}</div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                            <input value={motivoDeLiberacion[c.user_id] || ''} onChange={(e) => setMotivoDeLiberacion((m) => ({ ...m, [c.user_id]: e.target.value }))} placeholder="Motivo para liberar el CPF de esta cuenta" style={{ flex: 1, padding: '6px 8px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '12px' }} data-testid="cpf-motivo" />
                            <button type="button" onClick={() => liberarCpf(c.user_id)} disabled={liberando} style={{ padding: '6px 10px', borderRadius: '8px', border: 'none', background: '#dc2626', color: '#fff', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }} data-testid="cpf-liberar">Liberar el CPF de esta cuenta</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
            {/* Search bar */}
            <div style={{ ...cardStyle, padding: '16px' }}>
              <div style={{ position: 'relative' }}>
                <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                <input 
                  type="text" 
                  placeholder="Buscar usuario por nombre o email..." 
                  value={userSearchQuery} 
                  onChange={(e) => setUserSearchQuery(e.target.value)}
                  style={{ width: '100%', padding: '12px 12px 12px 40px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none' }} 
                />
              </div>
            </div>

            {/* De qué está hecho ese total.
                Sin esto, la tarjeta del Resumen dice un número y la tabla
                muestra otra cantidad de filas, y no hay forma de saber por
                qué. Los grupos son excluyentes y suman el total: eso es lo
                que los hace conciliables. Lo decide el servidor, en
                `services/estado_de_la_cuenta.py`. */}
            {resumenDeCuentas && (
              <div style={{ ...cardStyle, padding: '12px 16px', display: 'flex', flexWrap: 'wrap',
                            gap: '16px', fontSize: '13px', color: '#6b7280' }}
                   data-testid="resumen-de-cuentas">
                <span><strong style={{ color: '#111827' }}>{resumenDeCuentas.total}</strong> cuentas</span>
                <span><strong style={{ color: '#111827' }}>{resumenDeCuentas.activa}</strong> activas</span>
                {resumenDeCuentas.vetada > 0 && <span>{resumenDeCuentas.vetada} en lista negra</span>}
                {resumenDeCuentas.suspendida > 0 && <span>{resumenDeCuentas.suspendida} suspendidas</span>}
                {resumenDeCuentas.borrada > 0 && <span>{resumenDeCuentas.borrada} borradas</span>}
              </div>
            )}

            {/* Users List */}
            <div style={{ ...cardStyle, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
              ) : filteredUsers.length === 0 ? (
                <div style={{ padding: '48px', textAlign: 'center' }}><p style={{ color: '#6b7280' }}>No se encontraron usuarios</p></div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead style={{ backgroundColor: '#f8f9fa' }}>
                      <tr>
                        {['Usuario', 'Balance', 'Estado', 'Rol', 'Acciones'].map(h => (
                          <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers.map((u) => (
                        <tr key={u.user_id} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', transition: 'background 0.2s' }} 
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f9fafb'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                            data-testid={`user-${u.user_id}`}>
                          <td style={{ padding: '16px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{u.name}</p>
                              {/* Por qué esta cuenta no puede entrar. Antes las vetadas
                                  no aparecían y las borradas se veían como cualquiera. */}
                              {NOMBRE_DEL_ESTADO[u.estado] && (
                                <span
                                  data-testid={`estado-${u.user_id}`}
                                  style={{
                                    padding: '2px 8px', borderRadius: '8px', fontSize: '11px',
                                    fontWeight: '600', whiteSpace: 'nowrap',
                                    backgroundColor: COLOR_DEL_ESTADO[u.estado]?.fondo,
                                    color: COLOR_DEL_ESTADO[u.estado]?.letra,
                                  }}>
                                  {NOMBRE_DEL_ESTADO[u.estado]}
                                </span>
                              )}
                            </div>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{u.email}</p>
                          </td>
                          <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>{fmt(u.balance_ris)} RIS</td>
                          <td style={{ padding: '16px' }}>
                            <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600',
                              backgroundColor: u.verification_status === 'verified' ? '#dcfce7' : '#f3f4f6',
                              color: u.verification_status === 'verified' ? '#16a34a' : '#6b7280' }}>
                              {u.verification_status === 'verified' ? 'Verificado' : 'Pendiente'}
                            </span>
                          </td>
                          <td style={{ padding: '16px', fontSize: '14px', color: '#6b7280' }}>
                            <span style={{ 
                              padding: '4px 10px', 
                              borderRadius: '8px', 
                              fontSize: '12px', 
                              fontWeight: '600',
                              backgroundColor: COLOR_DEL_ROL[u.role]?.fondo || '#f3f4f6',
                              color: COLOR_DEL_ROL[u.role]?.letra || '#6b7280'
                            }}>
                              {NOMBRE_DEL_ROL[u.role] || 'Usuario'}
                            </span>
                          </td>
                          <td style={{ padding: '16px', display: 'flex', gap: '8px' }}>
                            {/* Una cuenta borrada se ve, pero no se opera.
                                Se muestra —sus transacciones viejas tienen que
                                seguir teniendo dueño visible— y los botones que
                                la tocarían no tienen sentido: cambiarle el rol o
                                la clave a alguien que ya no existe sólo sirve
                                para confundir a quien lo aprieta. */}
                            {u.estado === 'borrada' ? (
                              <button
                                onClick={() => loadUserHistory(u.user_id)}
                                style={{
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#f3f4f6', color: '#6b7280', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`view-user-${u.user_id}`}
                              >
                                <Eye style={{ width: '14px', height: '14px' }} />
                                Ver
                              </button>
                            ) : (<>
                            <button 
                              onClick={() => loadUserHistory(u.user_id)}
                              style={{ 
                                display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                backgroundColor: '#dbeafe', color: '#2563eb', border: 'none',
                                borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                              }}
                              data-testid={`view-user-${u.user_id}`}
                            >
                              <Eye style={{ width: '14px', height: '14px' }} />
                              Ver
                            </button>
                            {user?.role === 'super_admin' && u.user_id !== user.user_id && (
                              <button 
                                onClick={() => { setSelectedUserForRole(u); setShowRoleModal(true); }}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#fef3c7', color: '#d97706', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`change-role-${u.user_id}`}
                              >
                                <UserCog style={{ width: '14px', height: '14px' }} />
                                Rol
                              </button>
                            )}
                            {user?.role === 'super_admin' && u.user_id !== user.user_id && (
                              <button 
                                onClick={() => handleResetPassword(u.user_id, u.name)}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#fee2e2', color: '#dc2626', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`reset-password-${u.user_id}`}
                              >
                                <KeyRound style={{ width: '14px', height: '14px' }} />
                                Clave
                              </button>
                            )}
                            {u.user_id !== user.user_id && (
                              <button 
                                onClick={() => handleBanUser(u)}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: '#1f2937', color: '#fff', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`ban-user-${u.user_id}`}
                              >
                                <Shield style={{ width: '14px', height: '14px' }} />
                                Lista negra
                              </button>
                            )}
                            {user?.role === 'super_admin' && u.user_id !== user.user_id && u.role !== 'super_admin' && (
                              <button 
                                onClick={() => handleSetAgent(u)}
                                style={{ 
                                  display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
                                  backgroundColor: u.role === 'agent' ? '#fef3c7' : '#ecfeff', color: u.role === 'agent' ? '#b45309' : '#0e7490', border: 'none',
                                  borderRadius: '10px', fontSize: '13px', fontWeight: '500', cursor: 'pointer'
                                }}
                                data-testid={`set-agent-${u.user_id}`}
                              >
                                <UserCog style={{ width: '14px', height: '14px' }} />
                                {u.role === 'agent' ? 'Quitar agente' : 'Hacer agente'}
                              </button>
                            )}
                            </>)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* KYC Tab (new modular panel: tabs, search, lightbox, audit log, reject reasons) */}
        {activeTab === 'blacklist' && (
          <ListaNegra />
        )}

        {activeTab === 'kyc' && (
          <KycPanel onChange={refreshKycStats} />
        )}

        {/* Rates Tab */}
        {activeTab === 'rates' && (
          <div style={{ maxWidth: '700px' }}>
            <div style={{ ...cardStyle, padding: '24px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 24px 0' }}>Configurar Tasas de Cambio</h3>
              
              {/* Current Rates Display */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
                <div style={{ padding: '20px', backgroundColor: '#dbeafe', borderRadius: '14px' }}>
                  <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>ENVÍOS (RIS → VES)</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>1 RIS = {fmt(rates?.ris_to_ves) || '110.00'} VES</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para retiros a Venezuela</p>
                </div>
                <div style={{ padding: '20px', backgroundColor: '#dcfce7', borderRadius: '14px' }}>
                  <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>RECARGAS VES (VES → RIS)</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>{fmt(rates?.ves_to_ris_rate) || '140.00'} VES = 1 RIS</p>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para recargas con Bolívares</p>
                </div>
              </div>
              
              {/* BRL Rate Display */}
              <div style={{ padding: '20px', backgroundColor: '#fef9c3', borderRadius: '14px', marginBottom: '24px' }}>
                <p style={{ fontSize: '12px', color: '#ca8a04', margin: '0 0 4px 0', fontWeight: '600' }}>RECARGAS PIX (BRL → RIS)</p>
                <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>1 BRL = {fmt(rates?.brl_to_ris) || '1.00'} RIS</p>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Tasa para recargas con PIX Brasil</p>
              </div>

              {/* Update Rates Form - Independent */}
              <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '24px' }}>
                <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#374151', margin: '0 0 16px 0' }}>Actualizar Tasas</h4>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                  {/* RIS → VES Rate */}
                  <div style={{ padding: '20px', backgroundColor: '#f0f9ff', borderRadius: '14px', border: '1px solid #bfdbfe' }}>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#2563eb', marginBottom: '12px' }}>
                      RIS → VES (Envíos)
                    </label>
                    <input 
                      type="number" 
                      value={newRate} 
                      onChange={(e) => setNewRate(e.target.value)}
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                      placeholder={rates?.ris_to_ves?.toString() || '0'} 
                      data-testid="new-rate-input" 
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>VES por cada 1 RIS enviado</p>
                    <button 
                      onClick={handleUpdateRate} 
                      style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#2563eb' }} 
                      data-testid="update-rate-button"
                    >
                      Actualizar RIS → VES
                    </button>
                  </div>

                  {/* VES → RIS Rate */}
                  <div style={{ padding: '20px', backgroundColor: '#f0fdf4', borderRadius: '14px', border: '1px solid #bbf7d0' }}>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#16a34a', marginBottom: '12px' }}>
                      VES → RIS (Recargas)
                    </label>
                    <input 
                      type="number" 
                      value={newRateVesToRis} 
                      onChange={(e) => setNewRateVesToRis(e.target.value)}
                      style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                      placeholder={rates?.ves_to_ris?.toString() || '0'} 
                      data-testid="new-rate-ves-input" 
                    />
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>VES necesarios para obtener 1 RIS</p>
                    <button 
                      onClick={handleUpdateRateVesToRis} 
                      style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#16a34a' }} 
                      data-testid="update-rate-ves-button"
                    >
                      Actualizar VES → RIS
                    </button>
                  </div>
                </div>
                
                {/* BRL → RIS Rate Form */}
                <div style={{ marginTop: '24px', padding: '20px', backgroundColor: '#fefce8', borderRadius: '14px', border: '1px solid #fde68a' }}>
                  <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', color: '#ca8a04', marginBottom: '12px' }}>
                    BRL → RIS (Recargas PIX)
                  </label>
                  <input 
                    type="number" 
                    step="0.01"
                    value={newRateBrlToRis} 
                    onChange={(e) => setNewRateBrlToRis(e.target.value)}
                    style={{ width: '100%', padding: '14px 16px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '16px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' }}
                    placeholder={rates?.brl_to_ris?.toString() || '1'} 
                    data-testid="new-rate-brl-input" 
                  />
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 12px 0' }}>RIS que recibirá por cada 1 BRL pagado</p>
                  <button 
                    onClick={handleUpdateRateBrlToRis} 
                    style={{ ...btnPrimary, width: '100%', height: '44px', backgroundColor: '#ca8a04' }} 
                    data-testid="update-rate-brl-button"
                  >
                    Actualizar BRL → RIS
                  </button>
                </div>
              </div>
              {/* Sección unificada: ruta BTC USDI→VES + referencias (BCV, precio BTC) */}
              <TasasBtcSection />
              {/* Tasa de envíos con saldo cripto (USDT/USDC → VES) */}
              <TasasCriptoSection />
            </div>
          </div>
        )}

        {/* Chat Tab */}
        {/* La mesa de ayuda. Lo que había acá era una lista de personas y
            una caja de texto: el asesor tenía dos botones y respondía a
            ciegas. Ahora es un componente aparte —tres columnas, con la
            ficha del cliente y las herramientas— y esta pantalla vuelve a
            ser sólo el marco de pestañas. */}
        {activeTab === 'chat' && <MesaDeAyuda usuario={user} />}

        {/* Support Requests Tab */}
        {activeTab === 'ratings' && (
          <div style={{ backgroundColor: 'white', borderRadius: '16px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#1f2937', margin: '0 0 4px 0' }}>Calificaciones por agente</h2>
            <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 20px 0' }}>Uso interno · basado en las estrellas que dejan los clientes al cerrarse un caso</p>
            {(!agentRatings || agentRatings.length === 0) ? (
              <p style={{ color: '#9ca3af', fontSize: '14px' }}>Aún no hay calificaciones.</p>
            ) : (
              agentRatings.map((ag) => (
                <div key={ag.agent_id} style={{ border: '1px solid #e5e7eb', borderRadius: '14px', padding: '18px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '16px', fontWeight: '700', color: '#1f2937' }}>{ag.agent_name}</span>
                      <span style={{ fontSize: '13px', color: '#6b7280' }}>{ag.count} {ag.count === 1 ? 'calificación' : 'calificaciones'}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ color: '#f59e0b', fontSize: '18px', letterSpacing: '2px' }}>{'★'.repeat(Math.round(ag.average))}{'☆'.repeat(5 - Math.round(ag.average))}</span>
                      <span style={{ fontSize: '15px', fontWeight: '700', color: '#1f2937' }}>{ag.average.toFixed(2)}</span>
                    </div>
                  </div>
                  <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {ag.ratings.map((r, i) => (
                      <div key={i} style={{ background: '#f9fafb', borderRadius: '10px', padding: '10px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                          <span style={{ color: '#f59e0b', fontSize: '14px', letterSpacing: '1px' }}>{'★'.repeat(r.stars || 0)}{'☆'.repeat(5 - (r.stars || 0))}</span>
                          <span style={{ fontSize: '11px', color: '#9ca3af' }}>{r.channel === 'chat' ? 'Chat' : 'Soporte'}{r.case_code ? ` · ${r.case_code}` : ''}{r.created_at ? ` · ${new Date(r.created_at).toLocaleDateString('es-ES')}` : ''}</span>
                        </div>
                        {r.comment && <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#374151', whiteSpace: 'pre-wrap' }}>{r.comment}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'support' && (
          <div style={{ padding: '0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#1f2937', margin: 0 }}>
                Solicitudes de Soporte
              </h2>
              <div style={{ display: 'flex', gap: '8px' }}>
                {['pending', 'resolved', 'all'].map(filter => (
                  <button 
                    key={filter}
                    onClick={() => setSupportFilter(filter)}
                    style={{ 
                      padding: '8px 16px', 
                      borderRadius: '10px', 
                      border: 'none', 
                      fontSize: '14px', 
                      fontWeight: '600',
                      cursor: 'pointer',
                      backgroundColor: supportFilter === filter ? '#6366f1' : '#f3f4f6',
                      color: supportFilter === filter ? '#fff' : '#6b7280'
                    }}
                    data-testid={`support-filter-${filter}`}
                  >
                    {(filter === 'pending' ? 'Pendientes' : filter === 'resolved' ? 'Resueltas' : 'Todas') +  ` (${supportCounts[filter]})`}
                  </button>
                ))}
              </div>
            </div>

            <input value={supportSearch} onChange={(e) => setSupportSearch(e.target.value)} placeholder="Buscar por asunto, correo o mensaje…" style={{ width: '100%', padding: '11px 14px', borderRadius: '10px', border: '1px solid #e5e7eb', fontSize: '14px', outline: 'none', boxSizing: 'border-box', marginBottom: '16px' }} />
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
              {[['all', 'Todos'], ['mine', 'Mis casos'], ['unassigned', 'Sin asignar']].map(([key, label]) => (
                <button key={key} onClick={() => setSupportAssignFilter(key)} style={{
                  padding: '7px 14px', borderRadius: '999px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                  border: supportAssignFilter === key ? '1px solid #6366f1' : '1px solid #e5e7eb',
                  backgroundColor: supportAssignFilter === key ? '#eef2ff' : '#fff', color: supportAssignFilter === key ? '#4F46E5' : '#6b7280'
                }}>{label}</button>
              ))}
            </div>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <RefreshCw className="animate-spin" style={{ width: '32px', height: '32px', color: '#6366f1' }} />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {filteredSupport
                  .map((request) => (
                    <div 
                      key={request.support_id} 
                      style={{ 
                        padding: '20px', 
                        backgroundColor: '#fff', 
                        borderRadius: '16px', 
                        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                        border: request.status === 'pending' ? '2px solid #fbbf24' : '1px solid #e5e7eb'
                      }}
                      data-testid={`support-request-${request.support_id}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span style={{ 
                              padding: '4px 10px', 
                              borderRadius: '20px', 
                              fontSize: '12px', 
                              fontWeight: '600',
                              backgroundColor: request.status === 'pending' ? '#fef3c7' : '#dcfce7',
                              color: request.status === 'pending' ? '#b45309' : '#16a34a'
                            }}>
                              {request.status === 'pending' ? 'Pendiente' : 'Resuelta'}
                            </span>
                            <span style={{ fontSize: '12px', color: '#6366f1', fontWeight: 700 }}>
                              {request.case_code || request.support_id}
                            </span>
                          </div>
                          <h4 style={{ fontSize: '16px', fontWeight: '600', color: '#1f2937', margin: '8px 0 4px 0' }}>
                            {request.subject}
                          </h4>
                        </div>
                        {request.status === 'pending' && (
                          <button
                            onClick={async () => {
                              try {
                                await api.post(`/admin/support-requests/${request.support_id}/resolve`);
                                toast.success('Solicitud marcada como resuelta');
                                loadData();
                              } catch (error) {
                                toast.error('Error al marcar como resuelta');
                              }
                            }}
                            style={{ 
                              padding: '8px 16px', 
                              borderRadius: '10px', 
                              border: 'none', 
                              backgroundColor: '#16a34a', 
                              color: '#fff', 
                              fontSize: '14px', 
                              fontWeight: '600',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}
                            data-testid={`resolve-support-${request.support_id}`}
                          >
                            <CheckCircle style={{ width: '16px', height: '16px' }} />
                            Marcar Resuelta
                          </button>
                        )}
                      </div>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Mail style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>{request.email}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Phone style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>{request.phone_number || 'No proporcionado'}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Clock style={{ width: '16px', height: '16px', color: '#6b7280' }} />
                          <span style={{ fontSize: '14px', color: '#374151' }}>
                            {new Date(request.created_at).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Caracas' })}
                          </span>
                        </div>
                      </div>
                      
                      <div style={{ padding: '12px', backgroundColor: '#f9fafb', borderRadius: '10px' }}>
                        <p style={{ fontSize: '14px', color: '#4b5563', margin: 0, lineHeight: '1.5' }}>
                          {request.message}
                        </p>
                      </div>
                      <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        {request.assigned_to ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 600, color: '#15803d', backgroundColor: '#dcfce7', padding: '6px 10px', borderRadius: '999px' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#22c55e' }} />
                            Atendido por {request.assigned_to_name || 'Operador'}
                            {(request.assigned_to === user?.user_id || user?.role === 'super_admin') && (
                              <button onClick={() => releaseRequest(request)} style={{ marginLeft: '6px', background: 'none', border: 'none', color: '#6b7280', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}>soltar</button>
                            )}
                          </span>
                        ) : (
                          <button onClick={() => claimRequest(request)} style={{ padding: '8px 16px', borderRadius: '10px', border: 'none', backgroundColor: '#6366f1', color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <UserCog style={{ width: '16px', height: '16px' }} />
                            Atender este caso
                          </button>
                        )}
                        <button
                          onClick={() => { setReplyingTo(replyingTo === request.support_id ? null : request.support_id); setSupportReplyText(''); }}
                          style={{ padding: '8px 16px', borderRadius: '10px', border: '1px solid #6366f1', backgroundColor: replyingTo === request.support_id ? '#eef2ff' : '#fff', color: '#6366f1', fontSize: '14px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                          data-testid={`reply-support-${request.support_id}`}
                        >
                          <Mail style={{ width: '16px', height: '16px' }} />
                          {replyingTo === request.support_id ? 'Cancelar' : 'Responder por correo'}
                        </button>
                        {request.responded_at && (
                          <span style={{ fontSize: '12px', color: '#16a34a', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <CheckCircle style={{ width: '14px', height: '14px' }} /> Respondida
                          </span>
                        )}
                                              <select value={request.priority || 'normal'} onChange={(e) => setSupportPriority(request, e.target.value)} title="Prioridad" style={{ marginLeft: 'auto', padding: '7px 10px', borderRadius: '10px', border: '1px solid #e5e7eb', fontSize: '13px', cursor: 'pointer', color: PRIORITY_COLORS[request.priority || 'normal'], fontWeight: 700 }}>
                          <option value="baja">Prioridad: Baja</option>
                          <option value="normal">Prioridad: Normal</option>
                          <option value="alta">Prioridad: Alta</option>
                          <option value="urgente">Prioridad: Urgente</option>
                        </select>
                      </div>
                      {replyingTo === request.support_id && (
                        <div style={{ marginTop: '10px' }}>
                          <textarea
                            value={supportReplyText}
                            onChange={(e) => setSupportReplyText(e.target.value)}
                            rows={3}
                            placeholder={`Escribe tu respuesta para ${request.email}…`}
                            style={{ width: '100%', padding: '12px 14px', borderRadius: '10px', border: '1px solid #e5e7eb', fontSize: '14px', outline: 'none', resize: 'vertical', boxSizing: 'border-box', fontFamily: 'inherit' }}
                          />
                          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                            <button
                              onClick={() => sendSupportReply(request)}
                              disabled={sendingReply}
                              style={{ padding: '9px 18px', borderRadius: '10px', border: 'none', backgroundColor: '#6366f1', color: '#fff', fontSize: '14px', fontWeight: 600, cursor: 'pointer', opacity: sendingReply ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                              <Send style={{ width: '16px', height: '16px' }} />
                              {sendingReply ? 'Enviando…' : 'Enviar respuesta'}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                
                {filteredSupport.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#9ca3af' }}>
                    <MessageSquare style={{ width: '48px', height: '48px', margin: '0 auto 12px', opacity: 0.5 }} />
                    <p style={{ fontSize: '16px', fontWeight: '500' }}>No hay solicitudes {supportFilter === 'pending' ? 'pendientes' : supportFilter === 'resolved' ? 'resueltas' : ''}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      
      {/* BTC Orders Tab */}
      {activeTab === 'btc' && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px' }}>
          {/* Sub-tabs nav */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
            {[
              { key: 'pendientes',    label: '⚡ Pendientes',     color: '#f59e0b' },
              { key: 'historial',     label: '📊 Historial',       color: '#6366f1' },
              { key: 'configuracion', label: '⚙️  Configuración', color: '#16a34a' },
            ].map((t) => {
              const active = btcSubTab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setBtcSubTab(t.key)}
                  data-testid={`btc-subtab-${t.key}`}
                  style={{
                    padding: '10px 18px', borderRadius: '12px',
                    border: active ? `2px solid ${t.color}` : '1.5px solid #e5e7eb',
                    backgroundColor: active ? '#fff' : '#fff',
                    color: active ? t.color : '#374151',
                    fontWeight: 600, fontSize: '14px', cursor: 'pointer',
                    boxShadow: active ? `0 4px 10px ${t.color}40` : 'none',
                    transition: 'all 0.15s',
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Sub-tab: Historial */}
          {btcSubTab === 'historial' && <BtcAdminHistorial />}

          {/* Sub-tab: Configuración */}
          {btcSubTab === 'configuracion' && <BtcAdminConfig />}

          {/* Sub-tab: Pendientes (original content) */}
          {btcSubTab === 'pendientes' && (<>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>⚡ Órdenes BTC Pendientes</h2>
              <p style={{ color: '#6b7280', fontSize: '14px', margin: '4px 0 0' }}>Órdenes que requieren transferencia manual al beneficiario</p>
            </div>
            <button onClick={fetchBtcOrdenesPendientes} disabled={loadingBtcOrdenes}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 18px', background: '#f59e0b', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: '700', cursor: 'pointer', fontSize: '14px', opacity: loadingBtcOrdenes ? 0.7 : 1 }}>
              {loadingBtcOrdenes ? '⏳ Cargando...' : '🔄 Actualizar'}
            </button>
          </div>

          {btcOrdenesP.length === 0 && !loadingBtcOrdenes ? (
            <div style={{ background: '#f9fafb', border: '1px dashed #d1d5db', borderRadius: '16px', padding: '48px', textAlign: 'center' }}>
              <p style={{ fontSize: '48px', margin: '0 0 12px' }}>✅</p>
              <h3 style={{ color: '#374151', fontWeight: '700', margin: '0 0 8px' }}>No hay órdenes pendientes</h3>
              <p style={{ color: '#9ca3af', fontSize: '14px', margin: 0 }}>Todas las órdenes BTC han sido procesadas</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {btcOrdenesP.map((orden) => (
                <div key={orden.remesa_id} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '16px', padding: '20px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                    <div>
                      <span style={{ background: '#fef3c7', color: '#d97706', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '700' }}>💰 PAGADO - PENDIENTE ENVÍO</span>
                      <p style={{ margin: '8px 0 0', fontSize: '13px', color: '#9ca3af', fontFamily: 'monospace' }}>ID: {orden.remesa_id}</p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ fontWeight: '800', fontSize: '18px', color: '#111827', margin: 0 }}>{Number(orden.ves_recibe || 0).toLocaleString('es-VE', { minimumFractionDigits: 2 })} Bs</p>
                      <p style={{ color: '#6b7280', fontSize: '13px', margin: '2px 0 0' }}>{Number(orden.usd_cliente || 0).toFixed(2)} USDI · {Number(orden.sats || 0).toLocaleString()} sats</p>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                    <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', padding: '14px' }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: '#166534', margin: '0 0 6px', letterSpacing: '0.05em' }}>BENEFICIARIO</p>
                      <p style={{ fontWeight: '700', color: '#111827', margin: '0 0 2px', fontSize: '15px' }}>{orden.beneficiario_data?.full_name || 'N/A'}</p>
                      {/* `id_document` y `phone_number` son los nombres con que se guarda un
                          beneficiario (`BeneficiaryCreate`). Esta tarjeta leía `cedula` y
                          `phone`, que no existen: cada orden salía con «CI: N/A» y, en
                          pago móvil, sin teléfono, y quien pagaba tenía que ir a buscarlos
                          a otro lado. Los nombres viejos quedan como respaldo, igual que en
                          `routes/btc_admin.py`. */}
                      <p style={{ color: '#374151', fontSize: '13px', margin: '0 0 2px' }}>CI: {orden.beneficiario_data?.id_document || orden.beneficiario_data?.cedula || 'N/A'}</p>
                      <p style={{ color: '#374151', fontSize: '13px', margin: 0 }}>
                        {orden.beneficiario_data?.payment_type === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}
                      </p>
                    </div>
                    <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '12px', padding: '14px' }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: '#1e40af', margin: '0 0 6px', letterSpacing: '0.05em' }}>DATOS PAGO</p>
                      {orden.beneficiario_data?.payment_type === 'pago_movil' ? (
                        <>
                          <p style={{ fontWeight: '600', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>📱 {orden.beneficiario_data?.phone_number || orden.beneficiario_data?.phone || 'N/A'}</p>
                          <p style={{ color: '#374151', fontSize: '13px', margin: 0 }}>{orden.beneficiario_data?.bank || 'N/A'}</p>
                        </>
                      ) : (
                        <>
                          <p style={{ fontWeight: '600', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>🏦 {orden.beneficiario_data?.bank || 'N/A'}</p>
                          <p style={{ color: '#374151', fontSize: '13px', margin: 0, fontFamily: 'monospace' }}>{orden.beneficiario_data?.account_number || 'N/A'}</p>
                        </>
                      )}
                    </div>
                  </div>

                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: '#374151', cursor: 'pointer' }}>
                      📎 {comprobanteByOrden[orden.remesa_id] ? 'Comprobante adjunto ✓' : 'Adjuntar comprobante (opcional)'}
                      <input type="file" accept="image/*" style={{ display: 'none' }}
                        onChange={(e) => handleComprobanteSelect(orden.remesa_id, e.target.files?.[0])} />
                    </label>
                    {comprobanteByOrden[orden.remesa_id] && (
                      <img src={rutaDeArchivo(comprobanteByOrden[orden.remesa_id])} alt="comprobante" style={{ display: 'block', marginTop: '8px', maxWidth: '160px', borderRadius: '8px', border: '1px solid #e5e7eb' }} />
                    )}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <p style={{ color: '#9ca3af', fontSize: '12px', margin: 0 }}>
                      📅 {orden.creado_en ? new Date(orden.creado_en).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                    </p>
                    <button onClick={() => handleMarcarBtcEnviado(orden.remesa_id)} disabled={marcandoBtc === orden.remesa_id}
                      style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', background: marcandoBtc === orden.remesa_id ? '#9ca3af' : '#10b981', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: '700', cursor: marcandoBtc === orden.remesa_id ? 'not-allowed' : 'pointer', fontSize: '14px' }}>
                      {marcandoBtc === orden.remesa_id ? '⏳ Procesando...' : '✅ Marcar como Enviado'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          </>)}
        </div>
      )}
      {activeTab === 'operacion' && (
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 16px 40px 16px' }}>
          <OperacionPanel onTrabajoHecho={cargarPendientes} />
        </div>
      )}

      {activeTab === 'envios' && user?.role === 'super_admin' && (
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 16px 40px 16px' }}>
          <EnviosPanel />
        </div>
      )}

      {/* Credits Cripto Tab (USDT/USDC via NOWPayments) — solo super_admin */}
      {activeTab === 'credits' && user?.role === 'super_admin' && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px 0' }}>
          <div style={{ marginBottom: '16px' }}>
            <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>💰 Créditos Cripto (USDT/USDC)</h2>
            <p style={{ color: '#6b7280', fontSize: '14px', margin: '4px 0 0' }}>
              Billetera de créditos cripto vía NOWPayments — totalmente separada de balance_ris
            </p>
          </div>
          <CreditsAdminPanel />
        </div>
      )}
</main>
      </div>

      {/* Process Withdrawal Modal */}

      {/* User History Modal */}
      {selectedUser && (
        <div 
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}
          onClick={closeUserModal}
        >
          <div 
            style={{ backgroundColor: '#ffffff', borderRadius: '24px', width: '100%', maxWidth: '800px', maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ padding: '24px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>{selectedUser.name}</h3>
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{selectedUser.email}</p>
              </div>
              <button onClick={closeUserModal} style={{ width: '36px', height: '36px', borderRadius: '10px', border: 'none', backgroundColor: '#f3f4f6', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Modal Content */}
            <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
              {loadingUser ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px' }}>
                  <RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} />
                </div>
              ) : userHistory ? (
                <>
                  {/* User Stats */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '24px' }}>
                    <div style={{ padding: '16px', backgroundColor: '#f0fdf4', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>BALANCE ACTUAL</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.user?.balance_ris ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#dbeafe', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL RECARGADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_recharged ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#d97706', margin: '0 0 4px 0', fontWeight: '600' }}>TOTAL ENVIADO</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_withdrawn ?? 0))} RIS
                      </p>
                    </div>
                    <div style={{ padding: '16px', backgroundColor: '#f3e8ff', borderRadius: '14px', textAlign: 'center' }}>
                      <p style={{ fontSize: '12px', color: '#9333ea', margin: '0 0 4px 0', fontWeight: '600' }}>VES ENVIADOS</p>
                      <p style={{ fontSize: '22px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        {fmt((userHistory.stats?.total_ves_sent ?? 0))}
                      </p>
                    </div>
                  </div>

                  {/* User Info - COMPLETE REGISTRATION DATA */}
                  <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>DATOS DE REGISTRO COMPLETOS</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Nombre Completo</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user?.full_name || userHistory.user?.name || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Email</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.email || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Teléfono</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.phone_number || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>CPF</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.cpf_number || userHistory.user?.cpf || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>RNM / Documento</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '500' }}>{userHistory.user?.document_number || 'No disponible'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Estado KYC</p>
                        <p style={{ fontSize: '14px', margin: '2px 0 0 0', fontWeight: '600', color: userHistory.user?.verification_status === 'verified' ? '#16a34a' : '#d97706' }}>
                          {userHistory.user?.verification_status === 'verified' ? '✅ Verificado' : '⏳ Pendiente'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Fecha de Registro</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>
                          {userHistory.user?.created_at ? new Date(userHistory.user.created_at).toLocaleString('es-VE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Caracas' }) : 'No disponible'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Último Login</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0' }}>
                          {userHistory.user?.last_login ? new Date(userHistory.user.last_login).toLocaleString('es-VE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Caracas' }) : 'No disponible'}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Rol</p>
                        <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', textTransform: 'capitalize', fontWeight: '600' }}>{userHistory.user?.role || 'user'}</p>
                      </div>
                      <div>
                        <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Email Verificado</p>
                        <p style={{ fontSize: '14px', margin: '2px 0 0 0', fontWeight: '600', color: userHistory.user?.email_verified ? '#16a34a' : '#dc2626' }}>
                          {userHistory.user?.email_verified ? '✅ Sí' : '❌ No'}
                        </p>
                      </div>
                      {userHistory.user?.gestor_code && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Código Gestor</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user.gestor_code}</p>
                        </div>
                      )}
                      {userHistory.user?.referral_code && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Código Referido</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{userHistory.user.referral_code}</p>
                        </div>
                      )}
                      {userHistory.user?.balance_ris_terceros > 0 && (
                        <div>
                          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0' }}>Balance Terceros</p>
                          <p style={{ fontSize: '14px', color: '#111827', margin: '2px 0 0 0', fontWeight: '600' }}>{fmt(userHistory.user.balance_ris_terceros)} RIS</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Admin Actions: Suspend / Delete */}
                  {user?.role === 'super_admin' && selectedUser.role !== 'super_admin' && (
                    <div style={{ padding: '16px', backgroundColor: '#fef2f2', borderRadius: '14px', marginBottom: '24px' }}>
                      <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#991b1b', margin: '0 0 12px 0' }}>ACCIONES DE ADMINISTRADOR</h4>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button
                          onClick={async () => {
                            const isSuspended = userHistory.user?.status === 'suspended';
                            if (!confirm(isSuspended ? '¿Reactivar este usuario?' : '¿Suspender este usuario? No podrá iniciar sesión.')) return;
                            try {
                              await api.post(`/admin/users/${selectedUser.user_id}/suspend`, { suspend: !isSuspended });
                              toast.success(isSuspended ? 'Usuario reactivado' : 'Usuario suspendido');
                              loadData();
                              closeUserModal();
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error');
                            }
                          }}
                          style={{ padding: '10px 20px', borderRadius: '10px', border: 'none', backgroundColor: userHistory.user?.status === 'suspended' ? '#16a34a' : '#f59e0b', color: 'white', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
                          data-testid="suspend-user-btn"
                        >
                          {userHistory.user?.status === 'suspended' ? 'Reactivar Usuario' : 'Suspender Usuario'}
                        </button>
                        <button
                          onClick={async () => {
                            if (!confirm('¿Eliminar esta cuenta? Se conservará el historial para auditoría y se liberará el correo para que pueda volver a registrarse (salvo que esté baneado).')) return;
                            if (!confirm('¿Confirmas? La cuenta quedará deshabilitada y el correo quedará disponible para un registro nuevo.')) return;
                            try {
                              await api.delete(`/admin/users/${selectedUser.user_id}`);
                              toast.success('Usuario eliminado');
                              loadData();
                              closeUserModal();
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error');
                            }
                          }}
                          style={{ padding: '10px 20px', borderRadius: '10px', border: 'none', backgroundColor: '#dc2626', color: 'white', fontSize: '13px', fontWeight: '600', cursor: 'pointer' }}
                          data-testid="delete-user-btn"
                        >
                          Eliminar Usuario
                        </button>
                      </div>
                    </div>
                  )}

                  {/* KYC Documents Section */}
                  {(userHistory.user?.id_document_image || userHistory.user?.cpf_image || userHistory.user?.selfie_image || userHistory.user?.profile_picture) && (
                    <div style={{ padding: '16px', backgroundColor: '#fef3c7', borderRadius: '14px', marginBottom: '24px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#92400e', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Image style={{ width: '16px', height: '16px' }} />
                          DOCUMENTOS KYC
                        </h4>
                        <button
                          onClick={() => {
                            const docs = [];
                            if (userHistory.user?.profile_picture) docs.push({ name: 'foto_perfil', url: userHistory.user.profile_picture });
                            if (userHistory.user?.id_document_image) docs.push({ name: 'documento_identidad', url: userHistory.user.id_document_image });
                            if (userHistory.user?.cpf_image) docs.push({ name: 'cpf', url: userHistory.user.cpf_image });
                            if (userHistory.user?.selfie_image) docs.push({ name: 'selfie', url: userHistory.user.selfie_image });
                            
                            // `bajarArchivo` mira el valor antes de ponerlo en el
                            // href: estos cuatro campos los llena el usuario que
                            // se verifica, y un `javascript:` acá corría en la
                            // pantalla del que lo está aprobando.
                            const bajados = docs.filter((doc) => bajarArchivo(
                              doc.url,
                              `${userHistory.user?.name || 'usuario'}_${doc.name}.jpg`));
                            if (bajados.length < docs.length) {
                              toast.error(`${docs.length - bajados.length} documento(s) con una dirección que no se puede abrir. Avisale a soporte.`);
                            }
                            toast.success(`${bajados.length} documentos descargados`);
                          }}
                          style={{ padding: '8px 14px', borderRadius: '10px', border: 'none', backgroundColor: '#f59e0b', color: 'white', fontSize: '12px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
                          data-testid="download-all-docs-btn"
                        >
                          <Download style={{ width: '14px', height: '14px' }} />
                          Descargar Todo
                        </button>
                        {/* ESTE BOTON SUBIA LA FICHA A GOOGLE DRIVE.
                            Ahora la descarga desde nuestro servidor. Se fue
                            todo lo de Google: el OAuth, el token permanente
                            que quedaba guardado en la base, y la cuenta
                            personal que oficiaba de destino por omisión.
                            Cada descarga queda asentada en la auditoría. */}
                        <button
                          onClick={async () => {
                            setBajandoFicha(true);
                            try {
                              const res = await api.get(
                                `/admin/users/${selectedUser.user_id}/ficha`,
                                { responseType: 'blob' });
                              const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = `Ficha_${(selectedUser.full_name || selectedUser.name || 'cliente').replace(/ /g, '_')}.pdf`;
                              document.body.appendChild(a);
                              a.click();
                              a.remove();
                              URL.revokeObjectURL(url);
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'No se pudo generar la ficha');
                            } finally {
                              setBajandoFicha(false);
                            }
                          }}
                          disabled={bajandoFicha}
                          style={{ padding: '8px 14px', borderRadius: '10px', border: 'none', backgroundColor: '#4f46e5', color: 'white', fontSize: '12px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', opacity: bajandoFicha ? 0.6 : 1 }}
                          data-testid="descargar-ficha-btn"
                        >
                          <Download style={{ width: '14px', height: '14px' }} />
                          {bajandoFicha ? 'Armando...' : 'Descargar ficha'}
                        </button>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                        {sePuedeAbrir(userHistory.user?.profile_picture) && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={rutaDeArchivo(userHistory.user.profile_picture)} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={rutaDeArchivo(userHistory.user.profile_picture)} 
                                alt="Foto de Perfil" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Perfil</p>
                          </div>
                        )}
                        {sePuedeAbrir(userHistory.user?.id_document_image) && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={rutaDeArchivo(userHistory.user.id_document_image)} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={rutaDeArchivo(userHistory.user.id_document_image)} 
                                alt="Documento" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Documento</p>
                          </div>
                        )}
                        {sePuedeAbrir(userHistory.user?.cpf_image) && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={rutaDeArchivo(userHistory.user.cpf_image)} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={rutaDeArchivo(userHistory.user.cpf_image)} 
                                alt="CPF" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>CPF</p>
                          </div>
                        )}
                        {sePuedeAbrir(userHistory.user?.selfie_image) && (
                          <div style={{ textAlign: 'center' }}>
                            <a href={rutaDeArchivo(userHistory.user.selfie_image)} target="_blank" rel="noopener noreferrer">
                              <img 
                                src={rutaDeArchivo(userHistory.user.selfie_image)} 
                                alt="Selfie" 
                                style={{ width: '100%', height: '80px', objectFit: 'cover', borderRadius: '10px', border: '2px solid #fcd34d', cursor: 'pointer' }}
                              />
                            </a>
                            <p style={{ fontSize: '11px', color: '#92400e', margin: '6px 0 0 0', fontWeight: '600' }}>Selfie</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Transactions List */}
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>
                      HISTORIAL DE TRANSACCIONES ({(userHistory.recharges?.length || 0) + (userHistory.withdrawals?.length || 0)} total)
                    </h4>
                    
                    {(!userHistory.recharges?.length && !userHistory.withdrawals?.length) ? (
                      <div style={{ padding: '32px', backgroundColor: '#f8f9fa', borderRadius: '14px', textAlign: 'center' }}>
                        <p style={{ color: '#6b7280', margin: 0 }}>No hay transacciones</p>
                      </div>
                    ) : (
                      <div style={{ border: '1px solid #e5e7eb', borderRadius: '14px', overflow: 'hidden' }}>
                        {[...(userHistory.withdrawals || []), ...(userHistory.recharges || [])]
                          .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                          .map((tx, index) => (
                            <div 
                              key={tx.transaction_id || tx.recharge_id || index} 
                              style={{ 
                                padding: '14px 16px', 
                                borderBottom: index < (userHistory.withdrawals?.length || 0) + (userHistory.recharges?.length || 0) - 1 ? '1px solid #f3f4f6' : 'none',
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                  <div style={{ 
                                    width: '36px', height: '36px', borderRadius: '10px', 
                                    backgroundColor: tx.type === 'withdrawal' ? '#fef3c7' : '#dcfce7',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                  }}>
                                    {tx.type === 'withdrawal' ? (
                                      <ArrowUpRight style={{ width: '18px', height: '18px', color: '#d97706' }} />
                                    ) : (
                                      <ArrowDownLeft style={{ width: '18px', height: '18px', color: '#16a34a' }} />
                                    )}
                                  </div>
                                  <div>
                                    <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>
                                      {tx.type === 'withdrawal' ? 'Envío/Retiro' : 'Recarga'}
                                      {tx.source && <span style={{ fontSize: '12px', color: '#6b7280', fontWeight: '400' }}> ({tx.source})</span>}
                                    </p>
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      {new Date(tx.created_at).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'America/Caracas' })}
                                    </p>
                                    <p style={{ fontSize: '11px', color: '#9ca3af', margin: '2px 0 0 0', fontFamily: 'monospace' }}>
                                      ID: {tx.transaction_id || tx.recharge_id || 'N/A'}
                                    </p>
                                  </div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                  <p style={{ fontSize: '15px', fontWeight: '700', color: tx.type === 'withdrawal' ? '#d97706' : '#16a34a', margin: 0 }}>
                                    {tx.type === 'withdrawal' ? '-' : '+'}
                                    {tx.type === 'withdrawal' 
                                      ? fmt((tx.amount_input || tx.amount || 0))
                                      : fmt((tx.amount_output || tx.amount_ris || tx.amount || 0))
                                    } RIS
                                  </p>
                                  {tx.type === 'withdrawal' && tx.amount_output > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      = {fmt(tx.amount_output)} VES
                                    </p>
                                  )}
                                  {tx.type !== 'withdrawal' && tx.amount_ves > 0 && (
                                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                                      Pagó: {fmt(tx.amount_ves)} VES
                                    </p>
                                  )}
                                  <span style={{ 
                                    fontSize: '11px', fontWeight: '600', padding: '2px 8px', borderRadius: '9999px',
                                    backgroundColor: tx.status === 'completed' ? '#dcfce7' : tx.status === 'pending' ? '#fef3c7' : '#fee2e2',
                                    color: tx.status === 'completed' ? '#16a34a' : tx.status === 'pending' ? '#d97706' : '#dc2626'
                                  }}>
                                    {tx.status === 'completed' ? 'Completado' : tx.status === 'pending' ? 'Pendiente' : 'Rechazado'}
                                  </span>
                                </div>
                              </div>
                              
                              {/* Voucher/Comprobante */}
                              {sePuedeAbrir(tx.proof_image || tx.voucher_url) && (
                                <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px dashed #e5e7eb' }}>
                                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 6px 0' }}>Comprobante:</p>
                                  <img 
                                    src={rutaDeArchivo(tx.proof_image || tx.voucher_url)} 
                                    alt="Comprobante" 
                                    style={{ 
                                      maxWidth: '200px', 
                                      maxHeight: '150px', 
                                      borderRadius: '8px', 
                                      border: '1px solid #e5e7eb',
                                      cursor: 'pointer'
                                    }}
                                    onClick={() => abrirArchivo(tx.proof_image || tx.voucher_url)}
                                  />
                                </div>
                              )}
                              
                              {/* Beneficiario (para retiros) */}
                              {tx.type === 'withdrawal' && tx.beneficiary_name && (
                                <div style={{ marginTop: '8px', fontSize: '12px', color: '#6b7280' }}>
                                  <span>Beneficiario: </span>
                                  <span style={{ fontWeight: '500', color: '#374151' }}>{tx.beneficiary_name}</span>
                                  {tx.beneficiary_bank && <span> - {tx.beneficiary_bank}</span>}
                                </div>
                              )}
                            </div>
                          ))}
                      </div>
                    )}
                  </div>

                  {/* Beneficiaries */}
                  {userHistory.beneficiaries?.length > 0 && (
                    <div style={{ marginTop: '24px' }}>
                      <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#6b7280', margin: '0 0 12px 0' }}>
                        BENEFICIARIOS ({userHistory.beneficiaries.length})
                      </h4>
                      <div style={{ display: 'grid', gap: '8px' }}>
                        {userHistory.beneficiaries.map((b, i) => (
                          <div key={i} style={{ padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '10px' }}>
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{b.full_name}</p>
                            <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{b.bank} • {b.account_number}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Role Change Modal */}
      {showRoleModal && selectedUserForRole && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', padding: '20px', zIndex: 1000
        }} onClick={() => { setShowRoleModal(false); setSelectedUserForRole(null); }}>
          <div 
            style={{ 
              backgroundColor: '#ffffff', borderRadius: '20px', width: '100%', 
              maxWidth: '400px', overflow: 'hidden', boxShadow: '0 20px 50px rgba(0,0,0,0.2)' 
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '20px', borderBottom: '1px solid #e5e7eb' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ fontSize: '18px', fontWeight: '600', margin: 0 }}>Cambiar Rol de Usuario</h3>
                <button 
                  onClick={() => { setShowRoleModal(false); setSelectedUserForRole(null); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px' }}
                >
                  <X style={{ width: '24px', height: '24px', color: '#6b7280' }} />
                </button>
              </div>
            </div>

            <div style={{ padding: '20px' }}>
              <div style={{ marginBottom: '20px', padding: '16px', backgroundColor: '#f9fafb', borderRadius: '12px' }}>
                <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: '0 0 4px 0' }}>
                  {selectedUserForRole.name}
                </p>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>{selectedUserForRole.email}</p>
                <div style={{ marginTop: '8px' }}>
                  <span style={{ 
                    padding: '4px 10px', borderRadius: '8px', fontSize: '12px', fontWeight: '600',
                    backgroundColor: COLOR_DEL_ROL[selectedUserForRole.role]?.fondo || '#f3f4f6',
                    color: COLOR_DEL_ROL[selectedUserForRole.role]?.letra || '#6b7280'
                  }}>
                    {/* Acá también aplastaba `admin` y `agent` en «Usuario», y
                        acá es peor que en la tabla: esta es LA VENTANA DONDE SE
                        CAMBIA EL ROL. Abrías la de un colaborador y decía «Rol
                        actual: Usuario». Lo encontró la guarda de
                        `test_el_panel_dice_la_verdad.py`, no yo. */}
                    Rol actual: {NOMBRE_DEL_ROL[selectedUserForRole.role] || 'Usuario'}
                  </span>
                </div>
              </div>

              <p style={{ fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '12px' }}>
                Selecciona el nuevo rol:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {/* User Role */}
                <button
                  onClick={() => handleChangeRole('user')}
                  disabled={assigningRole || selectedUserForRole.role === 'user'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'user' ? '#f3f4f6' : '#ffffff',
                    border: '2px solid #e5e7eb', borderRadius: '12px', cursor: selectedUserForRole.role === 'user' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'user' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-user-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Users style={{ width: '22px', height: '22px', color: '#6b7280' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>👤 Usuario Normal</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Acceso básico a la app</p>
                  </div>
                </button>

                {/* Super Admin Role */}
                <button
                  onClick={() => {
                    if (confirm('¿Estás seguro? Este usuario tendrá los mismos poderes que tú.')) {
                      handleChangeRole('super_admin');
                    }
                  }}
                  disabled={assigningRole || selectedUserForRole.role === 'super_admin'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'super_admin' ? '#fef2f2' : '#ffffff',
                    border: '2px solid #dc2626', borderRadius: '12px', cursor: selectedUserForRole.role === 'super_admin' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'super_admin' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-super-admin-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Shield style={{ width: '22px', height: '22px', color: '#dc2626' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#dc2626', margin: 0 }}>Super Administrador</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Acceso total al panel de administración</p>
                  </div>
                </button>
              </div>

              {assigningRole && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: '16px' }}>
                  <RefreshCw style={{ width: '20px', height: '20px', color: '#6366f1', animation: 'spin 1s linear infinite' }} />
                  <span style={{ marginLeft: '8px', fontSize: '14px', color: '#6b7280' }}>Cambiando rol...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal para rechazar recarga VES */}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
