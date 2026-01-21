import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Beneficiary {
  beneficiary_id: string;
  full_name: string;
  account_number: string;
  id_document: string;
  phone_number: string;
  bank: string;
}

export default function SendRISScreen() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [rate, setRate] = useState(78);
  const [amount, setAmount] = useState('');
  const [vesAmount, setVesAmount] = useState('');
  
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState<Beneficiary | null>(null);
  const [showBeneficiaries, setShowBeneficiaries] = useState(false);
  
  const [beneficiaryData, setBeneficiaryData] = useState({
    full_name: '',
    account_number: '',
    id_document: '',
    phone_number: '',
    bank: '',
  });
  const [saveBeneficiary, setSaveBeneficiary] = useState(false);

  useEffect(() => {
    loadRate();
    loadBeneficiaries();
  }, []);

  const loadRate = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setRate(response.data.ris_to_ves);
    } catch (error) {
      console.error('Error loading rate:', error);
    }
  };

  const loadBeneficiaries = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/beneficiaries`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setBeneficiaries(response.data);
    } catch (error) {
      console.error('Error loading beneficiaries:', error);
    }
  };

  const handleAmountChange = (value: string) => {
    setAmount(value);
    const ris = parseFloat(value) || 0;
    setVesAmount((ris * rate).toFixed(2));
  };

  const selectBeneficiary = (beneficiary: Beneficiary) => {
    setSelectedBeneficiary(beneficiary);
    setBeneficiaryData({
      full_name: beneficiary.full_name,
      account_number: beneficiary.account_number,
      id_document: beneficiary.id_document,
      phone_number: beneficiary.phone_number,
      bank: beneficiary.bank,
    });
    setShowBeneficiaries(false);
  };

  const handleSend = async () => {
    // Validations
    const risAmount = parseFloat(amount);
    
    if (!risAmount || risAmount <= 0) {
      Alert.alert('Error', 'Ingresa un monto válido');
      return;
    }

    if (!user || user.balance_ris < risAmount) {
      Alert.alert('Error', `Saldo insuficiente. Balance actual: ${user?.balance_ris.toFixed(2)} RIS`);
      return;
    }

    if (!beneficiaryData.full_name.trim()) {
      Alert.alert('Error', 'Ingresa el nombre completo del beneficiario');
      return;
    }

    if (!beneficiaryData.account_number.trim()) {
      Alert.alert('Error', 'Ingresa el número de cuenta');
      return;
    }

    if (!beneficiaryData.id_document.trim()) {
      Alert.alert('Error', 'Ingresa la cédula del beneficiario');
      return;
    }

    if (!beneficiaryData.phone_number.trim()) {
      Alert.alert('Error', 'Ingresa el teléfono del beneficiario');
      return;
    }

    if (!beneficiaryData.bank.trim()) {
      Alert.alert('Error', 'Ingresa el banco del beneficiario');
      return;
    }

    // Confirm
    Alert.alert(
      'Confirmar Envío',
      `¿Enviar ${risAmount.toFixed(2)} RIS (${parseFloat(vesAmount).toFixed(2)} VES) a ${beneficiaryData.full_name}?\n\nEl monto será descontado inmediatamente y el equipo procesará la transferencia.`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar',
          onPress: async () => {
            try {
              setLoading(true);
              const token = await AsyncStorage.getItem('session_token');

              // Save beneficiary if requested
              if (saveBeneficiary && !selectedBeneficiary) {
                await axios.post(
                  `${BACKEND_URL}/api/beneficiaries`,
                  beneficiaryData,
                  { headers: { Authorization: `Bearer ${token}` } }
                );
              }

              // Create withdrawal
              await axios.post(
                `${BACKEND_URL}/api/withdrawal/create`,
                {
                  amount_ris: risAmount,
                  beneficiary_data: beneficiaryData,
                },
                { headers: { Authorization: `Bearer ${token}` } }
              );

              await refreshUser();

              Alert.alert(
                'Envío Exitoso',
                `Se han descontado ${risAmount.toFixed(2)} RIS de tu balance.\n\nEl equipo ha sido notificado y procesará tu transferencia pronto.`,
                [{ text: 'OK', onPress: () => router.back() }]
              );
            } catch (error: any) {
              console.error('Send error:', error);
              Alert.alert('Error', error.response?.data?.detail || 'No se pudo procesar el envío');
            } finally {
              setLoading(false);
            }
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Enviar RIS</Text>
          <View style={{ width: 24 }} />
        </View>

        {/* Balance Card */}
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Tu Balance</Text>
          <Text style={styles.balanceAmount}>{user?.balance_ris.toFixed(2) || '0.00'} RIS</Text>
        </View>

        {/* Amount Input */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Monto a Enviar</Text>
          <Text style={styles.rateText}>Tasa: 1 RIS = {rate.toFixed(2)} VES</Text>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Cantidad en RIS</Text>
            <TextInput
              style={styles.input}
              value={amount}
              onChangeText={handleAmountChange}
              keyboardType="numeric"
              placeholder="0.00"
            />
          </View>

          <View style={styles.conversionRow}>
            <Ionicons name="arrow-down" size={20} color="#6b7280" />
            <Text style={styles.conversionText}>
              Recibirá: <Text style={styles.conversionAmount}>{vesAmount} VES</Text>
            </Text>
          </View>
        </View>

        {/* Saved Beneficiaries */}
        {beneficiaries.length > 0 && (
          <View style={styles.card}>
            <TouchableOpacity
              style={styles.savedBeneficiariesHeader}
              onPress={() => setShowBeneficiaries(!showBeneficiaries)}
            >
              <Ionicons name="people" size={24} color="#2563eb" />
              <Text style={styles.cardTitle}>Beneficiarios Guardados</Text>
              <Ionicons
                name={showBeneficiaries ? 'chevron-up' : 'chevron-down'}
                size={24}
                color="#6b7280"
              />
            </TouchableOpacity>

            {showBeneficiaries && (
              <View style={styles.beneficiariesList}>
                {beneficiaries.map((ben) => (
                  <TouchableOpacity
                    key={ben.beneficiary_id}
                    style={[
                      styles.beneficiaryItem,
                      selectedBeneficiary?.beneficiary_id === ben.beneficiary_id &&
                        styles.beneficiaryItemSelected,
                    ]}
                    onPress={() => selectBeneficiary(ben)}
                  >
                    <View style={styles.beneficiaryIcon}>
                      <Ionicons name="person" size={20} color="#2563eb" />
                    </View>
                    <View style={styles.beneficiaryInfo}>
                      <Text style={styles.beneficiaryName}>{ben.full_name}</Text>
                      <Text style={styles.beneficiaryBank}>{ben.bank}</Text>
                    </View>
                    {selectedBeneficiary?.beneficiary_id === ben.beneficiary_id && (
                      <Ionicons name="checkmark-circle" size={24} color="#10b981" />
                    )}
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Beneficiary Form */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Datos del Beneficiario</Text>
          <Text style={styles.cardSubtitle}>
            Puede ser cualquier persona (familiar, amigo, tú mismo, etc.)
          </Text>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Nombre Completo *</Text>
            <TextInput
              style={styles.input}
              value={beneficiaryData.full_name}
              onChangeText={(text) =>
                setBeneficiaryData({ ...beneficiaryData, full_name: text })
              }
              placeholder="Ej: María González"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Banco *</Text>
            <TextInput
              style={styles.input}
              value={beneficiaryData.bank}
              onChangeText={(text) => setBeneficiaryData({ ...beneficiaryData, bank: text })}
              placeholder="Ej: Banco de Venezuela"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Número de Cuenta *</Text>
            <TextInput
              style={styles.input}
              value={beneficiaryData.account_number}
              onChangeText={(text) =>
                setBeneficiaryData({ ...beneficiaryData, account_number: text })
              }
              placeholder="0102-1234-5678-9012"
              keyboardType="numeric"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Cédula de Identidad *</Text>
            <TextInput
              style={styles.input}
              value={beneficiaryData.id_document}
              onChangeText={(text) =>
                setBeneficiaryData({ ...beneficiaryData, id_document: text })
              }
              placeholder="V-12345678"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Teléfono *</Text>
            <TextInput
              style={styles.input}
              value={beneficiaryData.phone_number}
              onChangeText={(text) =>
                setBeneficiaryData({ ...beneficiaryData, phone_number: text })
              }
              placeholder="+58 412-1234567"
              keyboardType="phone-pad"
            />
          </View>

          {!selectedBeneficiary && (
            <TouchableOpacity
              style={styles.saveCheckbox}
              onPress={() => setSaveBeneficiary(!saveBeneficiary)}
            >
              <View style={[styles.checkbox, saveBeneficiary && styles.checkboxChecked]}>
                {saveBeneficiary && <Ionicons name="checkmark" size={16} color="#fff" />}
              </View>
              <Text style={styles.checkboxLabel}>Guardar este beneficiario para futuros envíos</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Send Button */}
        <TouchableOpacity
          style={[styles.sendButton, loading && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="send" size={24} color="#fff" />
              <Text style={styles.sendButtonText}>Enviar {amount || '0'} RIS</Text>
            </>
          )}
        </TouchableOpacity>

        <Text style={styles.disclaimer}>
          El monto será descontado inmediatamente. El equipo procesará la transferencia y te notificará cuando esté completada.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  scrollContent: {
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  balanceCard: {
    backgroundColor: '#2563eb',
    borderRadius: 16,
    padding: 20,
    marginBottom: 16,
  },
  balanceLabel: {
    color: '#dbeafe',
    fontSize: 14,
    marginBottom: 4,
  },
  balanceAmount: {
    color: '#fff',
    fontSize: 32,
    fontWeight: 'bold',
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
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 16,
  },
  rateText: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 16,
  },
  inputContainer: {
    marginBottom: 16,
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
  conversionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f3f4f6',
    padding: 12,
    borderRadius: 8,
    gap: 8,
  },
  conversionText: {
    fontSize: 14,
    color: '#6b7280',
  },
  conversionAmount: {
    fontWeight: '700',
    color: '#059669',
    fontSize: 16,
  },
  savedBeneficiariesHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  beneficiariesList: {
    marginTop: 16,
    gap: 8,
  },
  beneficiaryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: 'transparent',
    gap: 12,
  },
  beneficiaryItemSelected: {
    backgroundColor: '#eff6ff',
    borderColor: '#2563eb',
  },
  beneficiaryIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  beneficiaryInfo: {
    flex: 1,
  },
  beneficiaryName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 2,
  },
  beneficiaryBank: {
    fontSize: 13,
    color: '#6b7280',
  },
  saveCheckbox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 8,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderWidth: 2,
    borderColor: '#d1d5db',
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxChecked: {
    backgroundColor: '#10b981',
    borderColor: '#10b981',
  },
  checkboxLabel: {
    flex: 1,
    fontSize: 14,
    color: '#374151',
  },
  sendButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f59e0b',
    padding: 16,
    borderRadius: 12,
    gap: 8,
    marginTop: 8,
  },
  sendButtonDisabled: {
    backgroundColor: '#9ca3af',
  },
  sendButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  disclaimer: {
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 16,
    lineHeight: 18,
  },
});
