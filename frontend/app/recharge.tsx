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
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const showAlert = (title: string, message: string | any, buttons?: any[]) => {
  // Ensure message is a string
  let displayMessage = message;
  if (typeof message === 'object') {
    if (Array.isArray(message)) {
      displayMessage = message.map(m => typeof m === 'object' ? JSON.stringify(m) : m).join('\n');
    } else if (message?.msg) {
      displayMessage = message.msg;
    } else if (message?.detail) {
      displayMessage = message.detail;
    } else {
      displayMessage = JSON.stringify(message);
    }
  }
  
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${displayMessage}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, String(displayMessage), buttons);
  }
};

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
  const [proofImage, setProofImage] = useState<string | null>(null);
  const [uploadingProof, setUploadingProof] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const quickAmounts = [50, 100, 200, 500, 1000];

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
      showAlert('Monto Mínimo', 'El monto mínimo es R$ 10,00');
      return;
    }
    
    if (amountNum > 2000) {
      showAlert('Monto Máximo', 'El monto máximo por transacción es R$ 2.000,00');
      return;
    }
    
    const cleanCpf = cpf.replace(/\D/g, '');
    if (cleanCpf.length !== 11) {
      showAlert('CPF Inválido', 'Por favor ingresa un CPF válido (11 dígitos)');
      return;
    }

    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      
      const response = await axios.post(
        `${BACKEND_URL}/api/pix/create`,
        { amount_brl: amountNum, payer_cpf: cleanCpf },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      setPixData(response.data);
    } catch (error: any) {
      // Handle different error formats
      let errorMessage = 'Error al generar PIX';
      if (error.response?.data) {
        const data = error.response.data;
        if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (Array.isArray(data.detail)) {
          // Pydantic validation errors
          errorMessage = data.detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join('\n');
        } else if (data.message) {
          errorMessage = data.message;
        }
      }
      showAlert('Error', errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const copyPixCode = async () => {
    if (pixData?.qr_code) {
      await Clipboard.setStringAsync(pixData.qr_code);
      showAlert('Copiado', 'Código PIX copiado al portapapeles');
    }
  };

  const takeProofPhoto = async () => {
    try {
      const permissionResult = await ImagePicker.requestCameraPermissionsAsync();
      if (!permissionResult.granted) {
        showAlert('Permiso Requerido', 'Necesitamos acceso a la cámara');
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        quality: 0.8,
        base64: true,
      });

      if (!result.canceled && result.assets[0].base64) {
        setProofImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
      }
    } catch (error) {
      console.error('Error taking photo:', error);
    }
  };

  const pickProofFromGallery = async () => {
    try {
      const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permissionResult.granted) {
        showAlert('Permiso Requerido', 'Necesitamos acceso a tu galería de fotos');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: false,
        quality: 0.8,
        base64: true,
      });

      if (!result.canceled && result.assets[0].base64) {
        setProofImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
      }
    } catch (error) {
      console.error('Error picking image:', error);
    }
  };

  const uploadProof = async () => {
    if (!proofImage || !pixData) return;

    try {
      setUploadingProof(true);
      const token = await AsyncStorage.getItem('session_token');
      
      await axios.post(
        `${BACKEND_URL}/api/pix/upload-proof`,
        { transaction_id: pixData.transaction_id, proof_image: proofImage },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      showAlert('Comprobante Enviado', 'Tu pago está siendo verificado. Recibirás una notificación pronto.', [
        { text: 'OK', onPress: () => { refreshUser(); router.replace('/'); } }
      ]);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'Error al enviar comprobante');
    } finally {
      setUploadingProof(false);
    }
  };

  const handleCancelRecharge = async () => {
    if (!pixData) return;
    
    Alert.alert(
      'Cancelar Recarga',
      '¿Estás seguro de cancelar esta recarga?',
      [
        { text: 'No', style: 'cancel' },
        {
          text: 'Sí, Cancelar',
          style: 'destructive',
          onPress: async () => {
            try {
              setCancelling(true);
              const token = await AsyncStorage.getItem('session_token');
              await axios.post(
                `${BACKEND_URL}/api/pix/cancel`,
                { transaction_id: pixData.transaction_id },
                { headers: { Authorization: `Bearer ${token}` } }
              );
              showAlert('Recarga Cancelada', 'La recarga ha sido cancelada');
              setPixData(null);
              setAmount('');
              setCpf('');
              setProofImage(null);
            } catch (error: any) {
              showAlert('Error', error.response?.data?.detail || 'Error al cancelar');
            } finally {
              setCancelling(false);
            }
          }
        }
      ]
    );
  };

  // Amount selection screen
  if (!pixData) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
              <Ionicons name="arrow-back" size={24} color="#0f172a" />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Recargar con PIX</Text>
            <View style={{ width: 44 }} />
          </View>

          {/* Balance Card */}
          <View style={styles.balanceCard}>
            <View style={styles.balanceHeader}>
              <View style={styles.balanceIcon}>
                <Ionicons name="wallet" size={24} color="#F5A623" />
              </View>
              <Text style={styles.balanceLabel}>Tu Saldo Actual</Text>
            </View>
            <Text style={styles.balanceAmount}>
              {user?.balance_ris?.toFixed(2) || '0.00'} <Text style={styles.balanceCurrency}>RIS</Text>
            </Text>
          </View>

          {/* Amount Input */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Monto a Recargar</Text>
            <View style={styles.amountInputContainer}>
              <Text style={styles.currencyPrefix}>R$</Text>
              <TextInput
                style={styles.amountInput}
                value={amount}
                onChangeText={setAmount}
                keyboardType="numeric"
                placeholder="0.00"
                placeholderTextColor="#94a3b8"
              />
            </View>
            <Text style={styles.limitText}>Mínimo R$ 10 • Máximo R$ 2.000</Text>
          </View>

          {/* Quick Amounts */}
          <View style={styles.quickAmountsContainer}>
            {quickAmounts.map((quick) => (
              <TouchableOpacity
                key={quick}
                style={[styles.quickAmountBtn, amount === quick.toString() && styles.quickAmountBtnActive]}
                onPress={() => setAmount(quick.toString())}
              >
                <Text style={[styles.quickAmountText, amount === quick.toString() && styles.quickAmountTextActive]}>
                  R$ {quick}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* CPF Input */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>CPF do Pagador</Text>
            <View style={styles.cpfInputContainer}>
              <Ionicons name="person-outline" size={20} color="#64748b" />
              <TextInput
                style={styles.cpfInput}
                value={cpf}
                onChangeText={handleCPFChange}
                keyboardType="numeric"
                placeholder="000.000.000-00"
                placeholderTextColor="#94a3b8"
                maxLength={14}
              />
            </View>
            <Text style={styles.cpfHint}>Deve ser o CPF do titular da conta</Text>
          </View>

          {/* Info Card */}
          <View style={styles.infoCard}>
            <Ionicons name="information-circle" size={20} color="#0369a1" />
            <View style={styles.infoContent}>
              <Text style={styles.infoTitle}>Como funciona?</Text>
              <Text style={styles.infoText}>1. Ingresa el monto y tu CPF</Text>
              <Text style={styles.infoText}>2. Escanea el QR Code o copia el código</Text>
              <Text style={styles.infoText}>3. Realiza el pago en tu app bancaria</Text>
              <Text style={styles.infoText}>4. Los RIS se acreditarán automáticamente</Text>
            </View>
          </View>

          {/* Generate Button */}
          <TouchableOpacity
            style={[styles.generateButton, (!amount || !cpf) && styles.generateButtonDisabled]}
            onPress={handleCreatePix}
            disabled={loading || !amount || !cpf}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="qr-code" size={20} color="#fff" />
                <Text style={styles.generateButtonText}>Generar Código PIX</Text>
              </>
            )}
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // QR Code display screen
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.backButton} onPress={() => setPixData(null)}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Pagar con PIX</Text>
          <View style={{ width: 44 }} />
        </View>

        {/* Amount Display */}
        <View style={styles.pixAmountCard}>
          <Text style={styles.pixAmountLabel}>Valor a Pagar</Text>
          <Text style={styles.pixAmountValue}>R$ {pixData.amount_brl.toFixed(2)}</Text>
          <View style={styles.pixExpirationBadge}>
            <Ionicons name="time-outline" size={14} color="#d97706" />
            <Text style={styles.pixExpirationText}>Válido por 30 minutos</Text>
          </View>
        </View>

        {/* QR Code */}
        <View style={styles.qrSection}>
          {pixData.qr_code_base64 && (
            <View style={styles.qrContainer}>
              <Image
                source={{ uri: `data:image/png;base64,${pixData.qr_code_base64}` }}
                style={styles.qrImage}
                resizeMode="contain"
              />
            </View>
          )}
          
          <TouchableOpacity style={styles.copyButton} onPress={copyPixCode}>
            <Ionicons name="copy-outline" size={20} color="#0f172a" />
            <Text style={styles.copyButtonText}>Copiar Código PIX</Text>
          </TouchableOpacity>
        </View>

        {/* Upload Proof Section */}
        <View style={styles.proofSection}>
          <Text style={styles.proofTitle}>Comprobante de Pago</Text>
          <Text style={styles.proofSubtitle}>Sube la captura de tu transferencia para acelerar la verificación</Text>
          
          {proofImage ? (
            <View style={styles.proofPreview}>
              <Image source={{ uri: proofImage }} style={styles.proofImage} />
              <TouchableOpacity style={styles.retakeButton} onPress={takeProofPhoto}>
                <Ionicons name="camera" size={18} color="#fff" />
                <Text style={styles.retakeButtonText}>Tomar otra</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity style={styles.uploadProofButton} onPress={takeProofPhoto}>
              <Ionicons name="camera-outline" size={32} color="#F5A623" />
              <Text style={styles.uploadProofText}>Tomar foto del comprobante</Text>
            </TouchableOpacity>
          )}

          {proofImage && (
            <TouchableOpacity
              style={styles.sendProofButton}
              onPress={uploadProof}
              disabled={uploadingProof}
            >
              {uploadingProof ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="cloud-upload" size={20} color="#fff" />
                  <Text style={styles.sendProofButtonText}>Enviar Comprobante</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </View>

        {/* Cancel Button */}
        <TouchableOpacity
          style={styles.cancelButton}
          onPress={handleCancelRecharge}
          disabled={cancelling}
        >
          {cancelling ? (
            <ActivityIndicator color="#dc2626" size="small" />
          ) : (
            <>
              <Ionicons name="close-circle-outline" size={18} color="#dc2626" />
              <Text style={styles.cancelButtonText}>Cancelar Recarga</Text>
            </>
          )}
        </TouchableOpacity>
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
    padding: 20,
    paddingBottom: 40,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  backButton: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  balanceCard: {
    backgroundColor: '#0f172a',
    borderRadius: 20,
    padding: 20,
    marginBottom: 24,
  },
  balanceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  balanceIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: 'rgba(245, 166, 35, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  balanceLabel: {
    fontSize: 14,
    color: '#94a3b8',
  },
  balanceAmount: {
    fontSize: 36,
    fontWeight: '800',
    color: '#fff',
  },
  balanceCurrency: {
    fontSize: 18,
    fontWeight: '600',
    color: '#F5A623',
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 10,
  },
  amountInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 2,
    borderColor: '#F5A623',
    paddingHorizontal: 16,
    height: 64,
  },
  currencyPrefix: {
    fontSize: 24,
    fontWeight: '700',
    color: '#F5A623',
    marginRight: 8,
  },
  amountInput: {
    flex: 1,
    fontSize: 28,
    fontWeight: '700',
    color: '#0f172a',
  },
  limitText: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 8,
    textAlign: 'center',
  },
  quickAmountsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 24,
  },
  quickAmountBtn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  quickAmountBtnActive: {
    backgroundColor: '#F5A623',
    borderColor: '#F5A623',
  },
  quickAmountText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#64748b',
  },
  quickAmountTextActive: {
    color: '#fff',
  },
  cpfInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#e2e8f0',
    paddingHorizontal: 14,
    height: 56,
    gap: 12,
  },
  cpfInput: {
    flex: 1,
    fontSize: 16,
    color: '#0f172a',
  },
  cpfHint: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 6,
  },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: '#e0f2fe',
    borderRadius: 14,
    padding: 16,
    gap: 12,
    marginBottom: 24,
  },
  infoContent: {
    flex: 1,
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0369a1',
    marginBottom: 8,
  },
  infoText: {
    fontSize: 13,
    color: '#0369a1',
    lineHeight: 20,
  },
  generateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 18,
    borderRadius: 16,
    gap: 10,
    shadowColor: '#F5A623',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  generateButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
  },
  generateButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#fff',
  },
  // QR Screen Styles
  pixAmountCard: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 3,
  },
  pixAmountLabel: {
    fontSize: 14,
    color: '#64748b',
    marginBottom: 4,
  },
  pixAmountValue: {
    fontSize: 40,
    fontWeight: '800',
    color: '#059669',
    marginBottom: 12,
  },
  pixExpirationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef3c7',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    gap: 6,
  },
  pixExpirationText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#d97706',
  },
  qrSection: {
    alignItems: 'center',
    marginBottom: 24,
  },
  qrContainer: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 4,
    marginBottom: 16,
  },
  qrImage: {
    width: 220,
    height: 220,
  },
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
    borderWidth: 1.5,
    borderColor: '#e2e8f0',
  },
  copyButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0f172a',
  },
  proofSection: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 20,
    marginBottom: 16,
  },
  proofTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 4,
  },
  proofSubtitle: {
    fontSize: 13,
    color: '#64748b',
    marginBottom: 16,
  },
  uploadProofButton: {
    borderWidth: 2,
    borderColor: '#F5A623',
    borderStyle: 'dashed',
    borderRadius: 14,
    padding: 24,
    alignItems: 'center',
    backgroundColor: '#fffbeb',
  },
  uploadProofText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F5A623',
    marginTop: 8,
  },
  proofPreview: {
    alignItems: 'center',
  },
  proofImage: {
    width: '100%',
    height: 180,
    borderRadius: 12,
    marginBottom: 12,
  },
  retakeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#64748b',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    gap: 8,
  },
  retakeButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
  sendProofButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
    marginTop: 16,
  },
  sendProofButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
  cancelButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
    borderWidth: 1.5,
    borderColor: '#fecaca',
  },
  cancelButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#dc2626',
  },
});
