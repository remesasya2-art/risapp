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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import { useRouter } from 'expo-router';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function HomeScreen() {
  const { user, loading: authLoading, login, refreshUser } = useAuth();
  const router = useRouter();
  const [rate, setRate] = useState(78);
  const [risAmount, setRisAmount] = useState('');
  const [vesAmount, setVesAmount] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) {
      loadRate();
      checkVerificationStatus();
    }
  }, [user]);

  const checkVerificationStatus = () => {
    if (user && user.verification_status === 'pending') {
      // User has submitted but waiting approval - don't redirect
      return;
    }
    if (user && user.verification_status === 'rejected') {
      // User was rejected - allow retry
      return;
    }
    if (user && !user.verification_status) {
      // User needs to submit verification - show alert but don't auto-redirect
      // They can access it from profile if needed
      return;
    }
  };

  const loadRate = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setRate(response.data.ris_to_ves);
    } catch (error) {
      console.error('Error loading rate:', error);
    }
  };

  const handleRisChange = (value: string) => {
    setRisAmount(value);
    const ris = parseFloat(value) || 0;
    setVesAmount((ris * rate).toFixed(2));
  };

  const handleVesChange = (value: string) => {
    setVesAmount(value);
    const ves = parseFloat(value) || 0;
    setRisAmount((ves / rate).toFixed(2));
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
    Alert.alert('Info', 'Funcionalidad de recarga próximamente');
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

  if (authLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="wallet" size={80} color="#2563eb" />
          <Text style={styles.welcomeTitle}>Bienvenido a RIS</Text>
          <Text style={styles.welcomeSubtitle}>
            La forma más fácil de recargar y enviar dinero
          </Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Ionicons name="logo-google" size={20} color="#fff" />
            <Text style={styles.loginButtonText}>Iniciar sesión con Google</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Show verification status
  if (user.verification_status === 'pending') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="time-outline" size={80} color="#f59e0b" />
          <Text style={styles.welcomeTitle}>Verificación Pendiente</Text>
          <Text style={styles.welcomeSubtitle}>
            Tu documentación está siendo revisada.{'\n'}
            Te notificaremos cuando esté aprobada.
          </Text>
          <View style={styles.statusCard}>
            <Text style={styles.statusText}>Estado: En revisión ⏳</Text>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  if (user.verification_status === 'rejected') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="close-circle-outline" size={80} color="#ef4444" />
          <Text style={styles.welcomeTitle}>Verificación Rechazada</Text>
          <Text style={styles.welcomeSubtitle}>
            {user.rejection_reason || 'Tu documentación fue rechazada'}
          </Text>
          <TouchableOpacity
            style={styles.loginButton}
            onPress={() => router.push('/verification')}
          >
            <Text style={styles.loginButtonText}>Intentar Nuevamente</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Verification Badge */}
        {user.verification_status === 'verified' && (
          <View style={styles.verifiedBadge}>
            <Ionicons name="shield-checkmark" size={20} color="#10b981" />
            <Text style={styles.verifiedText}>Cuenta Verificada ✓</Text>
          </View>
        )}

        {/* Balance Card */}
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Balance Disponible</Text>
          <Text style={styles.balanceAmount}>{user.balance_ris.toFixed(2)} RIS</Text>
          <TouchableOpacity
            style={styles.refreshButton}
            onPress={refreshUser}
          >
            <Ionicons name="refresh" size={20} color="#2563eb" />
          </TouchableOpacity>
        </View>

        {/* Calculator Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Calculadora de Cambio</Text>
          <Text style={styles.rateText}>Tasa actual: 1 RIS = {rate.toFixed(2)} VES</Text>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>RIS</Text>
            <TextInput
              style={styles.input}
              value={risAmount}
              onChangeText={handleRisChange}
              keyboardType="numeric"
              placeholder="0.00"
            />
          </View>

          <View style={styles.exchangeIcon}>
            <Ionicons name="swap-vertical" size={24} color="#6b7280" />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>VES (Bolívares)</Text>
            <TextInput
              style={styles.input}
              value={vesAmount}
              onChangeText={handleVesChange}
              keyboardType="numeric"
              placeholder="0.00"
            />
          </View>
        </View>

        {/* Action Buttons */}
        <View style={styles.actionsContainer}>
          <TouchableOpacity
            style={[styles.actionButton, styles.primaryButton]}
            onPress={handleRecharge}
          >
            <Ionicons name="add-circle" size={24} color="#fff" />
            <Text style={styles.actionButtonText}>Recargar REAIS</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionButton, styles.secondaryButton]}
            onPress={handleSend}
          >
            <Ionicons name="send" size={24} color="#fff" />
            <Text style={styles.actionButtonText}>Enviar RIS</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  scrollContent: {
    padding: 16,
  },
  welcomeTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2937',
    marginTop: 16,
    marginBottom: 8,
    textAlign: 'center',
  },
  welcomeSubtitle: {
    fontSize: 16,
    color: '#6b7280',
    textAlign: 'center',
    marginBottom: 32,
  },
  loginButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2563eb',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  verifiedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#d1fae5',
    padding: 12,
    borderRadius: 8,
    marginBottom: 16,
    gap: 8,
  },
  verifiedText: {
    color: '#065f46',
    fontSize: 14,
    fontWeight: '600',
  },
  statusCard: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    marginTop: 24,
  },
  statusText: {
    fontSize: 16,
    color: '#6b7280',
    textAlign: 'center',
  },
  balanceCard: {
    backgroundColor: '#2563eb',
    borderRadius: 16,
    padding: 24,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  balanceLabel: {
    color: '#dbeafe',
    fontSize: 14,
    marginBottom: 8,
  },
  balanceAmount: {
    color: '#fff',
    fontSize: 36,
    fontWeight: 'bold',
  },
  refreshButton: {
    position: 'absolute',
    top: 16,
    right: 16,
    backgroundColor: '#fff',
    borderRadius: 20,
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  rateText: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 16,
  },
  inputContainer: {
    marginBottom: 8,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
  exchangeIcon: {
    alignItems: 'center',
    marginVertical: 8,
  },
  actionsContainer: {
    gap: 12,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  primaryButton: {
    backgroundColor: '#10b981',
  },
  secondaryButton: {
    backgroundColor: '#f59e0b',
  },
  actionButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});