import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import ConfirmacionHost from './components/flujo/ConfirmacionHost';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { RateProvider } from './contexts/RateContext';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
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
import PartnerDashboard from './pages/PartnerDashboard';
import GestorDashboard from './pages/GestorDashboard';
import ForceChangePassword from './pages/ForceChangePassword';
import GestorFlowMockup from './pages/GestorFlowMockup';
import DriveCallback from './pages/DriveCallback';
import BTCLightning from './pages/BTCLightning';
import SendReais from './pages/SendReais';
import SendCrypto from './pages/SendCrypto';
import LegalPage from './pages/LegalPage';
import ActivarPersonal from './pages/ActivarPersonal';
import Landing from './pages/Landing';
import EnviosMis from './pages/EnviosMis';
import EnvioNuevo from './pages/EnvioNuevo';
import EnvioDetalle from './pages/EnvioDetalle';
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
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
      <Route path="/legal" element={<LegalPage />} />
      {/* Primer acceso del personal: llega por invitación, sin sesión previa. */}
      <Route path="/personal/activar" element={<ActivarPersonal />} />
      {/* Publica a proposito: es el link que el usuario le manda a quien espera
          la caja. No muestra ningun dato personal — ver Seguimiento.jsx. */}
      <Route path="/seguimiento/:token" element={<Seguimiento />} />
      
      {/* Protected Routes */}
      <Route path="/" element={<HomeGate />} />
      <Route path="/send" element={<ProtectedRoute><Send /></ProtectedRoute>} />
      <Route path="/send-reais" element={<ProtectedRoute><SendReais /></ProtectedRoute>} />
      <Route path="/send-crypto" element={<ProtectedRoute><SendCrypto /></ProtectedRoute>} />
      <Route path="/recharge" element={<ProtectedRoute><Recharge /></ProtectedRoute>} />
      <Route path="/recharge-ves" element={<ProtectedRoute><RechargeVES /></ProtectedRoute>} />
      <Route path="/credits/deposit" element={<ProtectedRoute><CreditsDeposit /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
      <Route path="/envios" element={<ProtectedRoute><EnviosMis /></ProtectedRoute>} />
      <Route path="/envios/nuevo" element={<ProtectedRoute><EnvioNuevo /></ProtectedRoute>} />
      <Route path="/envios/:envioId" element={<ProtectedRoute><EnvioDetalle /></ProtectedRoute>} />
      <Route path="/verification" element={<ProtectedRoute><Verification /></ProtectedRoute>} />
      <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
      <Route path="/support" element={<ProtectedRoute><Support /></ProtectedRoute>} />
      <Route path="/partner" element={<ProtectedRoute><PartnerDashboard /></ProtectedRoute>} />
      <Route path="/gestor" element={<ProtectedRoute><GestorDashboard /></ProtectedRoute>} />
      
      {/* Admin Routes */}
      <Route path="/admin" element={<ProtectedRoute adminOnly><AdminPanel /></ProtectedRoute>} />
      <Route path="/admin/drive-callback" element={<ProtectedRoute adminOnly><DriveCallback /></ProtectedRoute>} />
      
      {/* Force Change Password Route */}
      <Route path="/force-change-password" element={<ProtectedRoute><ForceChangePassword /></ProtectedRoute>} />

      {/* BTC Lightning Route */}
              <Route path="/btc-lightning" element={<ProtectedRoute><BTCLightning /></ProtectedRoute>} />
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
      </AuthProvider>
    </Router>
  );
}
