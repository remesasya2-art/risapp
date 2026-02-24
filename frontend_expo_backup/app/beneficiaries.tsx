import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import { VENEZUELA_BANKS } from '../constants/venezuelaBanks';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Beneficiary {
  beneficiary_id: string;
  full_name: string;
  account_number: string;
  id_document: string;
  phone_number: string;
  bank: string;
  bank_code: string;
}

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function BeneficiariesScreen() {
  const router = useRouter();
  const { user, login } = useAuth();
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      loadBeneficiaries();
    } else {
      setLoading(false);
    }
  }, [user]);

  const loadBeneficiaries = async () => {
    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/beneficiaries`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setBeneficiaries(response.data);
    } catch (error) {
      console.error('Error loading beneficiaries:', error);
    } finally {
      setLoading(false);
    }
  };

  const getBankName = (bankCode: string) => {
    const bank = VENEZUELA_BANKS.find(b => b.code === bankCode);
    return bank ? bank.name : bankCode;
  };

  const handleDelete = (beneficiary: Beneficiary) => {
    const doDelete = async () => {
      setDeleting(beneficiary.beneficiary_id);
      try {
        const token = await AsyncStorage.getItem('session_token');
        await axios.delete(`${BACKEND_URL}/api/beneficiaries/${beneficiary.beneficiary_id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setBeneficiaries(prev => prev.filter(b => b.beneficiary_id !== beneficiary.beneficiary_id));
        showAlert('Eliminado', 'Beneficiario eliminado correctamente. El historial de transacciones se mantiene.');
      } catch (error: any) {
        showAlert('Error', error.response?.data?.detail || 'No se pudo eliminar');
      } finally {
        setDeleting(null);
      }
    };

    if (Platform.OS === 'web') {
      if (confirm(`¿Eliminar a ${beneficiary.full_name}?\n\nNota: El historial de transacciones con este beneficiario NO se eliminará.`)) {
        doDelete();
      }
    } else {
      Alert.alert(
        'Confirmar Eliminación',
        `¿Eliminar a ${beneficiary.full_name}?\n\nNota: El historial de transacciones con este beneficiario NO se eliminará.`,
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Eliminar', style: 'destructive', onPress: doDelete },
        ]
      );
    }
  };

  const handleSendTo = (beneficiary: Beneficiary) => {
    router.push({
      pathname: '/send',
      params: { beneficiaryId: beneficiary.beneficiary_id },
    });
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Mis Beneficiarios</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.centerContainer}>
          <Ionicons name="lock-closed" size={60} color="#6b7280" />
          <Text style={styles.emptyText}>Inicia sesión para ver tus beneficiarios</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#1f2937" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Mis Beneficiarios</Text>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#2563eb" />
        </View>
      ) : beneficiaries.length === 0 ? (
        <View style={styles.centerContainer}>
          <Ionicons name="people-outline" size={60} color="#6b7280" />
          <Text style={styles.emptyText}>No tienes beneficiarios guardados</Text>
          <Text style={styles.emptySubtext}>Al hacer un envío, podrás guardar el beneficiario para futuros usos</Text>
          <TouchableOpacity style={styles.addButton} onPress={() => router.push('/send')}>
            <Ionicons name="add" size={24} color="#fff" />
            <Text style={styles.addButtonText}>Nuevo Envío</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <Text style={styles.infoText}>
            Selecciona un beneficiario para enviar dinero o elimínalo de tu lista.
            El historial de transacciones se mantiene.
          </Text>
          
          {beneficiaries.map((ben) => (
            <View key={ben.beneficiary_id} style={styles.beneficiaryCard}>
              <View style={styles.beneficiaryHeader}>
                <View style={styles.beneficiaryIcon}>
                  <Ionicons name="person" size={24} color="#2563eb" />
                </View>
                <View style={styles.beneficiaryInfo}>
                  <Text style={styles.beneficiaryName}>{ben.full_name}</Text>
                  <Text style={styles.beneficiaryBank}>
                    {ben.bank_code ? `${ben.bank_code} - ${getBankName(ben.bank_code)}` : ben.bank}
                  </Text>
                </View>
              </View>
              
              <View style={styles.beneficiaryDetails}>
                <View style={styles.detailRow}>
                  <Ionicons name="card-outline" size={16} color="#6b7280" />
                  <Text style={styles.detailText}>Cuenta: {ben.account_number}</Text>
                </View>
                <View style={styles.detailRow}>
                  <Ionicons name="id-card-outline" size={16} color="#6b7280" />
                  <Text style={styles.detailText}>Cédula: {ben.id_document}</Text>
                </View>
                <View style={styles.detailRow}>
                  <Ionicons name="call-outline" size={16} color="#6b7280" />
                  <Text style={styles.detailText}>Tel: {ben.phone_number}</Text>
                </View>
              </View>

              <View style={styles.beneficiaryActions}>
                <TouchableOpacity
                  style={styles.sendToButton}
                  onPress={() => handleSendTo(ben)}
                >
                  <Ionicons name="send" size={18} color="#fff" />
                  <Text style={styles.sendToButtonText}>Enviar</Text>
                </TouchableOpacity>
                
                <TouchableOpacity
                  style={styles.deleteButton}
                  onPress={() => handleDelete(ben)}
                  disabled={deleting === ben.beneficiary_id}
                >
                  {deleting === ben.beneficiary_id ? (
                    <ActivityIndicator size="small" color="#ef4444" />
                  ) : (
                    <Ionicons name="trash-outline" size={20} color="#ef4444" />
                  )}
                </TouchableOpacity>
              </View>
            </View>
          ))}

          <TouchableOpacity style={styles.newSendButton} onPress={() => router.push('/send')}>
            <Ionicons name="add-circle-outline" size={24} color="#2563eb" />
            <Text style={styles.newSendButtonText}>Nuevo Envío</Text>
          </TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  emptyText: {
    fontSize: 16,
    color: '#6b7280',
    marginTop: 16,
    textAlign: 'center',
  },
  emptySubtext: {
    fontSize: 14,
    color: '#9ca3af',
    marginTop: 8,
    textAlign: 'center',
    paddingHorizontal: 40,
  },
  loginButton: {
    backgroundColor: '#2563eb',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    marginTop: 20,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2563eb',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
    marginTop: 20,
    gap: 8,
  },
  addButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  scrollContent: {
    padding: 16,
  },
  infoText: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 16,
    lineHeight: 18,
  },
  beneficiaryCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  beneficiaryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  beneficiaryIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  beneficiaryInfo: {
    flex: 1,
  },
  beneficiaryName: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 2,
  },
  beneficiaryBank: {
    fontSize: 14,
    color: '#2563eb',
  },
  beneficiaryDetails: {
    backgroundColor: '#f9fafb',
    padding: 12,
    borderRadius: 8,
    marginBottom: 12,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  detailText: {
    fontSize: 14,
    color: '#4b5563',
  },
  beneficiaryActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sendToButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f59e0b',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
    flex: 1,
    marginRight: 12,
    justifyContent: 'center',
  },
  sendToButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  deleteButton: {
    width: 44,
    height: 44,
    borderRadius: 8,
    backgroundColor: '#fef2f2',
    justifyContent: 'center',
    alignItems: 'center',
  },
  newSendButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#2563eb',
    borderStyle: 'dashed',
    gap: 8,
    marginTop: 8,
  },
  newSendButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#2563eb',
  },
});
