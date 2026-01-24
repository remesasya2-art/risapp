import React, { createContext, useState, useEffect, useContext } from 'react';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import axios from 'axios';
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
        ? `${BACKEND_URL}/`
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
        await axios.post(`${BACKEND_URL}/api/auth/logout`, {}, {
          headers: { Authorization: `Bearer ${token}` }
        });
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      await AsyncStorage.removeItem('session_token');
      setUser(null);
    }
  };

  const refreshUser = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (token) {
        const response = await axios.get(`${BACKEND_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` }
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