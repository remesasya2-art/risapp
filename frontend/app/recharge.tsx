import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  ScrollView,
  Image,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import * as Clipboard from 'expo-clipboard';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function RechargeScreen() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [amount, setAmount] = useState('');
  const [cpf, setCpf] = useState('');
  const [loading, setLoading] = useState(false);
  const [pixData, setPixData] = useState<{
    qr_code: string;
    qr_code_base64: string;
    transaction_id: string;
    expiration: string;
    amount_brl: number;
  } | null>(null);
  const [checkingPayment, setCheckingPayment] = useState(false);
  const [paymentCompleted, setPaymentCompleted] = useState(false);

  // Quick amount options
  const quickAmounts = [50, 100, 200, 500, 1000, 2000];

  const formatCPF = (value: string) => {
    const numbers = value.replace(/\D/g, '');
    if (numbers.length <= 3) return numbers;
    if (numbers.length <= 6) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
    if (numbers.length <= 9) return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6)}`;
    return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6, 9)}-${numbers.slice(9, 11)}`;
  };

  const handleCPFChange = (text: string) => {
    const formatted = formatCPF(text);
    if (formatted.length <= 14) {
      setCpf(formatted);
    }
  };

  const handleCreatePix = async () => {
    const amountNum = parseFloat(amount);
    
    if (!amountNum || amountNum < 10) {
      Alert.alert('Error', 'El monto mínimo es R$ 10,00');
      return;
    }
    
    if (amountNum > 2000) {
      Alert.alert('Error', 'El monto máximo por transacción es R$ 2.000,00');
      return;
    }
    
    const cpfClean = cpf.replace(/\D/g, '');
    if (cpfClean.length !== 11) {
      Alert.alert('Error', 'Por favor ingresa un CPF válido');
      return;
    }

    setLoading(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.post(
        `${BACKEND_URL}/api/pix/create`,
        { amount: amountNum, cpf: cpfClean },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setPixData(response.data);
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Error al crear el pago PIX';
      Alert.alert('Error', message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyPixCode = async () => {
    if (pixData?.qr_code) {
      await Clipboard.setStringAsync(pixData.qr_code);
      Alert.alert('Copiado', 'Código PIX copiado al portapapeles');
    }
  };

  const checkPaymentStatus = async () => {
    if (!pixData?.transaction_id) return;

    setCheckingPayment(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(
        `${BACKEND_URL}/api/pix/status/${pixData.transaction_id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (response.data.status === 'completed') {
        setPaymentCompleted(true);
        await refreshUser();
        Alert.alert(
          '¡Pago Confirmado!',
          `Tu recarga de R$ ${pixData.amount_brl.toFixed(2)} fue procesada. Ya tienes ${response.data.amount_ris} RIS en tu cuenta.`,
          [{ text: 'OK', onPress: () => router.replace('/') }]
        );
      } else if (response.data.status === 'pending') {
        Alert.alert('Pendiente', 'El pago aún no ha sido confirmado. Intenta nuevamente en unos segundos.');
      } else {
        Alert.alert('Estado', `Estado del pago: ${response.data.status}`);
      }
    } catch (error) {
      Alert.alert('Error', 'No se pudo verificar el estado del pago');
    } finally {
      setCheckingPayment(false);
    }
  };

  // If showing PIX QR code
  if (pixData && !paymentCompleted) {
    return (
      <SafeAreaView style={styles.container}>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setPixData(null)} style={styles.backButton}>
              <Ionicons name="arrow-back" size={24} color="#1e293b" />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Pagar con PIX</Text>
            <View style={{ width: 40 }} />
          </View>

          {/* Amount */}
          <View style={styles.amountCard}>
            <Text style={styles.amountLabel}>Valor a pagar</Text>
            <Text style={styles.amountValue}>R$ {pixData.amount_brl.toFixed(2)}</Text>
            <Text style={styles.amountRis}>= {pixData.amount_brl.toFixed(2)} RIS</Text>
          </View>

          {/* QR Code */}
          <View style={styles.qrContainer}>
            <Text style={styles.qrTitle}>Escanea el código QR</Text>
            {pixData.qr_code_base64 && (
              <Image
                source={{ uri: `data:image/png;base64,${pixData.qr_code_base64}` }}
                style={styles.qrImage}
                resizeMode="contain"
              />
            )}
            <Text style={styles.qrSubtitle}>
              Abre la app de tu banco y escanea el código QR
            </Text>
          </View>

          {/* Copy PIX Code */}
          <View style={styles.copySection}>
            <Text style={styles.copyTitle}>O copia el código PIX:</Text>
            <View style={styles.codeContainer}>
              <Text style={styles.pixCode} numberOfLines={2}>
                {pixData.qr_code?.substring(0, 50)}...
              </Text>
              <TouchableOpacity style={styles.copyButton} onPress={handleCopyPixCode}>
                <Ionicons name="copy-outline" size={20} color="#fff" />
                <Text style={styles.copyButtonText}>Copiar</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Expiration Warning */}
          <View style={styles.warningContainer}>
            <Ionicons name="time-outline" size={20} color="#f59e0b" />
            <Text style={styles.warningText}>
              Este código expira en 30 minutos
            </Text>
          </View>

          {/* Check Payment Button */}
          <TouchableOpacity
            style={styles.checkButton}
            onPress={checkPaymentStatus}
            disabled={checkingPayment}
          >
            {checkingPayment ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="checkmark-circle-outline" size={24} color="#fff" />
                <Text style={styles.checkButtonText}>Ya pagué, verificar</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Instructions */}
          <View style={styles.instructionsContainer}>
            <Text style={styles.instructionsTitle}>Cómo pagar:</Text>
            <View style={styles.instructionStep}>
              <Text style={styles.stepNumber}>1</Text>
              <Text style={styles.stepText}>Abre la app de tu banco</Text>
            </View>
            <View style={styles.instructionStep}>
              <Text style={styles.stepNumber}>2</Text>
              <Text style={styles.stepText}>Busca la opción "Pagar con PIX"</Text>
            </View>
            <View style={styles.instructionStep}>
              <Text style={styles.stepNumber}>3</Text>
              <Text style={styles.stepText}>Escanea el QR o pega el código copiado</Text>
            </View>
            <View style={styles.instructionStep}>
              <Text style={styles.stepNumber}>4</Text>
              <Text style={styles.stepText}>Confirma el pago y vuelve aquí</Text>
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color="#1e293b" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Recargar con PIX</Text>
          <View style={{ width: 40 }} />
        </View>

        {/* Balance Card */}
        <View style={styles.balanceCard}>
          <Ionicons name="wallet-outline" size={32} color="#2563eb" />
          <View style={styles.balanceInfo}>
            <Text style={styles.balanceLabel}>Tu saldo actual</Text>
            <Text style={styles.balanceValue}>{user?.balance_ris?.toFixed(2) || '0.00'} RIS</Text>
          </View>
        </View>

        {/* Amount Input */}
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>Monto a recargar (BRL)</Text>
          <View style={styles.amountInputContainer}>
            <Text style={styles.currencySymbol}>R$</Text>
            <TextInput
              style={styles.amountInput}
              value={amount}
              onChangeText={setAmount}
              placeholder="0.00"
              keyboardType="decimal-pad"
              placeholderTextColor="#9ca3af"
            />
          </View>
          <Text style={styles.conversionText}>
            = {amount ? parseFloat(amount).toFixed(2) : '0.00'} RIS
          </Text>
        </View>

        {/* Quick Amount Buttons */}
        <View style={styles.quickAmountsContainer}>
          <Text style={styles.quickAmountsLabel}>Valores rápidos:</Text>
          <View style={styles.quickAmountsGrid}>
            {quickAmounts.map((quickAmount) => (
              <TouchableOpacity
                key={quickAmount}
                style={[
                  styles.quickAmountButton,
                  amount === String(quickAmount) && styles.quickAmountButtonActive,
                ]}
                onPress={() => setAmount(String(quickAmount))}
              >
                <Text
                  style={[
                    styles.quickAmountText,
                    amount === String(quickAmount) && styles.quickAmountTextActive,
                  ]}
                >
                  R$ {quickAmount}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* CPF Input */}
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>CPF del pagador</Text>
          <TextInput
            style={styles.cpfInput}
            value={cpf}
            onChangeText={handleCPFChange}
            placeholder="000.000.000-00"
            keyboardType="number-pad"
            placeholderTextColor="#9ca3af"
          />
          <Text style={styles.cpfNote}>
            El CPF debe coincidir con el titular del banco
          </Text>
        </View>

        {/* Limits Info */}
        <View style={styles.limitsContainer}>
          <Ionicons name="information-circle-outline" size={20} color="#6b7280" />
          <View style={styles.limitsTextContainer}>
            <Text style={styles.limitsText}>Mínimo: R$ 10,00 | Máximo: R$ 2.000,00</Text>
            <Text style={styles.limitsText}>Conversión: 1 BRL = 1 RIS</Text>
          </View>
        </View>

        {/* Create PIX Button */}
        <TouchableOpacity
          style={[styles.createButton, (!amount || !cpf) && styles.createButtonDisabled]}
          onPress={handleCreatePix}
          disabled={loading || !amount || !cpf}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="qr-code-outline" size={24} color="#fff" />
              <Text style={styles.createButtonText}>Generar código PIX</Text>
            </>
          )}
        </TouchableOpacity>

        {/* PIX Logo */}
        <View style={styles.pixLogoContainer}>
          <Text style={styles.pixLogoText}>Pago instantáneo via</Text>
          <Text style={styles.pixBrand}>PIX</Text>
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
  scrollContent: {
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  balanceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    padding: 16,
    borderRadius: 12,
    marginBottom: 24,
  },
  balanceInfo: {
    marginLeft: 12,
  },
  balanceLabel: {
    fontSize: 14,
    color: '#64748b',
  },
  balanceValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#2563eb',
  },
  inputSection: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1e293b',
    marginBottom: 8,
  },
  amountInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    paddingHorizontal: 16,
  },
  currencySymbol: {
    fontSize: 24,
    fontWeight: '600',
    color: '#64748b',
    marginRight: 8,
  },
  amountInput: {
    flex: 1,
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1e293b',
    paddingVertical: 16,
  },
  conversionText: {
    fontSize: 14,
    color: '#10b981',
    marginTop: 8,
    fontWeight: '500',
  },
  quickAmountsContainer: {
    marginBottom: 20,
  },
  quickAmountsLabel: {
    fontSize: 14,
    color: '#64748b',
    marginBottom: 8,
  },
  quickAmountsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  quickAmountButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  quickAmountButtonActive: {
    backgroundColor: '#2563eb',
    borderColor: '#2563eb',
  },
  quickAmountText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#64748b',
  },
  quickAmountTextActive: {
    color: '#fff',
  },
  cpfInput: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#e2e8f0',
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 18,
    color: '#1e293b',
  },
  cpfNote: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 4,
  },
  limitsContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#f1f5f9',
    padding: 12,
    borderRadius: 8,
    marginBottom: 24,
  },
  limitsTextContainer: {
    marginLeft: 8,
    flex: 1,
  },
  limitsText: {
    fontSize: 13,
    color: '#6b7280',
  },
  createButton: {
    backgroundColor: '#2563eb',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
  },
  createButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  createButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  pixLogoContainer: {
    alignItems: 'center',
    marginTop: 24,
  },
  pixLogoText: {
    fontSize: 12,
    color: '#9ca3af',
  },
  pixBrand: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#32bcad',
  },
  // PIX Payment Screen Styles
  amountCard: {
    backgroundColor: '#2563eb',
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    marginBottom: 24,
  },
  amountLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
  },
  amountValue: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#fff',
    marginTop: 4,
  },
  amountRis: {
    fontSize: 16,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 4,
  },
  qrContainer: {
    backgroundColor: '#fff',
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  qrTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1e293b',
    marginBottom: 16,
  },
  qrImage: {
    width: 200,
    height: 200,
    marginBottom: 16,
  },
  qrSubtitle: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
  },
  copySection: {
    marginBottom: 16,
  },
  copyTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1e293b',
    marginBottom: 8,
  },
  codeContainer: {
    backgroundColor: '#f1f5f9',
    borderRadius: 8,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
  },
  pixCode: {
    flex: 1,
    fontSize: 12,
    color: '#64748b',
    marginRight: 8,
  },
  copyButton: {
    backgroundColor: '#2563eb',
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
    gap: 4,
  },
  copyButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  warningContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef3c7',
    padding: 12,
    borderRadius: 8,
    marginBottom: 16,
  },
  warningText: {
    marginLeft: 8,
    fontSize: 14,
    color: '#92400e',
  },
  checkButton: {
    backgroundColor: '#10b981',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
    marginBottom: 24,
  },
  checkButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  instructionsContainer: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
  },
  instructionsTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1e293b',
    marginBottom: 12,
  },
  instructionStep: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  stepNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#2563eb',
    color: '#fff',
    textAlign: 'center',
    lineHeight: 24,
    fontSize: 14,
    fontWeight: '600',
    marginRight: 12,
  },
  stepText: {
    flex: 1,
    fontSize: 14,
    color: '#475569',
  },
});
