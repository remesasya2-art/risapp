import React, { useState } from 'react';
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

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function VerificationScreen() {
  const router = useRouter();
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

        {/* Declaration Section */}
        <View style={styles.declarationSection}>
          <View style={styles.declarationHeader}>
            <Ionicons name="shield-checkmark-outline" size={32} color="#ef4444" />
            <Text style={styles.declarationTitle}>DECLARACIÓN IMPORTANTE</Text>
          </View>
          
          <Text style={styles.declarationText}>
            Al continuar, declaro bajo responsabilidad legal que:
          </Text>

          <View style={styles.declarationList}>
            <View style={styles.declarationItem}>
              <Ionicons name="checkmark-circle" size={20} color="#10b981" />
              <Text style={styles.declarationItemText}>
                Las tarjetas y cuentas que usaré para recargar están <Text style={styles.bold}>A MI NOMBRE</Text>
              </Text>
            </View>

            <View style={styles.declarationItem}>
              <Ionicons name="close-circle" size={20} color="#ef4444" />
              <Text style={styles.declarationItemText}>
                <Text style={styles.bold}>NO</Text> usaré tarjetas o cuentas de otras personas (familiares, amigos, empresas)
              </Text>
            </View>

            <View style={styles.declarationItem}>
              <Ionicons name="cash-outline" size={20} color="#10b981" />
              <Text style={styles.declarationItemText}>
                Los fondos son míos y de origen lícito
              </Text>
            </View>
          </View>

          <View style={styles.warningBox}>
            <Ionicons name="warning" size={24} color="#ef4444" />
            <View style={styles.warningTextContainer}>
              <Text style={styles.warningTitle}>Si usas cuentas de terceros:</Text>
              <Text style={styles.warningText}>❌ Suspensión de cuenta</Text>
              <Text style={styles.warningText}>❌ Retención de fondos</Text>
              <Text style={styles.warningText}>❌ Reporte a autoridades</Text>
            </View>
          </View>

          <TouchableOpacity
            style={styles.checkboxContainer}
            onPress={() => setAcceptedDeclaration(!acceptedDeclaration)}
          >
            <View style={[styles.checkbox, acceptedDeclaration && styles.checkboxChecked]}>
              {acceptedDeclaration && (
                <Ionicons name="checkmark" size={20} color="#fff" />
              )}
            </View>
            <Text style={styles.checkboxLabel}>
              He leído y acepto esta declaración bajo responsabilidad legal
            </Text>
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
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    borderWidth: 2,
    borderColor: '#fecaca',
  },
  declarationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    gap: 12,
  },
  declarationTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#ef4444',
    flex: 1,
  },
  declarationText: {
    fontSize: 14,
    color: '#374151',
    marginBottom: 16,
    fontWeight: '600',
  },
  declarationList: {
    gap: 12,
    marginBottom: 16,
  },
  declarationItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  declarationItemText: {
    fontSize: 14,
    color: '#374151',
    flex: 1,
    lineHeight: 20,
  },
  bold: {
    fontWeight: '700',
    color: '#1f2937',
  },
  warningBox: {
    flexDirection: 'row',
    backgroundColor: '#fef2f2',
    padding: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#fecaca',
    marginBottom: 16,
    gap: 12,
  },
  warningTextContainer: {
    flex: 1,
  },
  warningTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#ef4444',
    marginBottom: 8,
  },
  warningText: {
    fontSize: 13,
    color: '#991b1b',
    lineHeight: 20,
  },
  checkboxContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  checkbox: {
    width: 28,
    height: 28,
    borderWidth: 2,
    borderColor: '#d1d5db',
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  checkboxChecked: {
    backgroundColor: '#10b981',
    borderColor: '#10b981',
  },
  checkboxLabel: {
    flex: 1,
    fontSize: 13,
    color: '#374151',
    lineHeight: 18,
  },
});
