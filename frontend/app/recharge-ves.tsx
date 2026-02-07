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
  Image,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import * as Clipboard from 'expo-clipboard';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

// Componente para mostrar dato copiable
const CopyableField = ({ label, value, onCopy }: { label: string; value: string; onCopy: (text: string) => void }) => (
  <View style={styles.copyableRow}>
    <View style={styles.copyableInfo}>
      <Text style={styles.bankInfoLabel}>{label}</Text>
      <Text style={styles.bankInfoValue}>{value}</Text>
    </View>
    <TouchableOpacity style={styles.copyButton} onPress={() => onCopy(value)}>
      <Ionicons name="copy-outline" size={18} color="#2563eb" />
    </TouchableOpacity>
  </View>
);

export default function RechargeVESScreen() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [step, setStep] = useState(1); // 1: amount, 2: payment method, 3: bank info, 4: upload voucher
  const [loading, setLoading] = useState(false);
  const [paymentInfo, setPaymentInfo] = useState<any>(null);
  const [rate, setRate] = useState(102);
  
  // Form data
  const [amountVES, setAmountVES] = useState('');
  const [amountRIS, setAmountRIS] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<'pago_movil' | 'transferencia' | null>(null);
  const [voucherImage, setVoucherImage] = useState<string | null>(null);

  useEffect(() => {
    loadPaymentInfo();
    loadRate();
  }, []);

  const loadPaymentInfo = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/ves-payment-info`);
      setPaymentInfo(response.data);
    } catch (error) {
      console.error('Error loading payment info:', error);
    }
  };

  const loadRate = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setRate(response.data.ves_to_ris || 102);
    } catch (error) {
      console.error('Error loading rate:', error);
    }
  };

  const handleVESChange = (value: string) => {
    setAmountVES(value);
    const ves = parseFloat(value) || 0;
    setAmountRIS((ves / rate).toFixed(2));
  };

  const handleRISChange = (value: string) => {
    setAmountRIS(value);
    const ris = parseFloat(value) || 0;
    setAmountVES((ris * rate).toFixed(2));
  };

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      quality: 0.8,
      base64: true,
    });

    if (!result.canceled && result.assets[0].base64) {
      setVoucherImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
    }
  };

  const takePhoto = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      showAlert('Permiso requerido', 'Necesitamos acceso a la cámara');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      allowsEditing: true,
      quality: 0.8,
      base64: true,
    });

    if (!result.canceled && result.assets[0].base64) {
      setVoucherImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
    }
  };

  const submitRecharge = async () => {
    if (!voucherImage) {
      showAlert('Error', 'Debes subir el comprobante de pago');
      return;
    }

    setLoading(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      
      await axios.post(
        `${BACKEND_URL}/api/recharge/ves`,
        {
          amount_ves: parseFloat(amountVES),
          amount_ris: parseFloat(amountRIS),
          payment_method: paymentMethod,
          voucher_image: voucherImage,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      showAlert(
        '✅ Solicitud Enviada',
        'Tu recarga está siendo procesada. Te notificaremos cuando sea aprobada.',
        [{ text: 'OK', onPress: () => router.replace('/') }]
      );
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'Error al procesar la recarga');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await Clipboard.setStringAsync(text);
      showAlert('✅ Copiado', `"${text}" copiado al portapapeles`);
    } catch (error) {
      console.error('Error copying:', error);
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color="#F5A623" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Recargar con Bolívares</Text>
          <View style={{ width: 44 }} />
        </View>

        {/* Progress Steps */}
        <View style={styles.progressContainer}>
          {[1, 2, 3, 4].map((s) => (
            <View key={s} style={styles.progressStep}>
              <View style={[styles.progressDot, step >= s && styles.progressDotActive]}>
                {step > s ? (
                  <Ionicons name="checkmark" size={14} color="#fff" />
                ) : (
                  <Text style={[styles.progressDotText, step >= s && styles.progressDotTextActive]}>{s}</Text>
                )}
              </View>
              {s < 4 && <View style={[styles.progressLine, step > s && styles.progressLineActive]} />}
            </View>
          ))}
        </View>

        {/* Step 1: Amount */}
        {step === 1 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <Ionicons name="calculator" size={28} color="#F5A623" />
              <Text style={styles.stepTitle}>¿Cuánto deseas recargar?</Text>
            </View>

            <View style={styles.rateCard}>
              <Text style={styles.rateLabel}>Tasa del día</Text>
              <Text style={styles.rateValue}>{rate} VES = 1 RIS</Text>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Monto en Bolívares (VES)</Text>
              <TextInput
                style={styles.input}
                value={amountVES}
                onChangeText={handleVESChange}
                keyboardType="numeric"
                placeholder="0.00"
                placeholderTextColor="#9ca3af"
              />
            </View>

            <View style={styles.convertArrow}>
              <Ionicons name="arrow-down" size={24} color="#F5A623" />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Recibirás en RIS</Text>
              <TextInput
                style={[styles.input, styles.inputHighlight]}
                value={amountRIS}
                onChangeText={handleRISChange}
                keyboardType="numeric"
                placeholder="0.00"
                placeholderTextColor="#9ca3af"
              />
            </View>

            <TouchableOpacity
              style={[styles.continueBtn, (!amountVES || parseFloat(amountVES) <= 0) && styles.btnDisabled]}
              onPress={() => setStep(2)}
              disabled={!amountVES || parseFloat(amountVES) <= 0}
            >
              <Text style={styles.continueBtnText}>Continuar</Text>
              <Ionicons name="arrow-forward" size={20} color="#fff" />
            </TouchableOpacity>
          </View>
        )}

        {/* Step 2: Payment Method */}
        {step === 2 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <Ionicons name="card" size={28} color="#F5A623" />
              <Text style={styles.stepTitle}>Método de Pago</Text>
            </View>

            <Text style={styles.stepSubtitle}>Selecciona cómo realizarás el pago</Text>

            <TouchableOpacity
              style={[styles.paymentOption, paymentMethod === 'pago_movil' && styles.paymentOptionActive]}
              onPress={() => setPaymentMethod('pago_movil')}
            >
              <View style={styles.paymentOptionIcon}>
                <Ionicons name="phone-portrait" size={28} color={paymentMethod === 'pago_movil' ? '#F5A623' : '#64748b'} />
              </View>
              <View style={styles.paymentOptionContent}>
                <Text style={[styles.paymentOptionTitle, paymentMethod === 'pago_movil' && styles.paymentOptionTitleActive]}>
                  Pago Móvil
                </Text>
                <Text style={styles.paymentOptionDesc}>Rápido y sencillo desde tu banco</Text>
              </View>
              {paymentMethod === 'pago_movil' && (
                <Ionicons name="checkmark-circle" size={24} color="#F5A623" />
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.paymentOption, paymentMethod === 'transferencia' && styles.paymentOptionActive]}
              onPress={() => setPaymentMethod('transferencia')}
            >
              <View style={styles.paymentOptionIcon}>
                <Ionicons name="business" size={28} color={paymentMethod === 'transferencia' ? '#F5A623' : '#64748b'} />
              </View>
              <View style={styles.paymentOptionContent}>
                <Text style={[styles.paymentOptionTitle, paymentMethod === 'transferencia' && styles.paymentOptionTitleActive]}>
                  Transferencia Bancaria
                </Text>
                <Text style={styles.paymentOptionDesc}>Desde cualquier banco venezolano</Text>
              </View>
              {paymentMethod === 'transferencia' && (
                <Ionicons name="checkmark-circle" size={24} color="#F5A623" />
              )}
            </TouchableOpacity>

            <View style={styles.btnRow}>
              <TouchableOpacity style={styles.backStepBtn} onPress={() => setStep(1)}>
                <Ionicons name="arrow-back" size={20} color="#64748b" />
                <Text style={styles.backStepBtnText}>Atrás</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.continueBtn, !paymentMethod && styles.btnDisabled]}
                onPress={() => setStep(3)}
                disabled={!paymentMethod}
              >
                <Text style={styles.continueBtnText}>Continuar</Text>
                <Ionicons name="arrow-forward" size={20} color="#fff" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Step 3: Bank Info */}
        {step === 3 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <Ionicons name="information-circle" size={28} color="#F5A623" />
              <Text style={styles.stepTitle}>Datos para {paymentMethod === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}</Text>
            </View>

            <View style={styles.amountSummary}>
              <Text style={styles.amountSummaryLabel}>Monto a pagar:</Text>
              <Text style={styles.amountSummaryValue}>{parseFloat(amountVES).toLocaleString()} VES</Text>
            </View>

            <View style={styles.bankInfoCard}>
              {paymentMethod === 'pago_movil' ? (
                <>
                  <CopyableField 
                    label="Teléfono" 
                    value={paymentInfo?.pago_movil_phone || '04249311288'} 
                    onCopy={copyToClipboard} 
                  />
                  <CopyableField 
                    label="Cédula" 
                    value={paymentInfo?.id_document || 'V-24560778'} 
                    onCopy={copyToClipboard} 
                  />
                  <View style={styles.bankInfoRow}>
                    <Text style={styles.bankInfoLabel}>Banco</Text>
                    <Text style={styles.bankInfoValue}>{paymentInfo?.pago_movil_bank_code || '0102'} - {paymentInfo?.pago_movil_bank || 'Banco de Venezuela'}</Text>
                  </View>
                </>
              ) : (
                <>
                  <View style={styles.bankInfoRow}>
                    <Text style={styles.bankInfoLabel}>Banco</Text>
                    <Text style={styles.bankInfoValue}>{paymentInfo?.bank_name || 'Banesco'}</Text>
                  </View>
                  <View style={styles.bankInfoRow}>
                    <Text style={styles.bankInfoLabel}>Titular</Text>
                    <Text style={styles.bankInfoValue}>{paymentInfo?.account_holder || 'RIS REMESAS'}</Text>
                  </View>
                  <View style={styles.bankInfoRow}>
                    <Text style={styles.bankInfoLabel}>Tipo de Cuenta</Text>
                    <Text style={styles.bankInfoValue}>{paymentInfo?.account_type || 'Corriente'}</Text>
                  </View>
                  <CopyableField 
                    label="Número de Cuenta" 
                    value={paymentInfo?.account_number || '01340869688691034659'} 
                    onCopy={copyToClipboard} 
                  />
                  <CopyableField 
                    label="Cédula" 
                    value={paymentInfo?.id_document || 'V-24560778'} 
                    onCopy={copyToClipboard} 
                  />
                </>
              )}
            </View>

            <View style={styles.warningBox}>
              <Ionicons name="warning" size={20} color="#d97706" />
              <Text style={styles.warningText}>
                Realiza el pago exacto de {parseFloat(amountVES).toLocaleString()} VES y guarda el comprobante
              </Text>
            </View>

            <View style={styles.btnRow}>
              <TouchableOpacity style={styles.backStepBtn} onPress={() => setStep(2)}>
                <Ionicons name="arrow-back" size={20} color="#64748b" />
                <Text style={styles.backStepBtnText}>Atrás</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.continueBtn} onPress={() => setStep(4)}>
                <Text style={styles.continueBtnText}>Ya realicé el pago</Text>
                <Ionicons name="arrow-forward" size={20} color="#fff" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Step 4: Upload Voucher */}
        {step === 4 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <Ionicons name="cloud-upload" size={28} color="#F5A623" />
              <Text style={styles.stepTitle}>Subir Comprobante</Text>
            </View>

            <Text style={styles.uploadLabel}>Comprobante de Pago</Text>
            
            {voucherImage ? (
              <View style={styles.voucherPreview}>
                <Image source={{ uri: voucherImage }} style={styles.voucherImage} />
                <TouchableOpacity style={styles.removeVoucherBtn} onPress={() => setVoucherImage(null)}>
                  <Ionicons name="close-circle" size={28} color="#dc2626" />
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.uploadOptions}>
                <TouchableOpacity style={styles.uploadOption} onPress={takePhoto}>
                  <Ionicons name="camera" size={32} color="#F5A623" />
                  <Text style={styles.uploadOptionText}>Tomar Foto</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.uploadOption} onPress={pickImage}>
                  <Ionicons name="images" size={32} color="#F5A623" />
                  <Text style={styles.uploadOptionText}>Galería</Text>
                </TouchableOpacity>
              </View>
            )}

            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Resumen de Recarga</Text>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Monto pagado:</Text>
                <Text style={styles.summaryValue}>{parseFloat(amountVES).toLocaleString()} VES</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Recibirás:</Text>
                <Text style={[styles.summaryValue, { color: '#059669' }]}>{parseFloat(amountRIS).toFixed(2)} RIS</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Método:</Text>
                <Text style={styles.summaryValue}>{paymentMethod === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}</Text>
              </View>
            </View>

            <View style={styles.btnRow}>
              <TouchableOpacity style={styles.backStepBtn} onPress={() => setStep(3)}>
                <Ionicons name="arrow-back" size={20} color="#64748b" />
                <Text style={styles.backStepBtnText}>Atrás</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.submitBtn, (loading || !voucherImage) && styles.btnDisabled]}
                onPress={submitRecharge}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="checkmark-circle" size={20} color="#fff" />
                    <Text style={styles.submitBtnText}>Enviar Solicitud</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}
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
  backBtn: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  
  // Progress
  progressContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  progressStep: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  progressDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#e2e8f0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  progressDotActive: {
    backgroundColor: '#F5A623',
  },
  progressDotText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94a3b8',
  },
  progressDotTextActive: {
    color: '#fff',
  },
  progressLine: {
    width: 40,
    height: 3,
    backgroundColor: '#e2e8f0',
    marginHorizontal: 4,
  },
  progressLineActive: {
    backgroundColor: '#F5A623',
  },
  
  // Step Content
  stepContent: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 24,
  },
  stepHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 20,
  },
  stepTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  stepSubtitle: {
    fontSize: 14,
    color: '#64748b',
    marginBottom: 20,
  },
  
  // Rate Card
  rateCard: {
    backgroundColor: '#fffbeb',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#fef3c7',
  },
  rateLabel: {
    fontSize: 12,
    color: '#92400e',
    marginBottom: 4,
  },
  rateValue: {
    fontSize: 20,
    fontWeight: '700',
    color: '#F5A623',
  },
  
  // Input
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#f8fafc',
    borderWidth: 2,
    borderColor: '#e2e8f0',
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    fontSize: 18,
    fontWeight: '600',
    color: '#0f172a',
  },
  inputHighlight: {
    borderColor: '#F5A623',
    backgroundColor: '#fffbeb',
  },
  convertArrow: {
    alignItems: 'center',
    marginVertical: 8,
  },
  
  // Payment Options
  paymentOption: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  paymentOptionActive: {
    borderColor: '#F5A623',
    backgroundColor: '#fffbeb',
  },
  paymentOptionIcon: {
    width: 50,
    height: 50,
    borderRadius: 12,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  paymentOptionContent: {
    flex: 1,
  },
  paymentOptionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#0f172a',
  },
  paymentOptionTitleActive: {
    color: '#92400e',
  },
  paymentOptionDesc: {
    fontSize: 13,
    color: '#64748b',
    marginTop: 2,
  },
  
  // Bank Info
  amountSummary: {
    backgroundColor: '#ecfdf5',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    alignItems: 'center',
  },
  amountSummaryLabel: {
    fontSize: 12,
    color: '#059669',
  },
  amountSummaryValue: {
    fontSize: 24,
    fontWeight: '700',
    color: '#059669',
  },
  bankInfoCard: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  bankInfoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  bankInfoLabel: {
    fontSize: 13,
    color: '#64748b',
  },
  bankInfoValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0f172a',
  },
  warningBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fffbeb',
    borderRadius: 10,
    padding: 12,
    gap: 10,
    marginBottom: 20,
  },
  warningText: {
    flex: 1,
    fontSize: 13,
    color: '#92400e',
    lineHeight: 18,
  },
  
  // Upload
  uploadLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 12,
  },
  uploadOptions: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  uploadOption: {
    flex: 1,
    backgroundColor: '#fffbeb',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#F5A623',
    borderStyle: 'dashed',
  },
  uploadOptionText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#92400e',
    marginTop: 8,
  },
  voucherPreview: {
    position: 'relative',
    marginBottom: 20,
  },
  voucherImage: {
    width: '100%',
    height: 200,
    borderRadius: 12,
  },
  removeVoucherBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: '#fff',
    borderRadius: 14,
  },
  
  // Summary
  summaryCard: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  summaryTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0f172a',
    marginBottom: 12,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  summaryLabel: {
    fontSize: 13,
    color: '#64748b',
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0f172a',
  },
  
  // Buttons
  btnRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  backStepBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f1f5f9',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 6,
  },
  backStepBtnText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#64748b',
  },
  continueBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  continueBtnText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
  },
  submitBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  submitBtnText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
  },
  btnDisabled: {
    opacity: 0.5,
  },
  
  // Copyable Fields
  copyableRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  copyableInfo: {
    flex: 1,
  },
  copyButton: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 12,
  },
});
