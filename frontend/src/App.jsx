import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { RateProvider } from './contexts/RateContext';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Send from './pages/Send';
import Recharge from './pages/Recharge';
import RechargeVES from './pages/RechargeVES';
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

  if (adminOnly && !['admin', 'super_admin'].includes(user.role)) {
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

function AppRoutes() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
      
      {/* Protected Routes */}
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/send" element={<ProtectedRoute><Send /></ProtectedRoute>} />
      <Route path="/recharge" element={<ProtectedRoute><Recharge /></ProtectedRoute>} />
      <Route path="/recharge-ves" element={<ProtectedRoute><RechargeVES /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
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
              <Route path="/btc-lightning" element={<ProtectedRoute><BTCLightning /></ProtectedRoute>ProtectedRoute>} /></ProtectedRoute>
      {/* Mockup Route - Temporal */}
      <Route path="/mockup-gestor" element={<GestorFlowMockup />} />
      
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
        </RateProvider>
      </AuthProvider>
    </Router>
  );
}
