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
  Platform,
  Modal,
  FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import { VENEZUELA_BANKS, CEDULA_TYPES, PHONE_PREFIXES, BankOption } from '../constants/venezuelaBanks';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Beneficiary {
  beneficiary_id: string;
  full_name: string;
  account_number: string;
  id_document: string;
  phone_number: string;
  bank: string;
  bank_code?: string;
}

export default function SendRISScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [amount, setAmount] = useState('');
  const [vesAmount, setVesAmount] = useState('');
  const [step, setStep] = useState(1); // 1 = calculadora, 2 = formulario
  
  // Estado local para las tasas (carga directa de API)
  const [rates, setRates] = useState({
    ris_to_ves: 0,
    ves_to_ris: 0,
    ris_to_brl: 1,
  });
  
  // Beneficiaries
  const [beneficiaries, setBeneficiaries] = useState<Beneficiary[]>([]);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState<Beneficiary | null>(null);
  const [showBeneficiaries, setShowBeneficiaries] = useState(false);
  const [useNewBeneficiary, setUseNewBeneficiary] = useState(true);
  
  // Form data with structured fields
  const [fullName, setFullName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [cedulaType, setCedulaType] = useState('V');
  const [cedulaNumber, setCedulaNumber] = useState('');
  const [phonePrefix, setPhonePrefix] = useState('0414');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [selectedBank, setSelectedBank] = useState<BankOption | null>(null);
  const [saveBeneficiary, setSaveBeneficiary] = useState(false);
  
  // Modals
  const [showBankModal, setShowBankModal] = useState(false);
  const [showPrefixModal, setShowPrefixModal] = useState(false);
  const [bankSearch, setBankSearch] = useState('');

  // Cargar tasas directamente desde la API
  const loadRates = async () => {
    try {
      console.log('[SendScreen] Loading rates from API...');
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      console.log('[SendScreen] Rates loaded:', response.data);
      setRates({
        ris_to_ves: response.data.ris_to_ves || 0,
        ves_to_ris: response.data.ves_to_ris || 0,
        ris_to_brl: response.data.ris_to_brl || 1,
      });
    } catch (error) {
      console.error('[SendScreen] Error loading rates:', error);
    }
  };

  useEffect(() => {
    loadBeneficiaries();
    loadRates();
    // Auto-refresh rates every 10 seconds
    const interval = setInterval(loadRates, 10000);
    return () => clearInterval(interval);
  }, []);

  // Recalcular VES cuando cambia la tasa (desde el contexto global)
  useEffect(() => {
    if (rates.ris_to_ves && amount) {
      const ris = parseFloat(amount) || 0;
      setVesAmount((ris * rates.ris_to_ves).toFixed(2));
    }
  }, [rates.ris_to_ves, amount]);

  useEffect(() => {
    // If coming from beneficiaries screen with a specific beneficiary
    if (params.beneficiaryId && beneficiaries.length > 0) {
      const ben = beneficiaries.find(b => b.beneficiary_id === params.beneficiaryId);
      if (ben) {
        selectBeneficiary(ben);
        setUseNewBeneficiary(false);
      }
    }
  }, [params.beneficiaryId, beneficiaries]);

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
    const currentRate = rates.ris_to_ves || 100;
    setVesAmount((ris * currentRate).toFixed(2));
  };

  const selectBeneficiary = (beneficiary: Beneficiary) => {
    setSelectedBeneficiary(beneficiary);
    setFullName(beneficiary.full_name);
    setAccountNumber(beneficiary.account_number);
    
    // Parse cedula
    if (beneficiary.id_document) {
      const match = beneficiary.id_document.match(/^([VE])-?(\d+)$/i);
      if (match) {
        setCedulaType(match[1].toUpperCase());
        setCedulaNumber(match[2]);
      }
    }
    
    // Parse phone
    if (beneficiary.phone_number) {
      const phoneMatch = beneficiary.phone_number.match(/\+?58\s*(04\d{2})[- ]?(\d+)/);
      if (phoneMatch) {
        setPhonePrefix(phoneMatch[1]);
        setPhoneNumber(phoneMatch[2]);
      }
    }
    
    // Find bank
    if (beneficiary.bank_code) {
      const bank = VENEZUELA_BANKS.find(b => b.code === beneficiary.bank_code);
      if (bank) setSelectedBank(bank);
    } else if (beneficiary.bank) {
      const bank = VENEZUELA_BANKS.find(b => 
        b.name.toLowerCase().includes(beneficiary.bank.toLowerCase()) ||
        beneficiary.bank.toLowerCase().includes(b.name.toLowerCase())
      );
      if (bank) setSelectedBank(bank);
    }
    
    setShowBeneficiaries(false);
    setUseNewBeneficiary(false);
  };

  const clearForm = () => {
    setSelectedBeneficiary(null);
    setFullName('');
    setAccountNumber('');
    setCedulaType('V');
    setCedulaNumber('');
    setPhonePrefix('0414');
    setPhoneNumber('');
    setSelectedBank(null);
    setSaveBeneficiary(false);
    setUseNewBeneficiary(true);
  };

  const showMessage = (title: string, message: string, onOk?: () => void) => {
    if (Platform.OS === 'web') {
      alert(`${title}\n\n${message}`);
      if (onOk) onOk();
    } else {
      Alert.alert(title, message, [{ text: 'OK', onPress: onOk }]);
    }
  };

  const getBeneficiaryData = () => {
    const idDocument = `${cedulaType}-${cedulaNumber}`;
    const fullPhone = `+58 ${phonePrefix}-${phoneNumber}`;
    
    return {
      full_name: fullName.trim(),
      account_number: accountNumber.trim(),
      id_document: idDocument,
      phone_number: fullPhone,
      bank: selectedBank ? selectedBank.fullName : '',
      bank_code: selectedBank ? selectedBank.code : '',
    };
  };

  const handleSend = async () => {
    const risAmount = parseFloat(amount);
    
    // Validations
    if (!risAmount || risAmount <= 0) {
      showMessage('Error', 'Ingresa un monto válido');
      return;
    }
    if (!user || user.balance_ris < risAmount) {
      showMessage('Error', 'Saldo insuficiente');
      return;
    }
    if (!fullName.trim()) {
      showMessage('Error', 'Ingresa el nombre del beneficiario');
      return;
    }
    if (!selectedBank) {
      showMessage('Error', 'Selecciona un banco');
      return;
    }
    if (!accountNumber.trim()) {
      showMessage('Error', 'Ingresa el número de cuenta');
      return;
    }
    if (!cedulaNumber.trim()) {
      showMessage('Error', 'Ingresa el número de cédula');
      return;
    }
    if (!phoneNumber.trim() || phoneNumber.length < 7) {
      showMessage('Error', 'Ingresa un número de teléfono válido');
      return;
    }

    const beneficiaryData = getBeneficiaryData();

    const doSend = async () => {
      setLoading(true);
      try {
        const token = await AsyncStorage.getItem('session_token');
        
        // Save beneficiary if checkbox is checked
        if (saveBeneficiary && !selectedBeneficiary) {
          try {
            await axios.post(
              `${BACKEND_URL}/api/beneficiaries`,
              beneficiaryData,
              { headers: { Authorization: `Bearer ${token}` } }
            );
          } catch (e) {
            console.log('Could not save beneficiary:', e);
          }
        }
        
        await axios.post(
          `${BACKEND_URL}/api/withdrawal/create`,
          { amount_ris: risAmount, beneficiary_data: beneficiaryData },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        
        await refreshUser();
        showMessage('¡Éxito!', 'Envío realizado. El equipo procesará tu transferencia y te notificará.', () => router.back());
      } catch (error: any) {
        showMessage('Error', error.response?.data?.detail || 'No se pudo procesar');
      } finally {
        setLoading(false);
      }
    };

    if (Platform.OS === 'web') {
      const confirmed = confirm(`¿Enviar ${risAmount} RIS a ${fullName}?\n\nBanco: ${selectedBank.name} (${selectedBank.code})\nRecibirá: ${vesAmount} VES`);
      if (confirmed) doSend();
    } else {
      Alert.alert(
        'Confirmar Envío',
        `¿Enviar ${risAmount} RIS a ${fullName}?\n\nBanco: ${selectedBank.name} (${selectedBank.code})\nRecibirá: ${vesAmount} VES`,
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Enviar', onPress: doSend }
        ]
      );
    }
  };

  const filteredBanks = VENEZUELA_BANKS.filter(b => 
    b.name.toLowerCase().includes(bankSearch.toLowerCase()) ||
    b.code.includes(bankSearch)
  );

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => step === 1 ? router.back() : setStep(1)}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Enviar a Venezuela</Text>
          <TouchableOpacity onPress={() => router.push('/beneficiaries')}>
            <Ionicons name="people" size={24} color="#2563eb" />
          </TouchableOpacity>
        </View>

        {/* Step 1: Calculator */}
        {step === 1 && (
          <>
            {/* Rate Card */}
            <View style={styles.rateCard}>
              <View style={styles.rateHeader}>
                <Ionicons name="swap-horizontal" size={24} color="#F5A623" />
                <Text style={styles.rateTitle}>Tasa del día</Text>
              </View>
              <Text style={styles.rateValue}>1 RIS = {(rates?.ris_to_ves || 0).toFixed(2)} VES</Text>
            </View>

            {/* Calculator */}
            <View style={styles.calculatorCard}>
              <Text style={styles.calculatorTitle}>¿Cuánto deseas enviar?</Text>
              
              <View style={styles.calcInputGroup}>
                <Text style={styles.calcInputLabel}>Envías (RIS)</Text>
                <TextInput
                  style={styles.calcInput}
                  value={amount}
                  onChangeText={handleAmountChange}
                  keyboardType="numeric"
                  placeholder="0.00"
                  placeholderTextColor="#9ca3af"
                />
              </View>

              <View style={styles.calcArrow}>
                <Ionicons name="arrow-down" size={28} color="#F5A623" />
              </View>

              <View style={styles.calcInputGroup}>
                <Text style={styles.calcInputLabel}>Recibe (VES)</Text>
                <TextInput
                  style={[styles.calcInput, styles.calcInputResult]}
                  value={vesAmount}
                  editable={false}
                  placeholder="0.00"
                  placeholderTextColor="#9ca3af"
                />
              </View>

              {/* Balance Info */}
              <View style={styles.balanceInfo}>
                <Ionicons name="wallet" size={16} color="#64748b" />
                <Text style={styles.balanceInfoText}>
                  Tu balance: <Text style={styles.balanceInfoAmount}>{user?.balance_ris?.toFixed(2) || '0.00'} RIS</Text>
                </Text>
              </View>

              {/* Continue Button */}
              {parseFloat(amount) > 0 && (
                <TouchableOpacity 
                  style={[
                    styles.continueBtn,
                    parseFloat(amount) > (user?.balance_ris || 0) && styles.continueBtnDisabled
                  ]}
                  onPress={() => {
                    if (parseFloat(amount) > (user?.balance_ris || 0)) {
                      showMessage('Saldo Insuficiente', 'No tienes suficiente balance para este envío');
                      return;
                    }
                    setStep(2);
                  }}
                >
                  <Text style={styles.continueBtnText}>
                    Enviar {amount} RIS → {vesAmount} VES
                  </Text>
                  <Ionicons name="arrow-forward" size={20} color="#fff" />
                </TouchableOpacity>
              )}
            </View>
          </>
        )}

        {/* Step 2: Beneficiary Form */}
        {step === 2 && (
          <>
            {/* Amount Summary */}
            <View style={styles.amountSummary}>
              <View style={styles.amountSummaryRow}>
                <Text style={styles.amountSummaryLabel}>Envías:</Text>
                <Text style={styles.amountSummaryValue}>{amount} RIS</Text>
              </View>
              <Ionicons name="arrow-forward" size={20} color="#F5A623" />
              <View style={styles.amountSummaryRow}>
                <Text style={styles.amountSummaryLabel}>Recibe:</Text>
                <Text style={[styles.amountSummaryValue, { color: '#059669' }]}>{vesAmount} VES</Text>
              </View>
            </View>

            {/* Beneficiary Selection */}
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Datos del Beneficiario</Text>
              
              {/* Toggle between saved and new */}
              <View style={styles.beneficiaryToggle}>
                <TouchableOpacity
                  style={[styles.toggleButton, !useNewBeneficiary && styles.toggleButtonActive]}
                  onPress={() => beneficiaries.length > 0 && setShowBeneficiaries(true)}
                  disabled={beneficiaries.length === 0}
                >
                  <Ionicons name="bookmark" size={18} color={!useNewBeneficiary ? '#fff' : '#6b7280'} />
                  <Text style={[styles.toggleButtonText, !useNewBeneficiary && styles.toggleButtonTextActive]}>
                    Guardados ({beneficiaries.length})
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.toggleButton, useNewBeneficiary && styles.toggleButtonActive]}
                  onPress={clearForm}
                >
                  <Ionicons name="person-add" size={18} color={useNewBeneficiary ? '#fff' : '#6b7280'} />
                  <Text style={[styles.toggleButtonText, useNewBeneficiary && styles.toggleButtonTextActive]}>
                    Nuevo
                  </Text>
                </TouchableOpacity>
          </View>

          {/* Selected beneficiary indicator */}
          {selectedBeneficiary && !useNewBeneficiary && (
            <View style={styles.selectedBeneficiaryBanner}>
              <Ionicons name="checkmark-circle" size={20} color="#10b981" />
              <Text style={styles.selectedBeneficiaryText}>
                Enviando a: {selectedBeneficiary.full_name}
              </Text>
              <TouchableOpacity onPress={clearForm}>
                <Ionicons name="close-circle" size={20} color="#6b7280" />
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Beneficiary Form */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Datos del Beneficiario</Text>
          <Text style={styles.cardSubtitle}>
            {useNewBeneficiary ? 'Ingresa los datos de quien recibirá el dinero' : 'Verifica los datos antes de enviar'}
          </Text>

          {/* Name */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Nombre Completo *</Text>
            <TextInput
              style={styles.input}
              value={fullName}
              onChangeText={setFullName}
              placeholder="Ej: María González"
            />
          </View>

          {/* Bank Selector */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Banco *</Text>
            <TouchableOpacity 
              style={styles.selectorButton}
              onPress={() => setShowBankModal(true)}
            >
              {selectedBank ? (
                <View style={styles.selectedBankContainer}>
                  <Text style={styles.bankCode}>{selectedBank.code}</Text>
                  <Text style={styles.bankName}>{selectedBank.name}</Text>
                </View>
              ) : (
                <Text style={styles.selectorPlaceholder}>Seleccionar banco</Text>
              )}
              <Ionicons name="chevron-down" size={20} color="#6b7280" />
            </TouchableOpacity>
          </View>

          {/* Account Number */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Número de Cuenta *</Text>
            <TextInput
              style={styles.input}
              value={accountNumber}
              onChangeText={setAccountNumber}
              placeholder="01020000000000000000"
              keyboardType="numeric"
              maxLength={20}
            />
          </View>

          {/* Cedula with Type Selector */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Cédula de Identidad *</Text>
            <View style={styles.rowInputContainer}>
              <View style={styles.typeSelector}>
                {CEDULA_TYPES.map((type) => (
                  <TouchableOpacity
                    key={type.value}
                    style={[styles.typeOption, cedulaType === type.value && styles.typeOptionActive]}
                    onPress={() => setCedulaType(type.value)}
                  >
                    <Text style={[styles.typeOptionText, cedulaType === type.value && styles.typeOptionTextActive]}>
                      {type.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TextInput
                style={[styles.input, styles.flexInput]}
                value={cedulaNumber}
                onChangeText={setCedulaNumber}
                placeholder="12345678"
                keyboardType="numeric"
                maxLength={10}
              />
            </View>
          </View>

          {/* Phone with Prefix Selector */}
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Teléfono (Aplica para Pago Móvil) *</Text>
            <View style={styles.phoneRow}>
              <View style={styles.phoneFixed}>
                <Text style={styles.phoneFixedText}>(+58)</Text>
              </View>
              <TouchableOpacity 
                style={styles.phonePrefixButton}
                onPress={() => setShowPrefixModal(true)}
              >
                <Text style={styles.phonePrefixText}>{phonePrefix}</Text>
                <Ionicons name="chevron-down" size={16} color="#6b7280" />
              </TouchableOpacity>
              <Text style={styles.phoneSeparator}>-</Text>
              <TextInput
                style={styles.phoneNumberInput}
                value={phoneNumber}
                onChangeText={(text) => setPhoneNumber(text.replace(/[^0-9]/g, ''))}
                placeholder="7666491"
                keyboardType="number-pad"
                maxLength={7}
              />
            </View>
            <Text style={styles.phoneHint}>Formato: (+58)0414-7666491</Text>
          </View>

          {/* Save checkbox for new beneficiary */}
          {useNewBeneficiary && (
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
          </>
        )}
      </ScrollView>

      {/* Bank Selection Modal */}
      <Modal
        visible={showBankModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowBankModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Seleccionar Banco</Text>
              <TouchableOpacity onPress={() => setShowBankModal(false)}>
                <Ionicons name="close" size={24} color="#1f2937" />
              </TouchableOpacity>
            </View>
            
            <TextInput
              style={styles.searchInput}
              placeholder="Buscar por nombre o código..."
              value={bankSearch}
              onChangeText={setBankSearch}
            />
            
            <FlatList
              data={filteredBanks}
              keyExtractor={(item) => item.code}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[styles.bankItem, selectedBank?.code === item.code && styles.bankItemSelected]}
                  onPress={() => {
                    setSelectedBank(item);
                    setShowBankModal(false);
                    setBankSearch('');
                  }}
                >
                  <Text style={styles.bankItemCode}>{item.code}</Text>
                  <View style={styles.bankItemInfo}>
                    <Text style={styles.bankItemName}>{item.name}</Text>
                    <Text style={styles.bankItemFullName}>{item.fullName}</Text>
                  </View>
                  {selectedBank?.code === item.code && (
                    <Ionicons name="checkmark-circle" size={24} color="#10b981" />
                  )}
                </TouchableOpacity>
              )}
              style={styles.bankList}
            />
          </View>
        </View>
      </Modal>

      {/* Phone Prefix Selection Modal */}
      <Modal
        visible={showPrefixModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowPrefixModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.prefixModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Seleccionar Operadora</Text>
              <TouchableOpacity onPress={() => setShowPrefixModal(false)}>
                <Ionicons name="close" size={24} color="#1f2937" />
              </TouchableOpacity>
            </View>
            
            {PHONE_PREFIXES.map((prefix) => (
              <TouchableOpacity
                key={prefix.value}
                style={[styles.prefixModalItem, phonePrefix === prefix.value && styles.prefixModalItemSelected]}
                onPress={() => {
                  setPhonePrefix(prefix.value);
                  setShowPrefixModal(false);
                }}
              >
                <Text style={[styles.prefixModalItemText, phonePrefix === prefix.value && styles.prefixModalItemTextSelected]}>
                  {prefix.label}
                </Text>
                {phonePrefix === prefix.value && (
                  <Ionicons name="checkmark-circle" size={24} color="#10b981" />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </Modal>

      {/* Beneficiaries Selection Modal */}
      <Modal
        visible={showBeneficiaries}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowBeneficiaries(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Beneficiarios Guardados</Text>
              <TouchableOpacity onPress={() => setShowBeneficiaries(false)}>
                <Ionicons name="close" size={24} color="#1f2937" />
              </TouchableOpacity>
            </View>
            
            <FlatList
              data={beneficiaries}
              keyExtractor={(item) => item.beneficiary_id}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.beneficiaryItem}
                  onPress={() => selectBeneficiary(item)}
                >
                  <View style={styles.beneficiaryIcon}>
                    <Ionicons name="person" size={20} color="#2563eb" />
                  </View>
                  <View style={styles.beneficiaryInfo}>
                    <Text style={styles.beneficiaryName}>{item.full_name}</Text>
                    <Text style={styles.beneficiaryBank}>
                      {item.bank_code ? `${item.bank_code} - ` : ''}{item.bank}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color="#6b7280" />
                </TouchableOpacity>
              )}
              style={styles.beneficiaryList}
              ListEmptyComponent={
                <Text style={styles.emptyListText}>No tienes beneficiarios guardados</Text>
              }
            />
          </View>
        </View>
      </Modal>
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
  beneficiaryToggle: {
    flexDirection: 'row',
    backgroundColor: '#f3f4f6',
    borderRadius: 8,
    padding: 4,
    marginBottom: 16,
  },
  toggleButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 6,
    gap: 6,
  },
  toggleButtonActive: {
    backgroundColor: '#2563eb',
  },
  toggleButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  toggleButtonTextActive: {
    color: '#fff',
  },
  selectedBeneficiaryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ecfdf5',
    padding: 12,
    borderRadius: 8,
    gap: 8,
  },
  selectedBeneficiaryText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    color: '#059669',
  },
  selectorButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    padding: 12,
  },
  selectorPlaceholder: {
    fontSize: 16,
    color: '#9ca3af',
  },
  selectedBankContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  bankCode: {
    backgroundColor: '#2563eb',
    color: '#fff',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    fontSize: 12,
    fontWeight: '700',
  },
  bankName: {
    fontSize: 16,
    color: '#1f2937',
    fontWeight: '500',
  },
  rowInputContainer: {
    flexDirection: 'row',
    gap: 8,
  },
  typeSelector: {
    flexDirection: 'row',
    backgroundColor: '#f3f4f6',
    borderRadius: 8,
    padding: 4,
  },
  typeOption: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 6,
  },
  typeOptionActive: {
    backgroundColor: '#2563eb',
  },
  typeOptionText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6b7280',
  },
  typeOptionTextActive: {
    color: '#fff',
  },
  flexInput: {
    flex: 1,
  },
  // Phone styles
  phoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  phoneFixed: {
    backgroundColor: '#e5e7eb',
    paddingHorizontal: 10,
    paddingVertical: 12,
    borderRadius: 8,
  },
  phoneFixedText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  phonePrefixButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 12,
    gap: 4,
  },
  phonePrefixText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
  },
  phoneSeparator: {
    fontSize: 16,
    color: '#6b7280',
    marginHorizontal: 2,
  },
  phoneNumberInput: {
    flex: 1,
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
  phoneHint: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 6,
  },
  // Prefix modal styles
  prefixModalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 30,
  },
  prefixModalItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  prefixModalItemSelected: {
    backgroundColor: '#eff6ff',
  },
  prefixModalItemText: {
    fontSize: 18,
    fontWeight: '500',
    color: '#1f2937',
  },
  prefixModalItemTextSelected: {
    color: '#2563eb',
    fontWeight: '600',
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
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  searchInput: {
    backgroundColor: '#f3f4f6',
    margin: 16,
    padding: 12,
    borderRadius: 8,
    fontSize: 16,
  },
  bankList: {
    maxHeight: 400,
  },
  bankItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
    gap: 12,
  },
  bankItemSelected: {
    backgroundColor: '#eff6ff',
  },
  bankItemCode: {
    backgroundColor: '#2563eb',
    color: '#fff',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    fontSize: 12,
    fontWeight: '700',
  },
  bankItemInfo: {
    flex: 1,
  },
  bankItemName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  bankItemFullName: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 2,
  },
  beneficiaryList: {
    maxHeight: 400,
  },
  beneficiaryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
    gap: 12,
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
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 2,
  },
  beneficiaryBank: {
    fontSize: 13,
    color: '#6b7280',
  },
  emptyListText: {
    textAlign: 'center',
    color: '#6b7280',
    padding: 20,
  },
  
  // New Calculator Styles
  rateCard: {
    backgroundColor: '#fffbeb',
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#fde68a',
  },
  rateHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rateTitle: {
    fontSize: 14,
    color: '#92400e',
    fontWeight: '500',
  },
  rateValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#F5A623',
  },
  calculatorCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  calculatorTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
    textAlign: 'center',
    marginBottom: 24,
  },
  calcInputGroup: {
    marginBottom: 8,
  },
  calcInputLabel: {
    fontSize: 13,
    color: '#64748b',
    marginBottom: 8,
    fontWeight: '500',
  },
  calcInput: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    padding: 16,
    fontSize: 24,
    fontWeight: '600',
    color: '#0f172a',
    textAlign: 'center',
    borderWidth: 2,
    borderColor: '#e2e8f0',
  },
  calcInputResult: {
    backgroundColor: '#f0fdf4',
    borderColor: '#bbf7d0',
    color: '#059669',
  },
  calcArrow: {
    alignItems: 'center',
    marginVertical: 12,
  },
  balanceInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  balanceInfoText: {
    fontSize: 14,
    color: '#64748b',
  },
  balanceInfoAmount: {
    fontWeight: '600',
    color: '#0f172a',
  },
  continueBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 14,
    padding: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginTop: 20,
  },
  continueBtnDisabled: {
    backgroundColor: '#94a3b8',
  },
  continueBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  amountSummary: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f0f9ff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    gap: 16,
  },
  amountSummaryRow: {
    alignItems: 'center',
  },
  amountSummaryLabel: {
    fontSize: 12,
    color: '#64748b',
  },
  amountSummaryValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
});
