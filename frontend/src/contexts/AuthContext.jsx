import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../utils/api';

const AuthContext = createContext(null);
const INACTIVITY_TIMEOUT = 10 * 60 * 1000; // 10 minutos

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const timerRef = useRef(null);

  const doLogout = useCallback(() => {
    localStorage.removeItem('session_token');
    localStorage.removeItem('last_activity');
    setUser(null);
    setMustChangePassword(false);
  }, []);

  const resetTimer = useCallback(() => {
    if (!localStorage.getItem('session_token')) return;
    localStorage.setItem('last_activity', Date.now().toString());
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doLogout().then(() => { window.location.href = '/login'; });
    }, INACTIVITY_TIMEOUT);
  }, [doLogout]);

  // Detectar actividad del usuario
  useEffect(() => {
    if (!user) return;
    const events = ['mousedown', 'keydown', 'touchstart', 'scroll'];
    events.forEach(e => window.addEventListener(e, resetTimer));
    resetTimer();
    return () => {
      events.forEach(e => window.removeEventListener(e, resetTimer));
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [user, resetTimer]);

  // Al cargar, verificar si ya pasaron 10 min desde última actividad
  useEffect(() => {
    const lastActivity = localStorage.getItem('last_activity');
    if (lastActivity && Date.now() - parseInt(lastActivity) > INACTIVITY_TIMEOUT) {
      doLogout();
    }
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('session_token');
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await api.get('/auth/me');
      setUser(response.data);
      setMustChangePassword(response.data.must_change_password || false);
    } catch (error) {
      localStorage.removeItem('session_token');
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    const response = await api.post('/auth/login-password', { email, password });
    const data = response.data;

    // 2FA required (enrollment or verify) — caller will handle the flow
    if (data.two_factor_required || data.two_factor_enrollment_required) {
      return data;
    }

    localStorage.setItem('session_token', data.session_token);
    localStorage.setItem('last_activity', Date.now().toString());
    setUser(data.user);
    setMustChangePassword(data.must_change_password || false);
    return data;
  };

  const completeTwoFactorLogin = (sessionToken, userData) => {
    localStorage.setItem('session_token', sessionToken);
    localStorage.setItem('last_activity', Date.now().toString());
    setUser(userData);
    setMustChangePassword(userData?.must_change_password || false);
  };

  const register = async (data) => {
    const response = await api.post('/auth/register', data);
    return response.data;
  };

  const logout = () => {
    doLogout();
  };

  const refreshUser = async () => {
    try {
      const response = await api.get('/auth/me');
      setUser(response.data);
      setMustChangePassword(response.data.must_change_password || false);
    } catch (error) {
      console.error('Error refreshing user:', error);
    }
  };

  const clearMustChangePassword = () => {
    setMustChangePassword(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser, mustChangePassword, clearMustChangePassword, completeTwoFactorLogin }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
