// components/admin/seccionesDelPanel.js — Qué secciones tiene el panel y en
// qué grupos se muestran.
//
// POR QUE ESTA EN UN ARCHIVO APARTE
//
//   Vivía adentro de pages/AdminPanel.jsx, que tiene 2525 líneas y está
//   congelado en ese número por la regla de las 800 (ver
//   backend/tests/archivos_largos.txt): no podía crecer ni una línea. Para
//   separar el panel por servicio hacía falta tocar justo esto, así que se
//   movió tal cual, con sus comentarios. Va separado del menú
//   (MenuDelPanel.jsx) porque el panel también lo lee, y un archivo de
//   componentes que exporta datos pierde la recarga en caliente de Vite.
import {
  Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, Package, Boxes,
  Shield, Activity, UserCog, MessageSquare, CheckCircle, Download,
  AlertCircle, Zap, BookOpen, Star, Wallet, ScrollText, ShieldCheck,
  SlidersHorizontal, AlertTriangle, BarChart3, Receipt, Landmark, Archive,
  Power, LayoutGrid, Send,
} from 'lucide-react';

export const CRM_SUBTABS = [
  { key: 'users', label: 'Usuarios', icon: Users },
  { key: 'kyc', label: 'KYC', icon: Shield },
  { key: 'blacklist', label: 'Lista negra', icon: Shield },
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'support', label: 'Soporte', icon: MessageSquare },
  { key: 'ratings', label: 'Calificaciones', icon: Star },
];

export const TABS = [
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
  // Crear y borrar las cuentas de donde salen los retiros y a donde entran
  // las recargas. Sólo del super administrador, como sus rutas.
  { key: 'bancos', label: 'Bancos', icon: Landmark, superAdminOnly: true },
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
  // Prender y apagar cada servicio. Del super administrador, como la
  // Configuración de la que lee: pausar remesas es una decisión del dueño.
  { key: 'servicios', label: 'Servicios', icon: Power, superAdminOnly: true },
];

// LOS GRUPOS DEL PANEL
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
//
//   Y ENCIMA DE LOS GRUPOS, EL SERVICIO.
//
//   Cada grupo es de un servicio —`servicio`—, y el menú muestra los de uno
//   por vez, elegido con los cuatro botones de arriba: cada servicio tiene su
//   propia gerencia, y el día que remesas se pause su menú entero queda
//   aparte, sin mezclarse con el del banco. Lo que es de todos (clientes,
//   contabilidad, personal) es la «plataforma».
//
//   Lo que cruza servicios se queda en la plataforma aunque mire plata de
//   remesas: el resumen, el uso, el libro mayor, la seguridad financiera y
//   los reportes suman lo de todos, y partirlos sería perder la foto entera.
//   Bancos y cobros sin acreditar sí se fueron a Remesas: son las cuentas de
//   donde salen sus retiros y los pagos de sus recargas.
export const SERVICIOS_DEL_PANEL = [
  { key: 'plataforma', label: 'Plataforma', icon: LayoutGrid },
  { key: 'remesas', label: 'Remesas', icon: Send },
  { key: 'encomiendas', label: 'Encomiendas', icon: Boxes },
  { key: 'banco', label: 'Banco', icon: Landmark },
];

export const GRUPOS = [
  { key: 'g_resumen', servicio: 'plataforma', label: 'Resumen', icon: Activity, hijas: ['overview', 'uso'] },
  { key: 'g_clientes', servicio: 'plataforma', label: 'Clientes', icon: UserCog,
    hijas: ['users', 'kyc', 'blacklist', 'chat', 'support', 'ratings'] },
  { key: 'g_cuentas', servicio: 'plataforma', label: 'Contabilidad', icon: BookOpen,
    hijas: ['ledger', 'seguridad', 'reportes'] },
  { key: 'g_admin', servicio: 'plataforma', label: 'Administración', icon: SlidersHorizontal,
    hijas: ['servicios', 'configuracion', 'respaldo', 'rrhh', 'auditoria', 'errores'] },
  { key: 'g_operacion', servicio: 'remesas', label: 'Operación', icon: CheckCircle,
    hijas: ['ordenes', 'withdrawals', 'recharges', 'diferencias', 'hoja_mp',
            'btc', 'credits', 'rates'] },
  { key: 'g_tesoreria', servicio: 'remesas', label: 'Tesorería', icon: Landmark,
    hijas: ['bancos', 'cobros'] },
  { key: 'g_envios', servicio: 'encomiendas', label: 'Encomiendas', icon: Boxes,
    hijas: ['operacion', 'envios'] },
  { key: 'g_banco', servicio: 'banco', label: 'Gerencia bancaria', icon: Landmark,
    hijas: ['nucleo'] },
];

// De qué servicio es cada sección. Lo usa el menú para saber qué botón
// encender cuando se llega a una sección desde afuera (la campana, `?tab=`).
export const SERVICIO_DE = Object.fromEntries(
  GRUPOS.flatMap((g) => g.hijas.map((h) => [h, g.servicio])));

// La ficha de cada sección, venga de donde venga. `crm` no entra: era el
// contenedor de las subpestañas y ahora ese trabajo lo hace el grupo.
export const POR_CLAVE = Object.fromEntries(
  [...TABS.filter((t) => t.key !== 'crm'), ...CRM_SUBTABS].map((s) => [s.key, s]));
