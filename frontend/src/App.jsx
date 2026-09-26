import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import ConfirmacionHost from './components/flujo/ConfirmacionHost';
import PuertaCripto from './components/PuertaCripto';
import PuertaRecarga from './components/PuertaRecarga';
import PuertaEncomiendas from './components/PuertaEncomiendas';
import PuertaRemesas from './components/PuertaRemesas';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { RateProvider } from './contexts/RateContext';
import { TemaProvider } from './contexts/TemaContext';
import ConTema from './components/tema/ConTema';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import Referidos from './pages/Referidos';
import Dashboard from './pages/Dashboard';
import Send from './pages/Send';
import Recharge from './pages/Recharge';
import RechargeVES from './pages/RechargeVES';
import CreditsDeposit from './pages/CreditsDeposit';
import Profile from './pages/Profile';
import History from './pages/History';
import Verification from './pages/Verification';
import AdminPanel from './pages/AdminPanel';
import Notifications from './pages/Notifications';
import Support from './pages/Support';
import ForceChangePassword from './pages/ForceChangePassword';
import GestorFlowMockup from './pages/GestorFlowMockup';
import BTCLightning from './pages/BTCLightning';
import SendReais from './pages/SendReais';
import SendCrypto from './pages/SendCrypto';
import LegalPage from './pages/LegalPage';
import ActivarPersonal from './pages/ActivarPersonal';
import Landing from './pages/Landing';
import EnviosMis from './pages/EnviosMis';
import EnvioNuevo from './pages/EnvioNuevo';
import EnvioDetalle from './pages/EnvioDetalle';
import RetomarPago from './pages/RetomarPago';
import Seguimiento from './pages/Seguimiento';

// Protected Route Component
function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, mustChangePassword } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)' }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', border: '4px solid #e5e7eb', borderTopColor: '#6366f1', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Force redirect to password change if needed (but not if already there)
  if (mustChangePassword && location.pathname !== '/force-change-password') {
    return <Navigate to="/force-change-password" replace />;
  }

  if (adminOnly && !['agent', 'admin', 'super_admin'].includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

// Public Route (redirects to dashboard if logged in)
function PublicRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)' }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', border: '4px solid #e5e7eb', borderTopColor: '#6366f1', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  return children;
}

// Ruta raiz "/": muestra la Landing publica si NO hay sesion, y el Dashboard si SI
// la hay. A diferencia de ProtectedRoute/PublicRoute (que redirigen), esta ruta
// debe RENDERIZAR contenido distinto segun el estado de auth, no redirigir.
function HomeGate() {
  const { user, loading, mustChangePassword } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)' }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', border: '4px solid #e5e7eb', borderTopColor: '#6366f1', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!user) {
    return <Landing />;
  }

  if (mustChangePassword && location.pathname !== '/force-change-password') {
    return <Navigate to="/force-change-password" replace />;
  }

  return <Dashboard />;
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<PublicRoute><ConTema><Login /></ConTema></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><ConTema><Register /></ConTema></PublicRoute>} />
      <Route path="/legal" element={<ConTema><LegalPage /></ConTema>} />
      {/* Primer acceso del personal: llega por invitación, sin sesión previa. */}
      <Route path="/personal/activar" element={<ConTema><ActivarPersonal /></ConTema>} />
      {/* Publica a proposito: es el link que el usuario le manda a quien espera
          la caja. No muestra ningun dato personal — ver Seguimiento.jsx. */}
      <Route path="/seguimiento/:token" element={<ConTema><Seguimiento /></ConTema>} />
      
      {/* Protected Routes */}
      <Route path="/" element={<HomeGate />} />
      <Route path="/send" element={<ProtectedRoute><PuertaRemesas><ConTema><Send /></ConTema></PuertaRemesas></ProtectedRoute>} />
      <Route path="/send-reais" element={<ProtectedRoute><PuertaRemesas><ConTema><SendReais /></ConTema></PuertaRemesas></ProtectedRoute>} />
      {/* La marca del tema va POR FUERA de la puerta cripto, no adentro: un
          test lee esta línea buscando la puerta pegada a su pantalla, y la
          puerta no dibuja nada propio (nada, o una redirección), así que
          envolverla no cambia cómo se ve. */}
      <Route path="/send-crypto" element={<ProtectedRoute><ConTema><PuertaCripto tipo="envio"><SendCrypto /></PuertaCripto></ConTema></ProtectedRoute>} />
      <Route path="/recharge" element={<ProtectedRoute><PuertaRecarga><ConTema><Recharge /></ConTema></PuertaRecarga></ProtectedRoute>} />
      <Route path="/recharge-ves" element={<ProtectedRoute><PuertaRecarga><ConTema><RechargeVES /></ConTema></PuertaRecarga></ProtectedRoute>} />
      <Route path="/credits/deposit" element={<ProtectedRoute><ConTema><PuertaCripto tipo="deposito"><CreditsDeposit /></PuertaCripto></ConTema></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/referidos" element={<ProtectedRoute><ConTema><Referidos /></ConTema></ProtectedRoute>} />
      <Route path="/history" element={<ProtectedRoute><ConTema><History /></ConTema></ProtectedRoute>} />
      <Route path="/envios" element={<ProtectedRoute><ConTema><EnviosMis /></ConTema></ProtectedRoute>} />
      <Route path="/envios/nuevo" element={<ProtectedRoute><PuertaEncomiendas><ConTema><EnvioNuevo /></ConTema></PuertaEncomiendas></ProtectedRoute>} />
      {/* VA ANTES QUE `/envios/:envioId`, y el orden importa: si fuera al
          revés, `:envioId` se comería «tx_xxx/pagar» y abriría el detalle de
          una encomienda que no existe. */}
      <Route path="/envios/:transactionId/pagar" element={<ProtectedRoute><ConTema><RetomarPago /></ConTema></ProtectedRoute>} />
      <Route path="/envios/:envioId" element={<ProtectedRoute><ConTema><EnvioDetalle /></ConTema></ProtectedRoute>} />
      <Route path="/verification" element={<ProtectedRoute><ConTema><Verification /></ConTema></ProtectedRoute>} />
      <Route path="/notifications" element={<ProtectedRoute><ConTema><Notifications /></ConTema></ProtectedRoute>} />
      <Route path="/support" element={<ProtectedRoute><ConTema><Support /></ConTema></ProtectedRoute>} />
      
      {/* Admin Routes */}
      <Route path="/admin" element={<ProtectedRoute adminOnly><ConTema><AdminPanel /></ConTema></ProtectedRoute>} />
      
      {/* Force Change Password Route */}
      <Route path="/force-change-password" element={<ProtectedRoute><ConTema><ForceChangePassword /></ConTema></ProtectedRoute>} />

      {/* BTC Lightning Route */}
              <Route path="/btc-lightning" element={<ProtectedRoute><ConTema><PuertaCripto tipo="deposito"><BTCLightning /></PuertaCripto></ConTema></ProtectedRoute>} />
      {/* Mockup Route - Temporal */}
      <Route path="/mockup-gestor" element={<ProtectedRoute><GestorFlowMockup /></ProtectedRoute>} />
      
      {/* Catch all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <Router>
      <AuthProvider>
        <TemaProvider>
        <RateProvider>
          <AppRoutes />
          <Toaster 
            position="top-center"
            toastOptions={{
              duration: 3000,
              style: {
                background: '#1e293b',
                color: '#fff',
                borderRadius: '12px',
              },
            }}
          />
          {/* Una sola vez, al lado del Toaster y por el mismo motivo: las
              preguntas de «¿seguro?» se hacen desde cualquier pantalla y no
              tienen por qué subir estado hasta acá. Ver components/flujo/
              confirmar.jsx. */}
          <ConfirmacionHost />
        </RateProvider>
        </TemaProvider>
      </AuthProvider>
    </Router>
  );
}
