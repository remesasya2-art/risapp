import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  Platform,
  Dimensions,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LinearGradient } from 'expo-linear-gradient';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

export default function HomeScreen() {
  const { user, loading: authLoading, login, refreshUser } = useAuth();
  const router = useRouter();
  const [rate, setRate] = useState(78);
  const [risAmount, setRisAmount] = useState('');
  const [vesAmount, setVesAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [checkingPolicies, setCheckingPolicies] = useState(true);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [rates, setRates] = useState({
    ris_to_ves: 92,
    ves_to_ris: 102,
    ris_to_brl: 1
  });
  const [conversionType, setConversionType] = useState<'ris_to_ves' | 'ves_to_ris' | 'ris_to_brl'>('ris_to_ves');

  // Pull to refresh
  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([
      loadRate(),
      loadUnreadNotifications(),
      refreshUser()
    ]);
    setRefreshing(false);
  };

  // MODO PRUEBA: Carga rápida sin verificaciones extras
  useEffect(() => {
    if (user) {
      loadRate();
      // Solo cargar notificaciones después de 2 segundos para no bloquear
      setTimeout(() => loadUnreadNotifications(), 2000);
    }
    setCheckingPolicies(false);
  }, [user]);

  // Auto-actualizar tasas cada 30 segundos
  useEffect(() => {
    if (user) {
      const rateInterval = setInterval(() => {
        loadRate();
        console.log('📊 Tasas actualizadas automáticamente');
      }, 30000); // 30 segundos
      return () => clearInterval(rateInterval);
    }
  }, [user]);

  const loadRate = async () => {
    try {
      console.log('Loading rate from:', `${BACKEND_URL}/api/rate`);
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      console.log('Rate response:', response.data);
      setRates({
        ris_to_ves: response.data.ris_to_ves || 100,
        ves_to_ris: response.data.ves_to_ris || 120,
        ris_to_brl: response.data.ris_to_brl || 1
      });
      setRate(response.data.ris_to_ves || 100);
    } catch (error) {
      console.error('Error loading rate:', error);
      // Intentar de nuevo en 5 segundos si falla
      setTimeout(loadRate, 5000);
    }
  };

  const loadUnreadNotifications = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (!token) return;
      const response = await axios.get(`${BACKEND_URL}/api/notifications/unread-count`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUnreadNotifications(response.data.count);
    } catch (error) {
      // Silenciar error para no bloquear
    }
  };

  // Actualizar notificaciones cada 60 segundos (antes era 30)
  useEffect(() => {
    if (user) {
      const interval = setInterval(loadUnreadNotifications, 60000);
      return () => clearInterval(interval);
    }
  }, [user]);

  // Get current rate based on conversion type
  const getCurrentRate = () => {
    switch (conversionType) {
      case 'ris_to_ves':
        return rates.ris_to_ves;
      case 'ves_to_ris':
        return rates.ves_to_ris;
      case 'ris_to_brl':
        return rates.ris_to_brl;
      default:
        return rates.ris_to_ves;
    }
  };

  // Get labels for conversion type
  const getConversionLabels = () => {
    switch (conversionType) {
      case 'ris_to_ves':
        return { from: 'RIS', to: 'VES', fromLabel: 'Enviar', toLabel: 'Recibe' };
      case 'ves_to_ris':
        return { from: 'VES', to: 'RIS', fromLabel: 'Pagas', toLabel: 'Recibes' };
      case 'ris_to_brl':
        return { from: 'RIS', to: 'BRL', fromLabel: 'Enviar', toLabel: 'Recibe' };
      default:
        return { from: 'RIS', to: 'VES', fromLabel: 'Enviar', toLabel: 'Recibe' };
    }
  };

  const handleRisChange = (value: string) => {
    setRisAmount(value);
    const amount = parseFloat(value) || 0;
    const currentRate = getCurrentRate();
    
    if (conversionType === 'ves_to_ris') {
      // VES to RIS: divide by rate
      setVesAmount((amount / currentRate).toFixed(2));
    } else {
      // RIS to VES/BRL: multiply by rate
      setVesAmount((amount * currentRate).toFixed(2));
    }
  };

  const handleVesChange = (value: string) => {
    setVesAmount(value);
    const amount = parseFloat(value) || 0;
    const currentRate = getCurrentRate();
    
    if (conversionType === 'ves_to_ris') {
      // VES to RIS: multiply by rate
      setRisAmount((amount * currentRate).toFixed(2));
    } else {
      // RIS to VES/BRL: divide by rate
      setRisAmount((amount / currentRate).toFixed(2));
    }
  };

  const handleRecharge = () => {
    if (user?.verification_status !== 'verified') {
      Alert.alert(
        'Verificación Requerida',
        'Debes completar la verificación de tu cuenta antes de recargar',
        [{ text: 'Verificar', onPress: () => router.push('/verification') }]
      );
      return;
    }
    router.push('/recharge');
  };

  const handleRechargeVES = () => {
    if (user?.verification_status !== 'verified') {
      Alert.alert(
        'Verificación Requerida',
        'Debes completar la verificación de tu cuenta antes de recargar',
        [{ text: 'Verificar', onPress: () => router.push('/verification') }]
      );
      return;
    }
    router.push('/recharge-ves');
  };

  const handleSend = () => {
    if (user?.verification_status !== 'verified') {
      Alert.alert(
        'Verificación Requerida',
        'Debes completar la verificación de tu cuenta antes de enviar RIS',
        [{ text: 'Verificar', onPress: () => router.push('/verification') }]
      );
      return;
    }
    router.push('/send');
  };

  if (authLoading || checkingPolicies) {
    return (
      <View style={styles.loadingContainer}>
        <View style={styles.loadingCard}>
          <ActivityIndicator size="large" color="#0f172a" />
          <Text style={styles.loadingText}>
            {checkingPolicies ? 'Verificando...' : 'Cargando...'}
          </Text>
        </View>
      </View>
    );
  }

  // Login Screen - Bank Style
  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loginContainer}>
          {/* Logo Area */}
          <View style={styles.logoArea}>
            <View style={styles.logoContainer}>
              <Ionicons name="wallet" size={40} color="#fff" />
            </View>
            <Text style={styles.brandName}>RIS</Text>
            <Text style={styles.brandTagline}>Transferencias Seguras</Text>
          </View>

          {/* Welcome Card */}
          <View style={styles.welcomeCard}>
            <View style={styles.securityBadge}>
              <Ionicons name="shield-checkmark" size={16} color="#059669" />
              <Text style={styles.securityText}>Conexión Segura</Text>
            </View>
            
            <Text style={styles.welcomeTitle}>Bienvenido</Text>
            <Text style={styles.welcomeSubtitle}>
              Crea tu cuenta o inicia sesión para realizar transferencias de forma segura.
            </Text>

            {/* Register Button - Primary */}
            <TouchableOpacity 
              style={styles.registerButton} 
              onPress={() => router.push('/register')}
            >
              <Ionicons name="person-add" size={20} color="#fff" />
              <Text style={styles.registerButtonText}>Crear Cuenta</Text>
            </TouchableOpacity>

            {/* Login Button - Secondary */}
            <TouchableOpacity 
              style={styles.loginButtonSecondary} 
              onPress={() => router.push('/login')}
            >
              <Ionicons name="log-in" size={20} color="#0f172a" />
              <Text style={styles.loginButtonSecondaryText}>Ya tengo cuenta</Text>
            </TouchableOpacity>

            <View style={styles.securityInfo}>
              <View style={styles.securityItem}>
                <Ionicons name="lock-closed" size={14} color="#64748b" />
                <Text style={styles.securityItemText}>Datos encriptados</Text>
              </View>
              <View style={styles.securityItem}>
                <Ionicons name="finger-print" size={14} color="#64748b" />
                <Text style={styles.securityItemText}>Autenticación segura</Text>
              </View>
            </View>

            {/* Forgot Password Link */}
            <TouchableOpacity 
              style={styles.forgotPasswordLink}
              onPress={() => router.push('/forgot-password')}
            >
              <Text style={styles.forgotPasswordText}>¿Olvidaste tu contraseña?</Text>
            </TouchableOpacity>
          </View>

          {/* Footer */}
          <Text style={styles.footerText}>
            Protegido por cifrado de extremo a extremo
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  // Pending Verification
  if (user.verification_status === 'pending') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.statusContainer}>
          <View style={styles.statusIconContainer}>
            <Ionicons name="hourglass" size={48} color="#f59e0b" />
          </View>
          <Text style={styles.statusTitle}>En Revisión</Text>
          <Text style={styles.statusSubtitle}>
            Tu documentación está siendo verificada por nuestro equipo de seguridad.
          </Text>
          <View style={styles.statusCard}>
            <View style={styles.statusRow}>
              <Ionicons name="document-text" size={20} color="#64748b" />
              <Text style={styles.statusRowText}>Documentos recibidos</Text>
              <Ionicons name="checkmark-circle" size={20} color="#10b981" />
            </View>
            <View style={styles.statusRow}>
              <Ionicons name="search" size={20} color="#64748b" />
              <Text style={styles.statusRowText}>Verificación en proceso</Text>
              <ActivityIndicator size="small" color="#f59e0b" />
            </View>
          </View>
          <Text style={styles.statusNote}>
            Te notificaremos cuando tu cuenta esté verificada
          </Text>
          
          {/* Botón Cerrar Sesión */}
          <TouchableOpacity
            style={styles.logoutBtnPending}
            onPress={async () => {
              await AsyncStorage.removeItem('session_token');
              router.replace('/login');
            }}
          >
            <Ionicons name="log-out-outline" size={20} color="#64748b" />
            <Text style={styles.logoutBtnPendingText}>Cerrar Sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Rejected Verification
  if (user.verification_status === 'rejected') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.statusContainer}>
          <View style={[styles.statusIconContainer, { backgroundColor: '#fef2f2' }]}>
            <Ionicons name="alert-circle" size={48} color="#ef4444" />
          </View>
          <Text style={styles.statusTitle}>Verificación Rechazada</Text>
          <Text style={styles.statusSubtitle}>
            {user.rejection_reason || 'No pudimos verificar tu documentación'}
          </Text>
          <TouchableOpacity
            style={styles.retryButton}
            onPress={() => router.push('/verification')}
          >
            <Ionicons name="refresh" size={20} color="#fff" />
            <Text style={styles.retryButtonText}>Intentar Nuevamente</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Main Dashboard - For verified users or users who haven't submitted KYC yet
  const userBalance = user.balance_ris ?? 0;
  const userName = user.name?.split(' ')[0] || 'Usuario';
  const isVerified = user.verification_status === 'verified';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView 
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl 
            refreshing={refreshing} 
            onRefresh={onRefresh} 
            colors={['#F5A623']}
            tintColor="#F5A623"
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.push('/profile')} style={styles.menuButton}>
            <Ionicons name="menu" size={28} color="#64748b" />
          </TouchableOpacity>
          <View style={styles.headerActions}>
            {isVerified && (
              <View style={styles.verifiedChip}>
                <Ionicons name="shield-checkmark" size={14} color="#059669" />
                <Text style={styles.verifiedChipText}>Verificado</Text>
              </View>
            )}
            <TouchableOpacity 
              style={styles.notificationBtn}
              onPress={() => router.push('/notifications')}
            >
              <Ionicons name="notifications-outline" size={24} color="#0f172a" />
              {unreadNotifications > 0 && (
                <View style={styles.notifBadge}>
                  <Text style={styles.notifBadgeText}>
                    {unreadNotifications > 9 ? '9+' : unreadNotifications}
                  </Text>
                </View>
              )}
            </TouchableOpacity>
          </View>
        </View>

        {/* Greeting - moved below header */}
        <View style={styles.greetingSection}>
          <Text style={styles.greeting}>Hola,</Text>
          <Text style={styles.userName}>{userName}</Text>
        </View>

        {/* Verification Banner - Show if not verified */}
        {!isVerified && user.verification_status !== 'pending' && user.verification_status !== 'rejected' && (
          <TouchableOpacity 
            style={styles.verificationBanner}
            onPress={() => router.push('/verification')}
          >
            <View style={styles.verificationBannerIcon}>
              <Ionicons name="shield-outline" size={24} color="#f59e0b" />
            </View>
            <View style={styles.verificationBannerContent}>
              <Text style={styles.verificationBannerTitle}>Verifica tu cuenta</Text>
              <Text style={styles.verificationBannerText}>Completa la verificación para acceder a todas las funciones</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#f59e0b" />
          </TouchableOpacity>
        )}

        {/* Balance Card */}
        <View style={styles.balanceCard}>
          <View style={styles.balanceHeader}>
            <Text style={styles.balanceLabel}>Balance Disponible</Text>
            <TouchableOpacity onPress={refreshUser} style={styles.refreshBtn}>
              <Ionicons name="refresh" size={18} color="rgba(255,255,255,0.8)" />
            </TouchableOpacity>
          </View>
          <Text style={styles.balanceAmount}>
            <Text style={styles.currencySymbol}>RIS </Text>
            {userBalance.toFixed(2)}
          </Text>
          <View style={styles.balanceFooter}>
            <Ionicons name="trending-up" size={16} color="rgba(255,255,255,0.7)" />
            <Text style={styles.balanceRate}>1 RIS = {rate.toFixed(2)} VES</Text>
          </View>
        </View>

        {/* Password Setup Alert */}
        {!user.password_set && (
          <TouchableOpacity 
            style={styles.securityAlert}
            onPress={() => router.push('/set-password')}
          >
            <View style={styles.alertIconContainer}>
              <Ionicons name="warning" size={24} color="#dc2626" />
            </View>
            <View style={styles.alertContent}>
              <Text style={styles.alertTitle}>Configura tu contraseña</Text>
              <Text style={styles.alertText}>Aumenta la seguridad de tu cuenta</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#dc2626" />
          </TouchableOpacity>
        )}

        {/* Main Action Buttons */}
        <View style={styles.mainActions}>
          <TouchableOpacity style={styles.rechargeBtn} onPress={handleRecharge}>
            <View style={styles.actionBtnContent}>
              <View style={styles.actionBtnIcon}>
                <Ionicons name="qr-code" size={24} color="#fff" />
              </View>
              <View>
                <Text style={styles.actionBtnTitle}>Recargar con PIX</Text>
                <Text style={styles.actionBtnSubtitle}>Instantáneo y seguro</Text>
              </View>
            </View>
            <Ionicons name="arrow-forward-circle" size={28} color="rgba(255,255,255,0.8)" />
          </TouchableOpacity>

          <TouchableOpacity style={styles.rechargeVesBtn} onPress={handleRechargeVES}>
            <View style={styles.actionBtnContent}>
              <View style={[styles.actionBtnIcon, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
                <Ionicons name="cash" size={24} color="#fff" />
              </View>
              <View>
                <Text style={styles.actionBtnTitle}>Recargar con Bolívares</Text>
                <Text style={styles.actionBtnSubtitle}>Pago Móvil o Transferencia</Text>
              </View>
            </View>
            <Ionicons name="arrow-forward-circle" size={28} color="rgba(255,255,255,0.8)" />
          </TouchableOpacity>

          <TouchableOpacity style={styles.sendBtn} onPress={handleSend}>
            <View style={styles.actionBtnContent}>
              <View style={[styles.actionBtnIcon, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
                <Ionicons name="send" size={22} color="#fff" />
              </View>
              <View>
                <Text style={styles.actionBtnTitle}>Enviar a Venezuela</Text>
                <Text style={styles.actionBtnSubtitle}>Transferencia directa</Text>
              </View>
            </View>
            <Ionicons name="arrow-forward-circle" size={28} color="rgba(255,255,255,0.8)" />
          </TouchableOpacity>

          <TouchableOpacity style={styles.historyBtn} onPress={() => router.push('/history')}>
            <View style={styles.actionBtnContent}>
              <View style={[styles.actionBtnIcon, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
                <Ionicons name="time" size={24} color="#fff" />
              </View>
              <View>
                <Text style={styles.actionBtnTitle}>Historial</Text>
                <Text style={styles.actionBtnSubtitle}>Ver mis transacciones</Text>
              </View>
            </View>
            <Ionicons name="arrow-forward-circle" size={28} color="rgba(255,255,255,0.8)" />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: '#f8fafc',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingCard: {
    backgroundColor: '#fff',
    padding: 32,
    borderRadius: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 5,
  },
  loadingText: {
    marginTop: 16,
    fontSize: 15,
    color: '#64748b',
    fontWeight: '500',
  },
  
  // Login Screen
  loginContainer: {
    flex: 1,
    backgroundColor: '#0f172a',
    paddingHorizontal: 24,
  },
  logoArea: {
    alignItems: 'center',
    paddingTop: 60,
    paddingBottom: 40,
  },
  logoContainer: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: '#1e40af',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  brandName: {
    fontSize: 36,
    fontWeight: '800',
    color: '#fff',
    letterSpacing: 2,
  },
  brandTagline: {
    fontSize: 14,
    color: '#94a3b8',
    marginTop: 4,
  },
  welcomeCard: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 28,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 24,
    elevation: 10,
  },
  securityBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#ecfdf5',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    marginBottom: 20,
    gap: 6,
  },
  securityText: {
    fontSize: 12,
    color: '#059669',
    fontWeight: '600',
  },
  welcomeTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 8,
  },
  welcomeSubtitle: {
    fontSize: 15,
    color: '#64748b',
    lineHeight: 22,
    marginBottom: 28,
  },
  googleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    paddingVertical: 16,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#e2e8f0',
    gap: 12,
  },
  googleIconContainer: {
    width: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  googleButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#0f172a',
  },
  registerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
    marginBottom: 12,
    shadowColor: '#F5A623',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  registerButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#fff',
  },
  loginButtonSecondary: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
    borderWidth: 1.5,
    borderColor: '#e2e8f0',
  },
  loginButtonSecondaryText: {
    fontSize: 17,
    fontWeight: '600',
    color: '#0f172a',
  },
  securityInfo: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 24,
    gap: 24,
  },
  securityItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  securityItemText: {
    fontSize: 12,
    color: '#64748b',
  },
  forgotPasswordLink: {
    alignItems: 'center',
    marginTop: 20,
    paddingVertical: 8,
  },
  forgotPasswordText: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
  footerText: {
    fontSize: 12,
    color: '#475569',
    textAlign: 'center',
    marginTop: 32,
  },

  // Status Screens
  statusContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  statusIconContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  statusTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 12,
    textAlign: 'center',
  },
  statusSubtitle: {
    fontSize: 15,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 22,
    paddingHorizontal: 20,
  },
  statusCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    marginTop: 32,
    gap: 16,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  statusRowText: {
    flex: 1,
    fontSize: 14,
    color: '#475569',
  },
  statusNote: {
    fontSize: 13,
    color: '#94a3b8',
    marginTop: 24,
    textAlign: 'center',
  },
  logoutBtnPending: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    marginTop: 32,
    gap: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  logoutBtnPendingText: {
    color: '#64748b',
    fontSize: 14,
    fontWeight: '500',
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    paddingHorizontal: 28,
    paddingVertical: 14,
    borderRadius: 12,
    marginTop: 32,
    gap: 8,
  },
  retryButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },

  // Verification Banner
  verificationBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fffbeb',
    borderRadius: 14,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#fef3c7',
  },
  verificationBannerIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  verificationBannerContent: {
    flex: 1,
  },
  verificationBannerTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#92400e',
  },
  verificationBannerText: {
    fontSize: 13,
    color: '#b45309',
    marginTop: 2,
  },

  // Main Dashboard
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 32,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  menuButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  greetingSection: {
    marginBottom: 20,
    marginTop: 8,
  },
  greeting: {
    fontSize: 14,
    color: '#64748b',
  },
  userName: {
    fontSize: 26,
    fontWeight: '700',
    color: '#0f172a',
    marginTop: 2,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  verifiedChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ecfdf5',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 20,
    gap: 4,
  },
  verifiedChipText: {
    fontSize: 12,
    color: '#059669',
    fontWeight: '600',
  },
  notificationBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  notifBadge: {
    position: 'absolute',
    top: -2,
    right: -2,
    backgroundColor: '#ef4444',
    width: 20,
    height: 20,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#f8fafc',
  },
  notifBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: 'bold',
  },

  // Balance Card
  balanceCard: {
    backgroundColor: '#0f172a',
    borderRadius: 20,
    padding: 24,
    marginBottom: 24,
  },
  balanceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  balanceLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.7)',
  },
  refreshBtn: {
    padding: 4,
  },
  balanceAmount: {
    fontSize: 40,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 16,
  },
  currencySymbol: {
    fontSize: 24,
    fontWeight: '500',
    color: 'rgba(255,255,255,0.7)',
  },
  balanceFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  balanceRate: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.7)',
  },

  // Quick Actions
  quickActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  quickActionBtn: {
    alignItems: 'center',
    width: (SCREEN_WIDTH - 60) / 4,
  },
  quickActionIcon: {
    width: 56,
    height: 56,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  quickActionText: {
    fontSize: 12,
    color: '#475569',
    fontWeight: '500',
  },

  // Calculator
  calculatorCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  calculatorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
  },
  calculatorTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0f172a',
  },
  
  // Conversion Type Selector
  conversionSelector: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 14,
  },
  conversionOption: {
    flex: 1,
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  conversionOptionActive: {
    backgroundColor: '#fffbeb',
    borderColor: '#F5A623',
  },
  conversionOptionText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748b',
  },
  conversionOptionTextActive: {
    color: '#92400e',
  },
  conversionRate: {
    fontSize: 13,
    fontWeight: '700',
    color: '#94a3b8',
    marginTop: 2,
  },
  conversionRateActive: {
    color: '#F5A623',
  },
  
  // Compact Calculator Inputs
  calculatorInputsCompact: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  calcInputGroupCompact: {
    flex: 1,
  },
  calcInputLabelCompact: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '500',
    marginBottom: 4,
    textAlign: 'center',
  },
  calcInputCompact: {
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    fontSize: 16,
    fontWeight: '600',
    color: '#0f172a',
    textAlign: 'center',
  },
  exchangeArrowCompact: {
    paddingHorizontal: 4,
    paddingTop: 16,
  },
  
  // Legacy calculator styles (keep for compatibility)
  calculatorInputs: {
    gap: 12,
  },
  calcInputGroup: {
    gap: 8,
  },
  calcInputLabel: {
    fontSize: 13,
    color: '#64748b',
    fontWeight: '500',
  },
  calcInputContainer: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  calcInput: {
    padding: 14,
    fontSize: 18,
    fontWeight: '600',
    color: '#0f172a',
  },
  exchangeArrow: {
    alignItems: 'center',
    paddingVertical: 4,
  },
  rateInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  rateInfoText: {
    fontSize: 12,
    color: '#64748b',
  },

  // Security Alert
  securityAlert: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef2f2',
    borderRadius: 14,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#fecaca',
  },
  alertIconContainer: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fee2e2',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  alertContent: {
    flex: 1,
  },
  alertTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#991b1b',
  },
  alertText: {
    fontSize: 13,
    color: '#b91c1c',
    marginTop: 2,
  },

  // Main Action Buttons
  mainActions: {
    gap: 12,
  },
  rechargeBtn: {
    backgroundColor: '#059669',
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  rechargeVesBtn: {
    backgroundColor: '#F5A623',
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sendBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  historyBtn: {
    backgroundColor: '#7c3aed',
    borderRadius: 16,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  actionBtnContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  actionBtnIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  actionBtnTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  actionBtnSubtitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 2,
  },
});
