import React, { createContext, useState, useEffect, useContext } from 'react';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import axios from 'axios';
import { useRouter, useSegments } from 'expo-router';
import { 
  registerForPushNotificationsAsync, 
  sendPushTokenToServer,
  addNotificationReceivedListener,
  addNotificationResponseReceivedListener
} from '../services/notifications';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface User {
  user_id: string;
  email: string;
  name: string;
  picture?: string;
  balance_ris: number;
  verification_status?: string;
  rejection_reason?: string;
  role?: string;  // 'user', 'admin', 'super_admin'
  permissions?: string[];
  password_set?: boolean;  // true if user has set a password
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
  refreshUser: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    checkExistingSession();
  }, []);

  // Setup push notifications when user is logged in (mobile only)
  useEffect(() => {
    if (user && Platform.OS !== 'web') {
      console.log('🔔 Usuario logueado, configurando push notifications...');
      setupPushNotifications();
    }
  }, [user]);

  // MODO PRUEBA: Heartbeat reducido a cada 2 minutos
  useEffect(() => {
    if (!user) return;
    
    let isActive = true;
    let timeoutId: NodeJS.Timeout | null = null;
    let intervalId: NodeJS.Timeout | null = null;
    
    const sendHeartbeat = () => {
      if (!isActive) return;
      
      AsyncStorage.getItem('session_token').then(token => {
        if (token && isActive) {
          axios.post(`${BACKEND_URL}/api/auth/heartbeat`, {}, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: 5000 // 5 segundos máximo
          }).catch(() => {}); // Ignorar errores
        }
      }).catch(() => {});
    };
    
    // Enviar heartbeat después de 5 segundos
    timeoutId = setTimeout(sendHeartbeat, 5000);
    
    // Heartbeat cada 2 minutos
    intervalId = setInterval(sendHeartbeat, 120000);
    
    return () => {
      isActive = false;
      if (timeoutId) clearTimeout(timeoutId);
      if (intervalId) clearInterval(intervalId);
    };
  }, [user]);

  const setupPushNotifications = async () => {
    try {
      console.log('🔔 Registrando token de notificaciones push...');
      const token = await registerForPushNotificationsAsync();
      
      if (token) {
        console.log('🔔 Token obtenido, enviando al servidor...');
        const success = await sendPushTokenToServer(token);
        if (success) {
          console.log('✅ Token de notificaciones registrado exitosamente');
        } else {
          console.log('⚠️ No se pudo registrar el token en el servidor');
        }
      } else {
        console.log('⚠️ No se pudo obtener token de notificaciones');
      }

      // Setup notification listeners
      const notificationListener = addNotificationReceivedListener((notification) => {
        console.log('🔔 Notificación recibida:', notification);
      });

      const responseListener = addNotificationResponseReceivedListener((response) => {
        console.log('🔔 Respuesta a notificación:', response);
        // Handle notification tap - could navigate to specific screen
        const data = response.notification.request.content.data;
        if (data?.type === 'withdrawal_completed') {
          // Could navigate to transaction history
          console.log('👆 Usuario tocó notificación de retiro completado');
        }
      });

      return () => {
        notificationListener.remove();
        responseListener.remove();
      };
    } catch (error) {
      console.error('❌ Error configurando push notifications:', error);
    }
  };

  const checkExistingSession = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (token) {
        // Verify token and get user
        const response = await axios.get(`${BACKEND_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setUser(response.data);
      }
    } catch (error) {
      console.error('Session check error:', error);
      await AsyncStorage.removeItem('session_token');
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    try {
      setLoading(true);
      
      const redirectUrl = Platform.OS === 'web'
        ? (typeof window !== 'undefined' ? window.location.origin + '/' : `${BACKEND_URL}/`)
        : Linking.createURL('/');
      
      const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
      
      if (Platform.OS === 'web') {
        // Web: Direct redirect
        window.location.href = authUrl;
      } else {
        // Mobile: Use WebBrowser
        const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
        
        if (result.type === 'success' && result.url) {
          await handleAuthRedirect(result.url);
        }
      }
    } catch (error) {
      console.error('Login error:', error);
      setLoading(false);
    }
  };

  const handleAuthRedirect = async (url: string) => {
    try {
      // Parse session_id from URL (hash or query)
      let sessionId = null;
      
      // Check hash
      if (url.includes('#session_id=')) {
        sessionId = url.split('#session_id=')[1].split('&')[0];
      }
      // Check query
      else if (url.includes('?session_id=')) {
        sessionId = url.split('?session_id=')[1].split('&')[0];
      }
      
      if (!sessionId) {
        throw new Error('No session_id found in redirect URL');
      }
      
      // Exchange session_id for user data
      const response = await axios.post(
        `${BACKEND_URL}/api/auth/session`,
        {},
        {
          headers: { 'X-Session-ID': sessionId }
        }
      );
      
      const { session_token, ...userData } = response.data;
      
      // Store token
      await AsyncStorage.setItem('session_token', session_token);
      
      // Get full user data
      const userResponse = await axios.get(`${BACKEND_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${session_token}` }
      });
      
      setUser(userResponse.data);
    } catch (error) {
      console.error('Auth redirect error:', error);
      throw error;
    }
  };

  const logout = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (token) {
        // No esperar la respuesta del servidor para evitar bloqueos
        axios.post(`${BACKEND_URL}/api/auth/logout`, {}, {
          headers: { Authorization: `Bearer ${token}` }
        }).catch(() => {}); // Ignorar errores silenciosamente
      }
    } catch (error) {
      console.error('Logout error:', error);
    }
    
    // Limpiar estado inmediatamente sin await
    AsyncStorage.removeItem('session_token').catch(() => {});
    setUser(null);
    
    // Redirigir a login en web
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.replace('/login');
    }
  };

  const refreshUser = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (token) {
        // Add timestamp to prevent caching
        const response = await axios.get(`${BACKEND_URL}/api/auth/me?_t=${Date.now()}`, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        });
        setUser(response.data);
      }
    } catch (error) {
      console.error('Refresh user error:', error);
    }
  };

  // Handle deep link for web
  useEffect(() => {
    if (Platform.OS === 'web') {
      const handleWebAuth = async () => {
        const hash = window.location.hash;
        if (hash.includes('session_id=')) {
          await handleAuthRedirect(window.location.href);
          // Clean URL
          window.history.replaceState({}, document.title, window.location.pathname);
        }
      };
      
      handleWebAuth();
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};