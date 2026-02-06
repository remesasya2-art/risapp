import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Image,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function VerificationScreen() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    fullName: '',
    documentNumber: '',
    cpfNumber: '',
  });
  const [idImage, setIdImage] = useState<string | null>(null);
  const [cpfImage, setCpfImage] = useState<string | null>(null);
  const [selfieImage, setSelfieImage] = useState<string | null>(null);
  const [acceptedDeclaration, setAcceptedDeclaration] = useState(false);
  const [hasSubmittedDocs, setHasSubmittedDocs] = useState(false);
  const [verifiedUserData, setVerifiedUserData] = useState<any>(null);

  useEffect(() => {
    checkVerificationStatus();
  }, [user]);

  const checkVerificationStatus = async () => {
    if (!user) return;
    
    // Si ya está verificado, cargar sus datos para mostrar
    if (user.verification_status === 'verified') {
      try {
        const token = await AsyncStorage.getItem('session_token');
        const response = await axios.get(`${BACKEND_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setVerifiedUserData(response.data);
      } catch (error) {
        console.log('Error loading user data');
      }
      return;
    }
    
    // Check if user has already submitted documents (pending review)
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/verification/status`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.data.documents_submitted) {
        setHasSubmittedDocs(true);
      }
    } catch (error) {
      console.log('Error checking verification status');
    }
  };

  // ========== PANTALLA PARA USUARIO YA VERIFICADO ==========
  if (user?.verification_status === 'verified') {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
              <Ionicons name="arrow-back" size={24} color="#0f172a" />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Mi Verificación</Text>
            <View style={{ width: 44 }} />
          </View>

          {/* Verified Status Card */}
          <View style={styles.verifiedCard}>
            <View style={styles.verifiedIconContainer}>
              <Ionicons name="shield-checkmark" size={48} color="#059669" />
            </View>
            <Text style={styles.verifiedTitle}>Cuenta Verificada</Text>
            <Text style={styles.verifiedSubtitle}>
              Tu identidad ha sido verificada exitosamente. Esta información no puede ser modificada.
            </Text>
          </View>

          {/* Verified User Data - Read Only */}
          <View style={styles.verifiedDataContainer}>
            <View style={styles.verifiedDataHeader}>
              <Ionicons name="lock-closed" size={18} color="#64748b" />
              <Text style={styles.verifiedDataTitle}>Información Verificada</Text>
            </View>

            <View style={styles.verifiedDataRow}>
              <View style={styles.verifiedDataIcon}>
                <Ionicons name="person" size={18} color="#F5A623" />
              </View>
              <View style={styles.verifiedDataContent}>
                <Text style={styles.verifiedDataLabel}>Nombre Completo</Text>
                <Text style={styles.verifiedDataValue}>{verifiedUserData?.full_name || user?.name || 'N/A'}</Text>
              </View>
            </View>

            <View style={styles.verifiedDataRow}>
              <View style={styles.verifiedDataIcon}>
                <Ionicons name="mail" size={18} color="#F5A623" />
              </View>
              <View style={styles.verifiedDataContent}>
                <Text style={styles.verifiedDataLabel}>Correo Electrónico</Text>
                <Text style={styles.verifiedDataValue}>{user?.email || 'N/A'}</Text>
              </View>
            </View>

            <View style={styles.verifiedDataRow}>
              <View style={styles.verifiedDataIcon}>
                <Ionicons name="card" size={18} color="#F5A623" />
              </View>
              <View style={styles.verifiedDataContent}>
                <Text style={styles.verifiedDataLabel}>Documento</Text>
                <Text style={styles.verifiedDataValue}>{verifiedUserData?.document_number || '••••••••'}</Text>
              </View>
            </View>

            <View style={styles.verifiedDataRow}>
              <View style={styles.verifiedDataIcon}>
                <Ionicons name="document-text" size={18} color="#F5A623" />
              </View>
              <View style={styles.verifiedDataContent}>
                <Text style={styles.verifiedDataLabel}>CPF</Text>
                <Text style={styles.verifiedDataValue}>{verifiedUserData?.cpf_number || '•••.•••.•••-••'}</Text>
              </View>
            </View>

            <View style={[styles.verifiedDataRow, { borderBottomWidth: 0 }]}>
              <View style={styles.verifiedDataIcon}>
                <Ionicons name="calendar" size={18} color="#F5A623" />
              </View>
              <View style={styles.verifiedDataContent}>
                <Text style={styles.verifiedDataLabel}>Fecha de Verificación</Text>
                <Text style={styles.verifiedDataValue}>
                  {verifiedUserData?.verified_at 
                    ? new Date(verifiedUserData.verified_at).toLocaleDateString('es', { day: '2-digit', month: 'long', year: 'numeric' })
                    : 'Verificado'}
                </Text>
              </View>
            </View>
          </View>

          {/* Info Note */}
          <View style={styles.infoNote}>
            <Ionicons name="information-circle" size={20} color="#64748b" />
            <Text style={styles.infoNoteText}>
              Si necesitas actualizar tu información, contacta a soporte.
            </Text>
          </View>

          {/* Back to Home Button */}
          <TouchableOpacity style={styles.homeButton} onPress={() => router.replace('/')}>
            <Ionicons name="home" size={20} color="#fff" />
            <Text style={styles.homeButtonText}>Volver al Inicio</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ========== PANTALLA PARA USUARIO CON DOCUMENTOS PENDIENTES DE REVISIÓN ==========
  // Solo mostrar "En Revisión" si el usuario tiene verification_status === 'pending' Y ya envió documentos
  if (user?.verification_status === 'pending' && (hasSubmittedDocs || user?.id_document_image)) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.pendingContainer}>
          <View style={styles.pendingIconContainer}>
            <Ionicons name="hourglass" size={64} color="#f59e0b" />
          </View>
          <Text style={styles.pendingTitle}>En Revisión</Text>
          <Text style={styles.pendingSubtitle}>
            Tu documentación está siendo verificada por nuestro equipo de seguridad.
          </Text>
          
          <View style={styles.pendingSteps}>
            <View style={styles.pendingStep}>
              <Ionicons name="checkmark-circle" size={24} color="#10b981" />
              <Text style={styles.pendingStepText}>Documentos recibidos</Text>
            </View>
            <View style={styles.pendingStep}>
              <ActivityIndicator size="small" color="#f59e0b" />
              <Text style={styles.pendingStepText}>Verificación en proceso</Text>
            </View>
            <View style={styles.pendingStep}>
              <Ionicons name="ellipse-outline" size={24} color="#d1d5db" />
              <Text style={[styles.pendingStepText, { color: '#9ca3af' }]}>Aprobación</Text>
            </View>
          </View>

          <Text style={styles.pendingNote}>
            Te notificaremos en cuanto tu cuenta esté verificada
          </Text>

          <TouchableOpacity style={styles.homeButton} onPress={() => router.replace('/')}>
            <Ionicons name="home" size={20} color="#fff" />
            <Text style={styles.homeButtonText}>Volver al Inicio</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const takePhoto = async (type: 'id' | 'cpf' | 'selfie') => {
    try {
      const permissionResult = await ImagePicker.requestCameraPermissionsAsync();
      
      if (!permissionResult.granted) {
        showAlert('Permiso Requerido', 'Necesitamos acceso a la cámara para verificar tu identidad.');
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        quality: 0.8,
        base64: true,
        cameraType: type === 'selfie' ? ImagePicker.CameraType.front : ImagePicker.CameraType.back,
      });

      if (!result.canceled && result.assets[0].base64) {
        const base64Image = `data:image/jpeg;base64,${result.assets[0].base64}`;
        
        if (type === 'id') setIdImage(base64Image);
        else if (type === 'cpf') setCpfImage(base64Image);
        else setSelfieImage(base64Image);
      }
    } catch (error) {
      console.error('Error taking photo:', error);
      showAlert('Error', 'No se pudo tomar la foto');
    }
  };

  const handleSubmit = async () => {
    if (!formData.fullName.trim() || !formData.documentNumber.trim() || !formData.cpfNumber.trim()) {
      showAlert('Datos Incompletos', 'Completa toda la información personal');
      return;
    }
    if (!idImage || !cpfImage || !selfieImage) {
      showAlert('Fotos Requeridas', 'Debes tomar todas las fotos solicitadas');
      return;
    }
    if (!acceptedDeclaration) {
      showAlert('Declaración', 'Debes aceptar la declaración de titularidad');
      return;
    }

    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');

      await axios.post(
        `${BACKEND_URL}/api/verification/submit`,
        {
          full_name: formData.fullName,
          document_number: formData.documentNumber,
          cpf_number: formData.cpfNumber,
          id_document_image: idImage,
          cpf_image: cpfImage,
          selfie_image: selfieImage,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      await refreshUser();
      
      showAlert(
        '✅ Verificación Enviada',
        'Tu documentación ha sido enviada. Recibirás una respuesta en minutos.',
        [{ text: 'Entendido', onPress: () => router.replace('/') }]
      );
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo enviar la verificación');
    } finally {
      setLoading(false);
    }
  };

  const canProceedStep1 = formData.fullName.trim() && formData.documentNumber.trim() && formData.cpfNumber.trim();
  const canProceedStep2 = idImage && cpfImage && selfieImage;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.backButton} onPress={() => step > 1 ? setStep(step - 1) : router.back()}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Verificación KYC</Text>
          <View style={{ width: 44 }} />
        </View>

        {/* Progress Bar */}
        <View style={styles.progressContainer}>
          {[1, 2, 3].map((s) => (
            <View key={s} style={styles.progressStep}>
              <View style={[styles.progressDot, step >= s && styles.progressDotActive]}>
                {step > s ? (
                  <Ionicons name="checkmark" size={16} color="#fff" />
                ) : (
                  <Text style={[styles.progressDotText, step >= s && styles.progressDotTextActive]}>{s}</Text>
                )}
              </View>
              <Text style={[styles.progressLabel, step >= s && styles.progressLabelActive]}>
                {s === 1 ? 'Datos' : s === 2 ? 'Documentos' : 'Confirmación'}
              </Text>
            </View>
          ))}
        </View>

        {/* Step 1: Personal Data */}
        {step === 1 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <View style={styles.stepIconContainer}>
                <Ionicons name="person" size={28} color="#F5A623" />
              </View>
              <Text style={styles.stepTitle}>Información Personal</Text>
              <Text style={styles.stepSubtitle}>Ingresa tus datos exactamente como aparecen en tu documento</Text>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Nombre Completo</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="person-outline" size={20} color="#64748b" />
                <TextInput
                  style={styles.input}
                  value={formData.fullName}
                  onChangeText={(text) => setFormData({ ...formData, fullName: text })}
                  placeholder="Ej: João Silva Santos"
                  autoCapitalize="words"
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Número de Documento (DNI/Pasaporte)</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="card-outline" size={20} color="#64748b" />
                <TextInput
                  style={styles.input}
                  value={formData.documentNumber}
                  onChangeText={(text) => setFormData({ ...formData, documentNumber: text })}
                  placeholder="Número de documento"
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>CPF</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="document-text-outline" size={20} color="#64748b" />
                <TextInput
                  style={styles.input}
                  value={formData.cpfNumber}
                  onChangeText={(text) => setFormData({ ...formData, cpfNumber: text })}
                  placeholder="000.000.000-00"
                  keyboardType="numeric"
                />
              </View>
            </View>

            <TouchableOpacity
              style={[styles.nextButton, !canProceedStep1 && styles.nextButtonDisabled]}
              onPress={() => setStep(2)}
              disabled={!canProceedStep1}
            >
              <Text style={styles.nextButtonText}>Continuar</Text>
              <Ionicons name="arrow-forward" size={20} color="#fff" />
            </TouchableOpacity>
          </View>
        )}

        {/* Step 2: Documents */}
        {step === 2 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <View style={styles.stepIconContainer}>
                <Ionicons name="camera" size={28} color="#F5A623" />
              </View>
              <Text style={styles.stepTitle}>Documentos</Text>
              <Text style={styles.stepSubtitle}>Toma fotos claras de tus documentos y un selfie</Text>
            </View>

            {/* ID Document */}
            <View style={styles.photoSection}>
              <Text style={styles.photoLabel}>📄 Documento de Identidad</Text>
              {idImage ? (
                <View style={styles.photoPreview}>
                  <Image source={{ uri: idImage }} style={styles.previewImage} />
                  <TouchableOpacity style={styles.retakeBtn} onPress={() => takePhoto('id')}>
                    <Ionicons name="refresh" size={18} color="#fff" />
                  </TouchableOpacity>
                  <View style={styles.photoCheckBadge}>
                    <Ionicons name="checkmark" size={16} color="#fff" />
                  </View>
                </View>
              ) : (
                <TouchableOpacity style={styles.photoButton} onPress={() => takePhoto('id')}>
                  <Ionicons name="camera-outline" size={32} color="#F5A623" />
                  <Text style={styles.photoButtonText}>Tomar foto del documento</Text>
                </TouchableOpacity>
              )}
            </View>

            {/* CPF Document */}
            <View style={styles.photoSection}>
              <Text style={styles.photoLabel}>📋 CPF</Text>
              {cpfImage ? (
                <View style={styles.photoPreview}>
                  <Image source={{ uri: cpfImage }} style={styles.previewImage} />
                  <TouchableOpacity style={styles.retakeBtn} onPress={() => takePhoto('cpf')}>
                    <Ionicons name="refresh" size={18} color="#fff" />
                  </TouchableOpacity>
                  <View style={styles.photoCheckBadge}>
                    <Ionicons name="checkmark" size={16} color="#fff" />
                  </View>
                </View>
              ) : (
                <TouchableOpacity style={styles.photoButton} onPress={() => takePhoto('cpf')}>
                  <Ionicons name="camera-outline" size={32} color="#F5A623" />
                  <Text style={styles.photoButtonText}>Tomar foto del CPF</Text>
                </TouchableOpacity>
              )}
            </View>

            {/* Selfie */}
            <View style={styles.photoSection}>
              <Text style={styles.photoLabel}>🤳 Selfie en Vivo</Text>
              {selfieImage ? (
                <View style={styles.photoPreview}>
                  <Image source={{ uri: selfieImage }} style={styles.previewImage} />
                  <TouchableOpacity style={styles.retakeBtn} onPress={() => takePhoto('selfie')}>
                    <Ionicons name="refresh" size={18} color="#fff" />
                  </TouchableOpacity>
                  <View style={styles.photoCheckBadge}>
                    <Ionicons name="checkmark" size={16} color="#fff" />
                  </View>
                </View>
              ) : (
                <TouchableOpacity style={[styles.photoButton, styles.selfieButton]} onPress={() => takePhoto('selfie')}>
                  <Ionicons name="camera-reverse-outline" size={40} color="#F5A623" />
                  <Text style={styles.photoButtonText}>Tomar selfie (cámara frontal)</Text>
                  <View style={styles.selfieTips}>
                    <Text style={styles.tipText}>✓ Buena iluminación</Text>
                    <Text style={styles.tipText}>✓ Sin gafas oscuras</Text>
                    <Text style={styles.tipText}>✓ Rostro visible</Text>
                  </View>
                </TouchableOpacity>
              )}
            </View>

            <TouchableOpacity
              style={[styles.nextButton, !canProceedStep2 && styles.nextButtonDisabled]}
              onPress={() => setStep(3)}
              disabled={!canProceedStep2}
            >
              <Text style={styles.nextButtonText}>Continuar</Text>
              <Ionicons name="arrow-forward" size={20} color="#fff" />
            </TouchableOpacity>
          </View>
        )}

        {/* Step 3: Declaration & Submit */}
        {step === 3 && (
          <View style={styles.stepContent}>
            <View style={styles.stepHeader}>
              <View style={styles.stepIconContainer}>
                <Ionicons name="shield-checkmark" size={28} color="#F5A623" />
              </View>
              <Text style={styles.stepTitle}>Declaración Legal</Text>
              <Text style={styles.stepSubtitle}>Lee y acepta la declaración de titularidad</Text>
            </View>

            {/* Summary */}
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Resumen de tu solicitud</Text>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Nombre:</Text>
                <Text style={styles.summaryValue}>{formData.fullName}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Documento:</Text>
                <Text style={styles.summaryValue}>{formData.documentNumber}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>CPF:</Text>
                <Text style={styles.summaryValue}>{formData.cpfNumber}</Text>
              </View>
              <View style={styles.summaryPhotos}>
                <View style={styles.summaryPhotoCheck}>
                  <Ionicons name="checkmark-circle" size={20} color="#059669" />
                  <Text style={styles.summaryPhotoText}>Documento</Text>
                </View>
                <View style={styles.summaryPhotoCheck}>
                  <Ionicons name="checkmark-circle" size={20} color="#059669" />
                  <Text style={styles.summaryPhotoText}>CPF</Text>
                </View>
                <View style={styles.summaryPhotoCheck}>
                  <Ionicons name="checkmark-circle" size={20} color="#059669" />
                  <Text style={styles.summaryPhotoText}>Selfie</Text>
                </View>
              </View>
            </View>

            {/* Declaration */}
            <View style={styles.declarationBox}>
              <Text style={styles.declarationTitle}>Declaración de Titularidad</Text>
              <Text style={styles.declarationText}>
                Declaro bajo juramento que soy el titular único de todas las tarjetas y cuentas bancarias que utilizaré en esta plataforma. Los fondos provienen de actividades lícitas.
              </Text>
              
              <TouchableOpacity
                style={styles.checkboxContainer}
                onPress={() => setAcceptedDeclaration(!acceptedDeclaration)}
              >
                <View style={[styles.checkbox, acceptedDeclaration && styles.checkboxChecked]}>
                  {acceptedDeclaration && <Ionicons name="checkmark" size={18} color="#fff" />}
                </View>
                <Text style={styles.checkboxLabel}>
                  Acepto la declaración bajo responsabilidad legal
                </Text>
              </TouchableOpacity>
            </View>

            {/* Submit Button */}
            <TouchableOpacity
              style={[styles.submitButton, (!acceptedDeclaration || loading) && styles.submitButtonDisabled]}
              onPress={handleSubmit}
              disabled={!acceptedDeclaration || loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="send" size={20} color="#fff" />
                  <Text style={styles.submitButtonText}>Enviar Verificación</Text>
                </>
              )}
            </TouchableOpacity>

            <Text style={styles.reviewTimeText}>
              ⚡ Tiempo de revisión: 5-15 minutos
            </Text>
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
  progressContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 32,
    paddingHorizontal: 20,
  },
  progressStep: {
    alignItems: 'center',
  },
  progressDot: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#e2e8f0',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  progressDotActive: {
    backgroundColor: '#F5A623',
  },
  progressDotText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#94a3b8',
  },
  progressDotTextActive: {
    color: '#fff',
  },
  progressLabel: {
    fontSize: 11,
    color: '#94a3b8',
    fontWeight: '500',
  },
  progressLabelActive: {
    color: '#F5A623',
  },
  stepContent: {
    flex: 1,
  },
  stepHeader: {
    alignItems: 'center',
    marginBottom: 28,
  },
  stepIconContainer: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  stepTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 8,
  },
  stepSubtitle: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 8,
  },
  inputContainer: {
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
  input: {
    flex: 1,
    fontSize: 16,
    color: '#0f172a',
  },
  nextButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 18,
    borderRadius: 16,
    gap: 10,
    marginTop: 24,
  },
  nextButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  nextButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#fff',
  },
  photoSection: {
    marginBottom: 20,
  },
  photoLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0f172a',
    marginBottom: 10,
  },
  photoButton: {
    borderWidth: 2,
    borderColor: '#F5A623',
    borderStyle: 'dashed',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    backgroundColor: '#fffbeb',
  },
  selfieButton: {
    padding: 32,
  },
  photoButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F5A623',
    marginTop: 8,
  },
  selfieTips: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 16,
  },
  tipText: {
    fontSize: 12,
    color: '#059669',
  },
  photoPreview: {
    position: 'relative',
  },
  previewImage: {
    width: '100%',
    height: 160,
    borderRadius: 14,
    backgroundColor: '#f1f5f9',
  },
  retakeBtn: {
    position: 'absolute',
    top: 10,
    right: 10,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  photoCheckBadge: {
    position: 'absolute',
    bottom: 10,
    right: 10,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#059669',
    justifyContent: 'center',
    alignItems: 'center',
  },
  summaryCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  summaryTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 16,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  summaryLabel: {
    fontSize: 14,
    color: '#64748b',
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#0f172a',
  },
  summaryPhotos: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  summaryPhotoCheck: {
    alignItems: 'center',
    gap: 4,
  },
  summaryPhotoText: {
    fontSize: 12,
    color: '#059669',
    fontWeight: '500',
  },
  declarationBox: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  declarationTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 12,
  },
  declarationText: {
    fontSize: 14,
    color: '#475569',
    lineHeight: 22,
    marginBottom: 20,
  },
  checkboxContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#f8fafc',
    padding: 14,
    borderRadius: 12,
  },
  checkbox: {
    width: 28,
    height: 28,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: '#d1d5db',
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxChecked: {
    backgroundColor: '#059669',
    borderColor: '#059669',
  },
  checkboxLabel: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
    color: '#374151',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    paddingVertical: 18,
    borderRadius: 16,
    gap: 10,
  },
  submitButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  submitButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#fff',
  },
  reviewTimeText: {
    fontSize: 14,
    color: '#059669',
    textAlign: 'center',
    marginTop: 16,
    fontWeight: '600',
  },

  // ========== ESTILOS PARA USUARIO VERIFICADO ==========
  verifiedCard: {
    backgroundColor: '#ecfdf5',
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#a7f3d0',
  },
  verifiedIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#d1fae5',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  verifiedTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#065f46',
    marginBottom: 8,
  },
  verifiedSubtitle: {
    fontSize: 14,
    color: '#047857',
    textAlign: 'center',
    lineHeight: 20,
  },
  verifiedDataContainer: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  verifiedDataHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  verifiedDataTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#64748b',
  },
  verifiedDataRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  verifiedDataIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#fffbeb',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  verifiedDataContent: {
    flex: 1,
  },
  verifiedDataLabel: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 2,
  },
  verifiedDataValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0f172a',
  },
  infoNote: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    padding: 14,
    gap: 10,
    marginBottom: 24,
  },
  infoNoteText: {
    flex: 1,
    fontSize: 13,
    color: '#64748b',
    lineHeight: 18,
  },
  homeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
  },
  homeButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },

  // ========== ESTILOS PARA PENDIENTE DE REVISIÓN ==========
  pendingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  pendingIconContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  pendingTitle: {
    fontSize: 26,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 12,
  },
  pendingSubtitle: {
    fontSize: 15,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
  },
  pendingSteps: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    marginBottom: 24,
    gap: 16,
  },
  pendingStep: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  pendingStepText: {
    fontSize: 15,
    color: '#374151',
    fontWeight: '500',
  },
  pendingNote: {
    fontSize: 13,
    color: '#94a3b8',
    textAlign: 'center',
    marginBottom: 32,
  },
});
