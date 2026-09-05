import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, Users, ArrowUpRight, ArrowDownLeft, TrendingUp, Search, Package, Boxes, 
  RefreshCw, Shield, Activity, Eye, X, ChevronRight, UserCog, Gift, Briefcase, KeyRound, Trash2, MessageSquare, CheckCircle, Clock, Phone, Mail, Send, Download, Image, Upload, AlertCircle, Zap, BookOpen, Star, Wallet, ScrollText, ShieldCheck
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { confirmar } from '../components/flujo/confirmar.js';
import OrdenesPorProcesar from '../components/admin/OrdenesPorProcesar';
import DiferenciasPago from '../components/admin/DiferenciasPago';
import Reportes from '../components/admin/Reportes';
import ReconciliacionLedger from '../components/admin/ReconciliacionLedger';
import SeguridadFinanciera from '../components/admin/SeguridadFinanciera';
import LibroMayor from '../components/admin/LibroMayor';
import RecursosHumanos from '../components/admin/RecursosHumanos';
import LibroAuditoria from '../components/admin/LibroAuditoria';
import RecargasVES from '../components/admin/RecargasVES';
import Retiros from '../components/admin/Retiros';
import ListaNegra from '../components/admin/ListaNegra';
import { fmt } from '../utils/format';
import MesaDeAyuda from '../components/admin/MesaDeAyuda';
import { WipeButton } from '../components/common/WipeButton';
import { RestoreButton } from '../components/common/RestoreButton';
import ErrorBoundary from '../components/common/ErrorBoundary';
import { AutoRateCard } from '../components/common/AutoRateCard';
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

const CRM_KEYS = ['partners', 'users', 'kyc', 'blacklist', 'chat', 'support'];

const CRM_SUBTABS = [
  { key: 'users', label: 'Usuarios', icon: Users },
  { key: 'kyc', label: 'KYC', icon: Shield },
  { key: 'blacklist', label: 'Lista negra', icon: Shield },
  { key: 'partners', label: 'Socios', icon: Briefcase },
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'support', label: 'Soporte', icon: MessageSquare },
  { key: 'ratings', label: 'Calificaciones', icon: Star },
];

const TABS = [
  { key: 'overview', label: 'Resumen', icon: Activity },
  { key: 'ordenes', label: 'Órdenes por procesar', icon: CheckCircle },
  { key: 'diferencias', label: 'Diferencias de pago', icon: AlertCircle, superAdminOnly: true },
  { key: 'reportes', label: 'Reportes', icon: Download },
  // Antes del Libro mayor a propósito: acá están las cuatro respuestas, allá
  // el detalle contable de cada una. Sólo del super administrador, igual que
  // las rutas que consulta (`get_super_admin` en el backend).
  { key: 'seguridad', label: 'Seguridad financiera', icon: ShieldCheck, superAdminOnly: true },
  { key: 'ledger', label: 'Libro mayor', icon: BookOpen },
  { key: 'withdrawals', label: 'Retiros', icon: ArrowUpRight },
  { key: 'recharges', label: 'Recargas VES', icon: ArrowDownLeft },
  { key: 'crm', label: 'CRM', icon: UserCog },
  { key: 'rates', label: 'Tasas', icon: TrendingUp },
  { key: 'btc', label: 'BTC Lightning', icon: Zap },
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
];

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
  const [stats, setStats] = useState({ users: 0, pending_withdrawals: 0, pending_recharges: 0, pending_kyc: 0 });
  // El banco que el operador elige a mano para una recarga que nacio sin el.
  const [users, setUsers] = useState([]);

  const [bannedEmails, setBannedEmails] = useState(() => new Set());
  const [newRate, setNewRate] = useState('');
  const [newRateVesToRis, setNewRateVesToRis] = useState('');
  const [newRateBrlToRis, setNewRateBrlToRis] = useState('');
  const [selectedUser, setSelectedUser] = useState(null);
  const [userHistory, setUserHistory] = useState(null);
  const [loadingUser, setLoadingUser] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [selectedUserForRole, setSelectedUserForRole] = useState(null);
  const [assigningRole, setAssigningRole] = useState(false);
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [pendingToClean, setPendingToClean] = useState([]);
  const [cleaningUp, setCleaningUp] = useState(false);
  const [driveConnected, setDriveConnected] = useState(false);
  const [uploadingKyc, setUploadingKyc] = useState(false);
  // Partner/Gestor management states
  const [partners, setPartners] = useState([]);
  const [gestors, setGestors] = useState([]);
  const [partnerSearchQuery, setPartnerSearchQuery] = useState('');
  const [partnerTab, setPartnerTab] = useState('socios'); // 'socios' or 'gestores'
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
  const [selectedChat, setSelectedChat] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
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
    api.get('/oauth/drive/status').then(res => setDriveConnected(res.data.connected)).catch(() => {});
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      switch (activeTab) {
        case 'overview':
          const [wRes, rRes, uRes, kRes] = await Promise.all([
            api.get('/admin/withdrawals/pending').catch(() => ({ data: [] })),
            api.get('/admin/recharges/ves/pending').catch(() => ({ data: { recharges: [] } })),
            api.get('/admin/users').catch(() => ({ data: { users: [] } })),
            api.get('/admin/kyc/list', { params: { status: 'pending', limit: 1 } }).catch(() => ({ data: { counts: { pending: 0 } } }))
          ]);
          setStats({
            pending_withdrawals: (wRes.data || []).length,
            pending_recharges: (rRes.data?.recharges || []).length,
            users: (uRes.data?.users || []).length,
            pending_kyc: (kRes.data?.counts?.pending ?? 0)
          });
          break;
        case 'partners':
          // Load both socios and gestores
          const [partnersRes, gestorsRes] = await Promise.all([
            api.get('/admin/partners').catch(() => ({ data: [] })),
            api.get('/admin/gestors').catch(() => ({ data: [] }))
          ]);
          setPartners(partnersRes.data || []);
          setGestors(gestorsRes.data || []);
          break;
        case 'users':
          const usersRes = await api.get('/admin/users');
          setUsers(usersRes.data?.users || []);
          const blRes = await api.get('/admin/blacklist').catch(() => ({ data: { items: [] } }));
          setBannedEmails(new Set((blRes.data?.items || []).filter((it) => it.type === 'email').map((it) => String(it.value || '').toLowerCase().trim())));
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

  // Refresh overview stats after KYC actions (the KycPanel manages its own state)
  const refreshKycStats = async () => {
    try {
      const res = await api.get('/admin/kyc/list', { params: { status: 'pending', limit: 1 } });
      setStats((prev) => ({ ...prev, pending_kyc: res.data?.counts?.pending ?? 0 }));
    } catch { /* silent */ }
  };

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
      detalle: `El correo ${u.email} queda bloqueado para registrarse de nuevo.`,
      accion: 'Agregar a la lista negra',
      tono: 'peligro',
    })) return;
    try {
      await api.post('/admin/blacklist', { type: 'email', value: u.email, reason: 'Agregado desde Usuarios' });
      toast.success('Usuario agregado a la lista negra');
      setBannedEmails((prev) => new Set(prev).add(String(u.email || '').toLowerCase().trim()));
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

  // Filtrar usuarios por búsqueda
  const filteredUsers = users.filter(u => 
    !bannedEmails.has(String(u.email || '').toLowerCase().trim()) &&
    (userSearchQuery === '' || 
    u.name?.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
    u.email?.toLowerCase().includes(userSearchQuery.toLowerCase()))
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

  const deleteSingleWithdrawal = async (txId) => {
    if (!confirm('¿Eliminar esta transacción? El saldo será reembolsado al usuario.')) return;
    setCleaningUp(true);
    try {
      await api.delete(`/admin/withdrawals/delete/${txId}`);
      toast.success('Transacción eliminada y saldo reembolsado');
      setPendingToClean(prev => prev.filter(tx => tx.transaction_id !== txId));
      loadData();
    } catch (error) {
      toast.error('Error al eliminar');
    } finally {
      setCleaningUp(false);
    }
  };

  const pageStyle = { minHeight: '100vh', background: '#f8f9fc', fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' };
  const cardStyle = { backgroundColor: '#ffffff', borderRadius: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', border: '1px solid #e5e7eb' };
  const btnPrimary = { backgroundColor: '#6366f1', color: 'white', borderRadius: '12px', padding: '10px 20px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '14px' };
  const btnSuccess = { backgroundColor: '#16a34a', color: 'white', borderRadius: '10px', padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '13px' };
  const btnDanger = { backgroundColor: '#dc2626', color: 'white', borderRadius: '10px', padding: '8px 16px', border: 'none', cursor: 'pointer', fontWeight: '500', fontSize: '13px' };
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
              <button onClick={() => navigate('/')} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="back-button">
                <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
              </button>
              <div>
                <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Panel de Control</h1>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{user?.role === 'super_admin' ? 'Super Admin' : user?.role === 'agent' ? 'Agente' : 'Admin'}</p>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <RestoreButton userRole={user?.role} onSuccess={loadData} size="sm" />
              <button onClick={loadData} style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} data-testid="refresh-button">
                <RefreshCw style={{ width: '20px', height: '20px', color: '#374151', animation: loading ? 'spin 1s linear infinite' : 'none' }} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '8px 24px' }}>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', rowGap: '8px' }}>
            {(isAgent ? TABS.filter(t => t.key === 'crm' || t.key === 'operacion') : TABS.filter(t => !t.superAdminOnly || user?.role === 'super_admin')).map((tab) => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key === 'crm' ? (isAgent ? 'chat' : 'users') : tab.key)}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px', borderRadius: '12px', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap', fontSize: '14px', fontWeight: '500',
                  backgroundColor: (activeTab === tab.key || (tab.key === 'crm' && CRM_KEYS.includes(activeTab))) ? '#6366f1' : 'transparent', color: (activeTab === tab.key || (tab.key === 'crm' && CRM_KEYS.includes(activeTab))) ? '#ffffff' : '#6b7280' }}
                data-testid={`tab-${tab.key}`}
              >
                <tab.icon style={{ width: '18px', height: '18px' }} /> {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <main style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px' }}>
        {CRM_KEYS.includes(activeTab) && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px', borderBottom: '1px solid #eef0f4', paddingBottom: '14px' }}>
            {(isAgent ? CRM_SUBTABS.filter(st => ['chat', 'support', 'users', 'kyc', 'blacklist'].includes(st.key)) : CRM_SUBTABS.filter(st => st.key !== 'ratings' || user?.role === 'super_admin')).map((st) => (
              <button key={st.key} onClick={() => setActiveTab(st.key)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 14px', borderRadius: '10px', border: activeTab === st.key ? '1px solid #6366f1' : '1px solid #e5e7eb', backgroundColor: activeTab === st.key ? '#eef2ff' : '#fff', color: activeTab === st.key ? '#4F46E5' : '#6b7280', fontWeight: 600, fontSize: '14px', cursor: 'pointer' }}
              >
                <st.icon style={{ width: '16px', height: '16px' }} /> {st.label}
              </button>
            ))}
          </div>
        )}
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
        {activeTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              {[
                { icon: ArrowUpRight, value: stats.pending_withdrawals, label: 'Retiros pendientes', bg: '#fef3c7', iconColor: '#d97706' },
                { icon: ArrowDownLeft, value: stats.pending_recharges, label: 'Recargas pendientes', bg: '#dcfce7', iconColor: '#16a34a' },
                { icon: Users, value: stats.users, label: 'Usuarios totales', bg: '#dbeafe', iconColor: '#2563eb' },
                { icon: Shield, value: stats.pending_kyc, label: 'KYC pendientes', bg: '#f3e8ff', iconColor: '#9333ea' },
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
                  {rates?.auto_rate_enabled && rates?.is_off_hours && (
                    <p style={{ fontSize: '12px', color: '#ca8a04', margin: '4px 0 0 0', fontWeight: '600' }}>
                      Modo automático activo — Base: {fmt(rates?.base_ris_to_ves)}
                    </p>
                  )}
                  <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>
                    Última actualización: {rates?.updated_at
                      ? new Date(rates.updated_at).toLocaleString('es-VE', { timeZone: 'America/Caracas', dateStyle: 'short', timeStyle: 'medium' })
                      : '—'}
                  </p>
                </div>
                <button onClick={() => setActiveTab('rates')} style={btnPrimary}>Modificar</button>
              </div>
            </div>

            <AutoRateCard
              baseRisToVes={rates?.base_ris_to_ves ?? rates?.ris_to_ves}
              baseVesToRis={rates?.base_ves_to_ris_rate ?? rates?.ves_to_ris_rate}
              onChange={loadData}
              userRole={user?.role}
            />

            <BcvRatesCard />
          </div>
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
        {activeTab === 'partners' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Sub-tabs for Socios / Gestores */}
            <div style={{ ...cardStyle, padding: '16px' }}>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                <button 
                  onClick={() => setPartnerTab('socios')}
                  style={{ 
                    flex: 1, padding: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                    backgroundColor: partnerTab === 'socios' ? '#7c3aed' : '#f3f4f6',
                    color: partnerTab === 'socios' ? '#ffffff' : '#374151',
                    fontWeight: '600', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                  }}
                  data-testid="partner-tab-socios"
                >
                  <Gift style={{ width: '18px', height: '18px' }} />
                  Socios Referidos ({partners.length})
                </button>
                <button 
                  onClick={() => setPartnerTab('gestores')}
                  style={{ 
                    flex: 1, padding: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                    backgroundColor: partnerTab === 'gestores' ? '#059669' : '#f3f4f6',
                    color: partnerTab === 'gestores' ? '#ffffff' : '#374151',
                    fontWeight: '600', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                  }}
                  data-testid="partner-tab-gestores"
                >
                  <Briefcase style={{ width: '18px', height: '18px' }} />
                  Socios Gestores ({gestors.length})
                </button>
              </div>
              
              {/* Search */}
              <div style={{ position: 'relative' }}>
                <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '18px', height: '18px', color: '#9ca3af' }} />
                <input 
                  type="text" 
                  placeholder={`Buscar ${partnerTab === 'socios' ? 'socio' : 'gestor'}...`}
                  value={partnerSearchQuery} 
                  onChange={(e) => setPartnerSearchQuery(e.target.value)}
                  style={{ width: '100%', padding: '12px 12px 12px 40px', borderRadius: '12px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none', boxSizing: 'border-box' }} 
                />
              </div>
            </div>

            {/* Socios List */}
            {partnerTab === 'socios' && (
              <div style={{ ...cardStyle, overflow: 'hidden' }}>
                {loading ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
                ) : partners.filter(p => !partnerSearchQuery || p.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || p.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).length === 0 ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}>
                    <Gift style={{ width: '48px', height: '48px', color: '#d1d5db', margin: '0 auto 16px' }} />
                    <p style={{ color: '#6b7280', margin: 0 }}>No hay socios registrados</p>
                    <p style={{ color: '#9ca3af', fontSize: '13px', margin: '8px 0 0 0' }}>Asigna el rol Socio desde la pestaña de usuarios</p>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead style={{ backgroundColor: '#faf5ff' }}>
                        <tr>
                          {['Socio', 'Código', 'Referidos', 'Total Ganancias', 'Este Mes', 'Estado'].map(h => (
                            <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#7c3aed', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {partners.filter(p => !partnerSearchQuery || p.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || p.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).map((p) => (
                          <tr key={p.user_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`partner-${p.user_id}`}>
                            <td style={{ padding: '16px' }}>
                              <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{p.name}</p>
                              <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{p.email}</p>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: '600', color: '#7c3aed', backgroundColor: '#f5f3ff', padding: '4px 10px', borderRadius: '6px' }}>
                                {p.referral_code || 'N/A'}
                              </span>
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {p.referrals_count || 0}
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {fmt((p.total_earnings || 0))} RIS
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#16a34a' }}>
                              +{fmt((p.month_earnings || 0))} RIS
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: '#dcfce7', color: '#16a34a' }}>
                                Activo
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Gestores List */}
            {partnerTab === 'gestores' && (
              <div style={{ ...cardStyle, overflow: 'hidden' }}>
                {loading ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}><RefreshCw style={{ width: '32px', height: '32px', color: '#6366f1', animation: 'spin 1s linear infinite' }} /></div>
                ) : gestors.filter(g => !partnerSearchQuery || g.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || g.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).length === 0 ? (
                  <div style={{ padding: '48px', textAlign: 'center' }}>
                    <Briefcase style={{ width: '48px', height: '48px', color: '#d1d5db', margin: '0 auto 16px' }} />
                    <p style={{ color: '#6b7280', margin: 0 }}>No hay gestores registrados</p>
                    <p style={{ color: '#9ca3af', fontSize: '13px', margin: '8px 0 0 0' }}>Asigna el rol Socio Gestor desde la pestaña de usuarios</p>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead style={{ backgroundColor: '#ecfdf5' }}>
                        <tr>
                          {['Gestor', 'Código', 'Transacciones', 'Volumen Total', 'Saldo Terceros', 'Estado'].map(h => (
                            <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: '#059669', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {gestors.filter(g => !partnerSearchQuery || g.name?.toLowerCase().includes(partnerSearchQuery.toLowerCase()) || g.email?.toLowerCase().includes(partnerSearchQuery.toLowerCase())).map((g) => (
                          <tr key={g.user_id} style={{ borderBottom: '1px solid #f3f4f6' }} data-testid={`gestor-${g.user_id}`}>
                            <td style={{ padding: '16px' }}>
                              <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{g.name}</p>
                              <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{g.email}</p>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: '600', color: '#059669', backgroundColor: '#ecfdf5', padding: '4px 10px', borderRadius: '6px' }}>
                                {g.gestor_code || 'N/A'}
                              </span>
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {g.total_transactions || 0}
                            </td>
                            <td style={{ padding: '16px', fontSize: '14px', fontWeight: '600', color: '#111827' }}>
                              {fmt((g.total_volume || 0))} RIS
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ fontSize: '14px', fontWeight: '700', color: '#059669' }}>
                                {fmt((g.balance_ris_terceros || 0))} RIS
                              </span>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <span style={{ padding: '4px 12px', borderRadius: '9999px', fontSize: '12px', fontWeight: '600', backgroundColor: '#dcfce7', color: '#16a34a' }}>
                                Activo
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
                            <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{u.name}</p>
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
                              backgroundColor: u.role === 'socio' ? '#ede9fe' : u.role === 'socio_gestor' ? '#d1fae5' : '#f3f4f6',
                              color: u.role === 'socio' ? '#7c3aed' : u.role === 'socio_gestor' ? '#059669' : '#6b7280'
                            }}>
                              {u.role === 'socio' ? '🎁 Socio' : u.role === 'socio_gestor' ? '🏪 Gestor' : '👤 Usuario'}
                            </span>
                          </td>
                          <td style={{ padding: '16px', display: 'flex', gap: '8px' }}>
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
                      <p style={{ color: '#374151', fontSize: '13px', margin: '0 0 2px' }}>CI: {orden.beneficiario_data?.cedula || 'N/A'}</p>
                      <p style={{ color: '#374151', fontSize: '13px', margin: 0 }}>
                        {orden.beneficiario_data?.payment_type === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}
                      </p>
                    </div>
                    <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '12px', padding: '14px' }}>
                      <p style={{ fontSize: '11px', fontWeight: '700', color: '#1e40af', margin: '0 0 6px', letterSpacing: '0.05em' }}>DATOS PAGO</p>
                      {orden.beneficiario_data?.payment_type === 'pago_movil' ? (
                        <>
                          <p style={{ fontWeight: '600', color: '#111827', margin: '0 0 2px', fontSize: '14px' }}>📱 {orden.beneficiario_data?.phone || 'N/A'}</p>
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
          <OperacionPanel />
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
                        <button
                          onClick={async () => {
                            if (!driveConnected) {
                              try {
                                const res = await api.get('/oauth/drive/connect');
                                window.location.href = res.data.authorization_url;
                              } catch (e) {
                                toast.error('Error al conectar Drive');
                              }
                              return;
                            }
                            setUploadingKyc(true);
                            try {
                              const res = await api.post(`/oauth/drive/upload-kyc/${selectedUser.user_id}`);
                              toast.success(res.data.message);
                            } catch (e) {
                              toast.error(e.response?.data?.detail || 'Error al subir a Drive');
                            } finally {
                              setUploadingKyc(false);
                            }
                          }}
                          disabled={uploadingKyc}
                          style={{ padding: '8px 14px', borderRadius: '10px', border: 'none', backgroundColor: driveConnected ? '#16a34a' : '#4285f4', color: 'white', fontSize: '12px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', opacity: uploadingKyc ? 0.6 : 1 }}
                          data-testid="upload-drive-btn"
                        >
                          <Upload style={{ width: '14px', height: '14px' }} />
                          {uploadingKyc ? 'Subiendo...' : driveConnected ? 'Subir a Drive' : 'Conectar Drive'}
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
                    backgroundColor: selectedUserForRole.role === 'socio' ? '#ede9fe' : selectedUserForRole.role === 'socio_gestor' ? '#d1fae5' : '#f3f4f6',
                    color: selectedUserForRole.role === 'socio' ? '#7c3aed' : selectedUserForRole.role === 'socio_gestor' ? '#059669' : '#6b7280'
                  }}>
                    Rol actual: {selectedUserForRole.role === 'socio' ? 'Socio' : selectedUserForRole.role === 'socio_gestor' ? 'Gestor' : 'Usuario'}
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

                {/* Socio Role */}
                <button
                  onClick={() => handleChangeRole('socio')}
                  disabled={assigningRole || selectedUserForRole.role === 'socio'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'socio' ? '#ede9fe' : '#ffffff',
                    border: '2px solid #8b5cf6', borderRadius: '12px', cursor: selectedUserForRole.role === 'socio' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'socio' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-socio-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Gift style={{ width: '22px', height: '22px', color: '#7c3aed' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>🎁 Socio (Referidor)</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Puede referir usuarios y ganar comisiones</p>
                  </div>
                </button>

                {/* Socio Gestor Role */}
                <button
                  onClick={() => handleChangeRole('socio_gestor')}
                  disabled={assigningRole || selectedUserForRole.role === 'socio_gestor'}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                    backgroundColor: selectedUserForRole.role === 'socio_gestor' ? '#d1fae5' : '#ffffff',
                    border: '2px solid #10b981', borderRadius: '12px', cursor: selectedUserForRole.role === 'socio_gestor' ? 'not-allowed' : 'pointer',
                    opacity: selectedUserForRole.role === 'socio_gestor' ? 0.5 : 1, textAlign: 'left'
                  }}
                  data-testid="role-gestor-btn"
                >
                  <div style={{ width: '44px', height: '44px', borderRadius: '12px', backgroundColor: '#d1fae5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Briefcase style={{ width: '22px', height: '22px', color: '#059669' }} />
                  </div>
                  <div>
                    <p style={{ fontSize: '15px', fontWeight: '600', color: '#111827', margin: 0 }}>Socio Gestor</p>
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>Procesa envíos de terceros</p>
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

      {/* Cleanup Modal */}
      {showCleanupModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px', zIndex: 50 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', width: '100%', maxWidth: '550px', maxHeight: '90vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', backgroundColor: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Trash2 style={{ width: '24px', height: '24px', color: '#dc2626' }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>Limpieza de Retiros</h3>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>Transacciones pendientes detectadas</p>
                </div>
              </div>
              <button onClick={() => setShowCleanupModal(false)} style={{ width: '36px', height: '36px', borderRadius: '10px', backgroundColor: '#f3f4f6', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {pendingToClean.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                  <Activity style={{ width: '32px', height: '32px', color: '#16a34a' }} />
                </div>
                <h4 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: '0 0 8px 0' }}>¡Todo limpio!</h4>
                <p style={{ color: '#6b7280', margin: 0 }}>No hay transacciones pendientes para limpiar</p>
              </div>
            ) : (
              <>
                <div style={{ backgroundColor: '#fef3c7', borderRadius: '12px', padding: '12px', marginBottom: '16px' }}>
                  <p style={{ color: '#92400e', fontSize: '13px', margin: 0 }}>
                    ⚠️ Se encontraron {pendingToClean.length} transacción(es) pendiente(s). Eliminar devolverá el saldo al usuario.
                  </p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px', maxHeight: '300px', overflowY: 'auto' }}>
                  {pendingToClean.map((tx) => (
                    <div key={tx.transaction_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
                      <div>
                        <p style={{ fontSize: '14px', fontWeight: '600', color: '#111827', margin: 0 }}>{tx.beneficiary || 'Sin nombre'}</p>
                        <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>
                          R{tx.display_id} • {fmt(tx.amount_ves)} VES
                        </p>
                      </div>
                      <button 
                        onClick={() => deleteSingleWithdrawal(tx.transaction_id)}
                        disabled={cleaningUp}
                        style={{ ...btnDanger, opacity: cleaningUp ? 0.5 : 1, padding: '8px 12px' }}
                      >
                        <Trash2 style={{ width: '14px', height: '14px' }} />
                      </button>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setShowCleanupModal(false)} style={{ ...btnSecondary, flex: 1 }}>
                    Cerrar
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Modal para rechazar recarga VES */}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
