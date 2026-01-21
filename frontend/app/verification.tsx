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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function VerificationScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    fullName: '',
    documentNumber: '',
    cpfNumber: '',
  });
  const [idImage, setIdImage] = useState<string | null>(null);
  const [cpfImage, setCpfImage] = useState<string | null>(null);
  const [selfieImage, setSelfieImage] = useState<string | null>(null);
  const [acceptedDeclaration, setAcceptedDeclaration] = useState(false);

  // Redirect if already verified or pending
  useEffect(() => {
    if (user?.verification_status === 'verified') {
      Alert.alert(
        'Ya Verificado',
        'Tu cuenta ya está verificada. No necesitas completar este proceso nuevamente.',
        [{ text: 'OK', onPress: () => router.replace('/') }]
      );
    } else if (user?.verification_status === 'pending') {
      Alert.alert(
        'Verificación Pendiente',
        'Ya has enviado tu documentación. Estamos revisándola.',
        [{ text: 'OK', onPress: () => router.replace('/') }]
      );
    }
  }, [user]);

  const takePhoto = async (type: 'id' | 'cpf' | 'selfie') => {
    try {
      // Request camera permissions
      const permissionResult = await ImagePicker.requestCameraPermissionsAsync();
      
      if (!permissionResult.granted) {
        Alert.alert(
          'Permiso requerido', 
          'Necesitamos acceso a tu cámara para verificar tu identidad. Ve a Configuración → RIS → Cámara y activa el permiso.'
        );
        return;
      }

      // Launch camera with specific settings
      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        quality: 0.8,
        base64: true,
        cameraType: type === 'selfie' ? ImagePicker.CameraType.front : ImagePicker.CameraType.back,
      });

      if (!result.canceled && result.assets[0].base64) {
        const base64Image = `data:image/jpeg;base64,${result.assets[0].base64}`;
        
        if (type === 'id') {
          setIdImage(base64Image);
        } else if (type === 'cpf') {
          setCpfImage(base64Image);
        } else {
          setSelfieImage(base64Image);
        }
      }
    } catch (error) {
      console.error('Error taking photo:', error);
      Alert.alert('Error', 'No se pudo tomar la foto. Intenta nuevamente.');
    }
  };

  const handleSubmit = async () => {
    // Validation
    if (!formData.fullName.trim()) {
      Alert.alert('Error', 'Por favor ingresa tu nombre completo');
      return;
    }
    if (!formData.documentNumber.trim()) {
      Alert.alert('Error', 'Por favor ingresa tu número de documento');
      return;
    }
    if (!formData.cpfNumber.trim()) {
      Alert.alert('Error', 'Por favor ingresa tu número de CPF');
      return;
    }
    if (!idImage) {
      Alert.alert('Error', 'Por favor toma una foto de tu documento de identidad');
      return;
    }
    if (!cpfImage) {
      Alert.alert('Error', 'Por favor toma una foto de tu CPF');
      return;
    }
    if (!selfieImage) {
      Alert.alert('Error', 'Por favor toma un selfie en vivo desde la cámara frontal');
      return;
    }
    if (!acceptedDeclaration) {
      Alert.alert('Error', 'Debes aceptar la declaración de titularidad para continuar');
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
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      Alert.alert(
        'Verificación enviada',
        'Tu documentación ha sido enviada exitosamente. El equipo la revisará pronto.',
        [{ text: 'OK', onPress: () => router.replace('/') }]
      );
    } catch (error: any) {
      console.error('Verification error:', error);
      Alert.alert('Error', error.response?.data?.detail || 'No se pudo enviar la verificación');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.header}>
          <Ionicons name="shield-checkmark" size={60} color="#2563eb" />
          <Text style={styles.title}>Verificación de Cuenta</Text>
          <Text style={styles.subtitle}>
            Para tu seguridad, necesitamos verificar tu identidad
          </Text>
        </View>

        {/* Personal Information */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Información Personal</Text>
          
          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Nombre Completo *</Text>
            <TextInput
              style={styles.input}
              value={formData.fullName}
              onChangeText={(text) => setFormData({ ...formData, fullName: text })}
              placeholder="Ej: João Silva Santos"
              autoCapitalize="words"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Número de Documento *</Text>
            <TextInput
              style={styles.input}
              value={formData.documentNumber}
              onChangeText={(text) => setFormData({ ...formData, documentNumber: text })}
              placeholder="DNI o Pasaporte"
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Número de CPF *</Text>
            <TextInput
              style={styles.input}
              value={formData.cpfNumber}
              onChangeText={(text) => setFormData({ ...formData, cpfNumber: text })}
              placeholder="000.000.000-00"
              keyboardType="numeric"
            />
          </View>
        </View>

        {/* ID Document */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Documento de Identidad *</Text>
          <Text style={styles.sectionSubtitle}>DNI o Pasaporte vigente</Text>
          
          {idImage ? (
            <View style={styles.imagePreview}>
              <Image source={{ uri: idImage }} style={styles.previewImage} />
              <TouchableOpacity
                style={styles.changeImageButton}
                onPress={() => takePhoto('id')}
              >
                <Ionicons name="camera" size={20} color="#fff" />
                <Text style={styles.changeImageText}>Tomar nueva foto</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.uploadButton}
              onPress={() => takePhoto('id')}
            >
              <Ionicons name="camera-outline" size={40} color="#2563eb" />
              <Text style={styles.uploadButtonText}>Tomar foto con cámara</Text>
              <Text style={styles.uploadButtonSubtext}>📸 Foto en vivo requerida</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* CPF Document */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>CPF *</Text>
          <Text style={styles.sectionSubtitle}>Documento CPF vigente</Text>
          
          {cpfImage ? (
            <View style={styles.imagePreview}>
              <Image source={{ uri: cpfImage }} style={styles.previewImage} />
              <TouchableOpacity
                style={styles.changeImageButton}
                onPress={() => takePhoto('cpf')}
              >
                <Ionicons name="camera" size={20} color="#fff" />
                <Text style={styles.changeImageText}>Tomar nueva foto</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.uploadButton}
              onPress={() => takePhoto('cpf')}
            >
              <Ionicons name="camera-outline" size={40} color="#2563eb" />
              <Text style={styles.uploadButtonText}>Tomar foto con cámara</Text>
              <Text style={styles.uploadButtonSubtext}>Foto en vivo requerida</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Selfie */}
        <View style={styles.section}>
          <View style={styles.selfieHeader}>
            <Ionicons name="person-circle" size={32} color="#2563eb" />
            <View style={styles.selfieHeaderText}>
              <Text style={styles.sectionTitle}>Selfie en Vivo *</Text>
              <Text style={styles.sectionSubtitle}>Cámara frontal - Asegúrate de estar bien iluminado</Text>
            </View>
          </View>
          
          {selfieImage ? (
            <View style={styles.imagePreview}>
              <Image source={{ uri: selfieImage }} style={styles.previewImage} />
              <TouchableOpacity
                style={styles.changeImageButton}
                onPress={() => takePhoto('selfie')}
              >
                <Ionicons name="camera" size={20} color="#fff" />
                <Text style={styles.changeImageText}>Tomar nuevo selfie</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={[styles.uploadButton, styles.selfieButton]}
              onPress={() => takePhoto('selfie')}
            >
              <Ionicons name="camera-reverse-outline" size={50} color="#2563eb" />
              <Text style={styles.uploadButtonText}>Tomar selfie con cámara frontal</Text>
              <Text style={styles.uploadButtonSubtext}>📸 Foto en vivo requerida</Text>
              <View style={styles.selfieTips}>
                <Text style={styles.selfieTipText}>✓ Buena iluminación</Text>
                <Text style={styles.selfieTipText}>✓ Rostro visible</Text>
                <Text style={styles.selfieTipText}>✓ Sin gafas oscuras</Text>
              </View>
            </TouchableOpacity>
          )}
        </View>

        {/* Declaration Section - Professional Design */}
        <View style={styles.declarationSection}>
          <View style={styles.declarationHeaderPro}>
            <View style={styles.declarationIconContainer}>
              <Ionicons name="document-text" size={28} color="#2563eb" />
            </View>
            <Text style={styles.declarationTitlePro}>Declaración de Titularidad</Text>
          </View>
          
          <View style={styles.declarationDivider} />

          <Text style={styles.declarationIntro}>
            Al aceptar esta declaración, yo <Text style={styles.boldText}>{formData.fullName || '[Tu nombre]'}</Text>, declaro bajo juramento que:
          </Text>

          <View style={styles.declarationPoints}>
            <View style={styles.pointRow}>
              <View style={styles.pointNumber}>
                <Text style={styles.pointNumberText}>1</Text>
              </View>
              <Text style={styles.pointText}>
                Soy el <Text style={styles.boldText}>titular único y exclusivo</Text> de todas las tarjetas de crédito/débito y cuentas bancarias que utilizaré para realizar recargas en la plataforma RIS.
              </Text>
            </View>

            <View style={styles.pointRow}>
              <View style={styles.pointNumber}>
                <Text style={styles.pointNumberText}>2</Text>
              </View>
              <Text style={styles.pointText}>
                Los fondos utilizados para las recargas provienen de <Text style={styles.boldText}>actividades lícitas</Text> y son de mi completa propiedad.
              </Text>
            </View>

            <View style={styles.pointRow}>
              <View style={styles.pointNumber}>
                <Text style={styles.pointNumberText}>3</Text>
              </View>
              <Text style={styles.pointText}>
                <Text style={styles.boldText}>No utilizaré</Text> tarjetas, cuentas o métodos de pago pertenecientes a terceras personas, incluyendo familiares, amigos o entidades corporativas.
              </Text>
            </View>

            <View style={styles.pointRow}>
              <View style={styles.pointNumber}>
                <Text style={styles.pointNumberText}>4</Text>
              </View>
              <Text style={styles.pointText}>
                Autorizo a RIS a verificar la titularidad de mis métodos de pago y acepto que las transacciones que no cumplan con esta declaración serán rechazadas.
              </Text>
            </View>
          </View>

          <View style={styles.consequencesBox}>
            <View style={styles.consequencesHeader}>
              <Ionicons name="alert-circle" size={24} color="#dc2626" />
              <Text style={styles.consequencesTitle}>Consecuencias por Incumplimiento</Text>
            </View>
            <View style={styles.consequencesList}>
              <View style={styles.consequenceItem}>
                <Ionicons name="close-circle" size={16} color="#dc2626" />
                <Text style={styles.consequenceText}>Suspensión inmediata de la cuenta</Text>
              </View>
              <View style={styles.consequenceItem}>
                <Ionicons name="close-circle" size={16} color="#dc2626" />
                <Text style={styles.consequenceText}>Retención de fondos para investigación</Text>
              </View>
              <View style={styles.consequenceItem}>
                <Ionicons name="close-circle" size={16} color="#dc2626" />
                <Text style={styles.consequenceText}>Reporte a autoridades competentes</Text>
              </View>
            </View>
          </View>

          <View style={styles.declarationDivider} />

          <TouchableOpacity
            style={styles.checkboxContainerPro}
            onPress={() => setAcceptedDeclaration(!acceptedDeclaration)}
          >
            <View style={[styles.checkboxPro, acceptedDeclaration && styles.checkboxCheckedPro]}>
              {acceptedDeclaration && (
                <Ionicons name="checkmark" size={24} color="#fff" />
              )}
            </View>
            <View style={styles.checkboxTextContainer}>
              <Text style={styles.checkboxLabelPro}>
                He leído, comprendido y acepto esta declaración bajo responsabilidad legal
              </Text>
              <Text style={styles.checkboxSubtext}>
                Al marcar esta casilla, confirmo que toda la información proporcionada es verdadera y verificable.
              </Text>
            </View>
          </TouchableOpacity>
        </View>

        {/* Submit Button */}
        <TouchableOpacity
          style={[styles.submitButton, loading && styles.submitButtonDisabled]}
          onPress={handleSubmit}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={24} color="#fff" />
              <Text style={styles.submitButtonText}>Enviar Verificación</Text>
            </>
          )}
        </TouchableOpacity>

        <Text style={styles.disclaimer}>
          * Campos obligatorios. Tus documentos serán revisados por nuestro equipo en un máximo de 24 horas.
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
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1f2937',
    marginTop: 16,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
  },
  section: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 12,
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
  uploadButton: {
    borderWidth: 2,
    borderColor: '#2563eb',
    borderStyle: 'dashed',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    backgroundColor: '#eff6ff',
  },
  uploadButtonText: {
    fontSize: 14,
    color: '#2563eb',
    fontWeight: '600',
    marginTop: 8,
  },
  uploadButtonSubtext: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 4,
  },
  selfieButton: {
    paddingVertical: 40,
  },
  selfieHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16,
  },
  selfieHeaderText: {
    flex: 1,
  },
  selfieTips: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    width: '100%',
    gap: 4,
  },
  selfieTipText: {
    fontSize: 12,
    color: '#059669',
    fontWeight: '500',
  },
  imagePreview: {
    alignItems: 'center',
  },
  previewImage: {
    width: '100%',
    height: 200,
    borderRadius: 12,
    resizeMode: 'contain',
    backgroundColor: '#f3f4f6',
  },
  changeImageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2563eb',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    marginTop: 12,
    gap: 8,
  },
  changeImageText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10b981',
    padding: 16,
    borderRadius: 12,
    marginTop: 8,
    gap: 8,
  },
  submitButtonDisabled: {
    backgroundColor: '#9ca3af',
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  disclaimer: {
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 16,
    lineHeight: 18,
  },
  declarationSection: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  declarationHeaderPro: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
    gap: 12,
  },
  declarationIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  declarationTitlePro: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
    flex: 1,
  },
  declarationDivider: {
    height: 1,
    backgroundColor: '#e5e7eb',
    marginVertical: 20,
  },
  declarationIntro: {
    fontSize: 15,
    color: '#374151',
    lineHeight: 22,
    marginBottom: 20,
  },
  boldText: {
    fontWeight: '700',
    color: '#1f2937',
  },
  declarationPoints: {
    gap: 16,
    marginBottom: 20,
  },
  pointRow: {
    flexDirection: 'row',
    gap: 12,
  },
  pointNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pointNumberText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  pointText: {
    flex: 1,
    fontSize: 14,
    color: '#374151',
    lineHeight: 21,
  },
  consequencesBox: {
    backgroundColor: '#fef2f2',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#fecaca',
    marginBottom: 20,
  },
  consequencesHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  consequencesTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#dc2626',
  },
  consequencesList: {
    gap: 8,
  },
  consequenceItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  consequenceText: {
    fontSize: 13,
    color: '#991b1b',
    flex: 1,
  },
  checkboxContainerPro: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    backgroundColor: '#f9fafb',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  checkboxPro: {
    width: 32,
    height: 32,
    borderWidth: 2,
    borderColor: '#d1d5db',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  checkboxCheckedPro: {
    backgroundColor: '#10b981',
    borderColor: '#10b981',
  },
  checkboxTextContainer: {
    flex: 1,
  },
  checkboxLabelPro: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
    lineHeight: 20,
    marginBottom: 4,
  },
  checkboxSubtext: {
    fontSize: 12,
    color: '#6b7280',
    lineHeight: 18,
  },
});
