import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
  KeyboardAvoidingView,
  ScrollView,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useFocusEffect } from '@react-navigation/native';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function ChangePasswordScreen() {
  const router = useRouter();
  const cameraRef = useRef<any>(null);
  const [permission, requestPermission] = useCameraPermissions();
  
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  const [step, setStep] = useState<'password' | 'selfie'>('password');
  const [selfieImage, setSelfieImage] = useState<string | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [loading, setLoading] = useState(false);

  // Clear all fields when screen is focused
  useFocusEffect(
    useCallback(() => {
      // Reset all states when entering the screen
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowCurrentPassword(false);
      setShowNewPassword(false);
      setShowConfirmPassword(false);
      setStep('password');
      setSelfieImage(null);
      setLivenessStep(0);
      setLoading(false);
    }, [])
  );
  
  // Liveness detection states
  const [livenessStep, setLivenessStep] = useState(0);
  const [livenessInstructions] = useState([
    'Mira directamente a la cámara',
    'Parpadea dos veces',
    'Sonríe ligeramente',
  ]);

  const validatePassword = (pass: string): string[] => {
    const errs: string[] = [];
    if (pass.length < 7) errs.push('Mínimo 7 caracteres');
    if (!/[a-zA-Z]/.test(pass)) errs.push('Debe contener letras');
    if (!/[0-9]/.test(pass)) errs.push('Debe contener números');
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(pass)) errs.push('Debe contener un símbolo');
    return errs;
  };

  const errors = validatePassword(newPassword);
  const isPasswordValid = currentPassword.length > 0 && 
                          newPassword.length >= 7 && 
                          newPassword === confirmPassword && 
                          errors.length === 0;

  const handlePasswordStep = () => {
    if (!isPasswordValid) {
      showAlert('Error', 'Verifica que todos los campos estén correctos');
      return;
    }
    setStep('selfie');
  };

  const takeSelfie = async () => {
    if (!cameraRef.current) {
      showAlert('Error', 'Cámara no disponible');
      return;
    }
    
    try {
      console.log('Taking picture...');
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
        base64: true,
        skipProcessing: true,
      });
      
      console.log('Photo taken:', photo ? 'success' : 'failed');
      
      if (photo && photo.base64) {
        const imageData = `data:image/jpeg;base64,${photo.base64}`;
        setSelfieImage(imageData);
        // Move to final step
        setLivenessStep(livenessInstructions.length - 1);
      } else if (photo && photo.uri) {
        // Fallback if base64 not available
        setSelfieImage(photo.uri);
        setLivenessStep(livenessInstructions.length - 1);
      } else {
        showAlert('Error', 'No se pudo procesar la foto');
      }
    } catch (error: any) {
      console.error('Error taking photo:', error);
      showAlert('Error', `No se pudo capturar la foto: ${error.message || 'Error desconocido'}`);
    }
  };

  const handleSubmit = async () => {
    if (!selfieImage) {
      showAlert('Error', 'Debes tomar una selfie para verificar tu identidad');
      return;
    }

    setLoading(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/auth/change-password`,
        {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
          selfie_image: selfieImage,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      showAlert('¡Listo!', 'Tu contraseña ha sido cambiada exitosamente.', [
        { text: 'OK', onPress: () => router.back() }
      ]);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo cambiar la contraseña');
    } finally {
      setLoading(false);
    }
  };

  if (step === 'selfie') {
    if (!permission?.granted) {
      return (
        <SafeAreaView style={styles.container}>
          <View style={styles.permissionContainer}>
            <Ionicons name="camera-outline" size={64} color="#9ca3af" />
            <Text style={styles.permissionTitle}>Cámara Requerida</Text>
            <Text style={styles.permissionText}>
              Necesitamos acceso a tu cámara para verificar tu identidad
            </Text>
            <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
              <Text style={styles.permissionButtonText}>Permitir Cámara</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.backLink} onPress={() => setStep('password')}>
              <Text style={styles.backLinkText}>Volver</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      );
    }

    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.selfieContainer}>
          <View style={styles.selfieHeader}>
            <TouchableOpacity onPress={() => setStep('password')} style={styles.backButton}>
              <Ionicons name="arrow-back" size={24} color="#1f2937" />
            </TouchableOpacity>
            <Text style={styles.selfieTitle}>Verificación de Identidad</Text>
            <View style={{ width: 24 }} />
          </View>

          <View style={styles.instructionBox}>
            <Ionicons name="information-circle" size={20} color="#2563eb" />
            <Text style={styles.instructionText}>
              {livenessInstructions[livenessStep]}
            </Text>
          </View>

          <View style={styles.cameraContainer}>
            {selfieImage ? (
              <Image source={{ uri: selfieImage }} style={styles.selfiePreview} />
            ) : (
              <CameraView
                ref={cameraRef}
                style={styles.camera}
                facing="front"
                onCameraReady={() => setCameraReady(true)}
              />
            )}
            <View style={styles.cameraOverlay}>
              <View style={styles.faceGuide} />
            </View>
          </View>

          <View style={styles.livenessProgress}>
            {livenessInstructions.map((_, index) => (
              <View
                key={index}
                style={[
                  styles.livenessStep,
                  index <= livenessStep && styles.livenessStepActive,
                ]}
              />
            ))}
          </View>

          {selfieImage && livenessStep === livenessInstructions.length - 1 ? (
            <View style={styles.selfieActions}>
              <TouchableOpacity
                style={styles.retakeButton}
                onPress={() => {
                  setSelfieImage(null);
                  setLivenessStep(0);
                }}
              >
                <Ionicons name="refresh" size={20} color="#6b7280" />
                <Text style={styles.retakeButtonText}>Repetir</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.confirmButton}
                onPress={handleSubmit}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="checkmark" size={20} color="#fff" />
                    <Text style={styles.confirmButtonText}>Confirmar Cambio</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.captureButton}
              onPress={takeSelfie}
              disabled={!cameraReady}
            >
              <View style={styles.captureButtonInner} />
            </TouchableOpacity>
          )}

          <Text style={styles.privacyNote}>
            Esta foto se usa solo para verificar tu identidad y se guarda de forma segura
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView 
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
              <Ionicons name="arrow-back" size={24} color="#1f2937" />
            </TouchableOpacity>
            <Text style={styles.title}>Cambiar Contraseña</Text>
            <View style={{ width: 24 }} />
          </View>

          <View style={styles.form}>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Contraseña Actual</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="key-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={currentPassword}
                  onChangeText={setCurrentPassword}
                  placeholder="Ingresa tu contraseña actual"
                  secureTextEntry={!showCurrentPassword}
                  autoCapitalize="none"
                />
                <TouchableOpacity onPress={() => setShowCurrentPassword(!showCurrentPassword)}>
                  <Ionicons 
                    name={showCurrentPassword ? 'eye-off-outline' : 'eye-outline'} 
                    size={20} 
                    color="#6b7280" 
                  />
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Nueva Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={newPassword}
                  onChangeText={setNewPassword}
                  placeholder="Ingresa tu nueva contraseña"
                  secureTextEntry={!showNewPassword}
                  autoCapitalize="none"
                />
                <TouchableOpacity onPress={() => setShowNewPassword(!showNewPassword)}>
                  <Ionicons 
                    name={showNewPassword ? 'eye-off-outline' : 'eye-outline'} 
                    size={20} 
                    color="#6b7280" 
                  />
                </TouchableOpacity>
              </View>
            </View>

            {/* Password Requirements */}
            <View style={styles.requirements}>
              <RequirementItem text="Mínimo 7 caracteres" met={newPassword.length >= 7} />
              <RequirementItem text="Al menos una letra" met={/[a-zA-Z]/.test(newPassword)} />
              <RequirementItem text="Al menos un número" met={/[0-9]/.test(newPassword)} />
              <RequirementItem text="Al menos un símbolo (!@#$%...)" met={/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(newPassword)} />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Confirmar Nueva Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={confirmPassword}
                  onChangeText={setConfirmPassword}
                  placeholder="Repite tu nueva contraseña"
                  secureTextEntry={!showConfirmPassword}
                  autoCapitalize="none"
                />
                <TouchableOpacity onPress={() => setShowConfirmPassword(!showConfirmPassword)}>
                  <Ionicons 
                    name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'} 
                    size={20} 
                    color="#6b7280" 
                  />
                </TouchableOpacity>
              </View>
              {confirmPassword.length > 0 && newPassword !== confirmPassword && (
                <Text style={styles.errorText}>Las contraseñas no coinciden</Text>
              )}
            </View>

            <TouchableOpacity
              style={[styles.submitButton, !isPasswordValid && styles.submitButtonDisabled]}
              onPress={handlePasswordStep}
              disabled={!isPasswordValid}
            >
              <Text style={styles.submitButtonText}>Continuar</Text>
              <Ionicons name="arrow-forward" size={20} color="#fff" />
            </TouchableOpacity>

            <View style={styles.selfieNote}>
              <Ionicons name="camera" size={20} color="#6b7280" />
              <Text style={styles.selfieNoteText}>
                En el siguiente paso, tomarás una selfie en vivo para verificar tu identidad
              </Text>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function RequirementItem({ text, met }: { text: string; met: boolean }) {
  return (
    <View style={styles.requirementItem}>
      <Ionicons 
        name={met ? 'checkmark-circle' : 'ellipse-outline'} 
        size={16} 
        color={met ? '#10b981' : '#9ca3af'} 
      />
      <Text style={[styles.requirementText, met && styles.requirementMet]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    padding: 24,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  backButton: {
    padding: 4,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
  },
  form: {
    gap: 20,
  },
  inputGroup: {
    gap: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    paddingHorizontal: 12,
    height: 52,
  },
  inputIcon: {
    marginRight: 10,
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: '#1f2937',
  },
  requirements: {
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  requirementItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  requirementText: {
    fontSize: 13,
    color: '#6b7280',
  },
  requirementMet: {
    color: '#10b981',
  },
  errorText: {
    fontSize: 12,
    color: '#ef4444',
    marginTop: 4,
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2563eb',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
    marginTop: 8,
  },
  submitButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  selfieNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#fef3c7',
    padding: 16,
    borderRadius: 12,
    marginTop: 8,
  },
  selfieNoteText: {
    flex: 1,
    fontSize: 13,
    color: '#92400e',
  },
  // Selfie step styles
  selfieContainer: {
    flex: 1,
    padding: 24,
  },
  selfieHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  selfieTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f2937',
  },
  instructionBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#dbeafe',
    padding: 16,
    borderRadius: 12,
    marginBottom: 24,
  },
  instructionText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
    color: '#1e40af',
  },
  cameraContainer: {
    aspectRatio: 3/4,
    backgroundColor: '#000',
    borderRadius: 24,
    overflow: 'hidden',
    position: 'relative',
  },
  camera: {
    flex: 1,
  },
  selfiePreview: {
    flex: 1,
    resizeMode: 'cover',
  },
  cameraOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  faceGuide: {
    width: 200,
    height: 260,
    borderRadius: 100,
    borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.5)',
    borderStyle: 'dashed',
  },
  livenessProgress: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    marginTop: 16,
  },
  livenessStep: {
    width: 40,
    height: 4,
    backgroundColor: '#e5e7eb',
    borderRadius: 2,
  },
  livenessStepActive: {
    backgroundColor: '#2563eb',
  },
  captureButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
    marginTop: 24,
    borderWidth: 4,
    borderColor: '#2563eb',
  },
  captureButtonInner: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#2563eb',
  },
  selfieActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 24,
  },
  retakeButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f3f4f6',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  retakeButtonText: {
    color: '#6b7280',
    fontSize: 15,
    fontWeight: '600',
  },
  confirmButton: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10b981',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  confirmButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  privacyNote: {
    fontSize: 12,
    color: '#9ca3af',
    textAlign: 'center',
    marginTop: 16,
  },
  // Permission styles
  permissionContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  permissionTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
    marginTop: 16,
  },
  permissionText: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 8,
  },
  permissionButton: {
    backgroundColor: '#2563eb',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 12,
    marginTop: 24,
  },
  permissionButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  backLink: {
    marginTop: 16,
  },
  backLinkText: {
    color: '#6b7280',
    fontSize: 14,
  },
});
