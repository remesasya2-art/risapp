import React, { useState } from 'react';
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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import axios from 'axios';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [step, setStep] = useState<'email' | 'reset'>('email');
  const [email, setEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const validatePassword = (pass: string): string[] => {
    const errs: string[] = [];
    if (pass.length < 7) {
      errs.push('Mínimo 7 caracteres');
    }
    if (!/[a-zA-Z]/.test(pass)) {
      errs.push('Debe contener letras');
    }
    if (!/[0-9]/.test(pass)) {
      errs.push('Debe contener números');
    }
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(pass)) {
      errs.push('Debe contener un símbolo (!@#$%...)');
    }
    return errs;
  };

  const handlePasswordChange = (text: string) => {
    setNewPassword(text);
    setErrors(validatePassword(text));
  };

  const handleRequestReset = async () => {
    if (!email.trim()) {
      showAlert('Error', 'Por favor ingresa tu correo electrónico');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      showAlert('Error', 'Por favor ingresa un correo electrónico válido');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${BACKEND_URL}/api/auth/request-password-reset`, {
        email: email.toLowerCase().trim()
      });

      showAlert(
        'Código Enviado',
        'Si el email está registrado, recibirás un código de recuperación. Revisa tus notificaciones en la app o tu correo.',
        [{ text: 'Continuar', onPress: () => setStep('reset') }]
      );
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar la solicitud');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!resetToken.trim()) {
      showAlert('Error', 'Por favor ingresa el código de recuperación');
      return;
    }

    if (newPassword !== confirmPassword) {
      showAlert('Error', 'Las contraseñas no coinciden');
      return;
    }

    const validationErrors = validatePassword(newPassword);
    if (validationErrors.length > 0) {
      showAlert('Error', 'La contraseña no cumple los requisitos');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${BACKEND_URL}/api/auth/reset-password`, {
        email: email.toLowerCase().trim(),
        reset_token: resetToken.trim(),
        new_password: newPassword,
        confirm_password: confirmPassword
      });

      showAlert(
        '¡Contraseña Actualizada!',
        'Tu contraseña ha sido restablecida exitosamente. Ahora puedes iniciar sesión.',
        [{ text: 'Ir a Inicio', onPress: () => router.replace('/') }]
      );
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo restablecer la contraseña');
    } finally {
      setLoading(false);
    }
  };

  const isResetValid = newPassword.length >= 7 && 
                       newPassword === confirmPassword && 
                       errors.length === 0 &&
                       resetToken.trim().length > 0;

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
          {/* Header with Back Button */}
          <View style={styles.topBar}>
            <TouchableOpacity 
              style={styles.backButton} 
              onPress={() => step === 'reset' ? setStep('email') : router.back()}
            >
              <Ionicons name="arrow-back" size={24} color="#0f172a" />
            </TouchableOpacity>
          </View>

          {step === 'email' ? (
            // Step 1: Request Reset Code
            <>
              <View style={styles.header}>
                <View style={styles.iconContainer}>
                  <Ionicons name="mail-open" size={48} color="#F5A623" />
                </View>
                <Text style={styles.title}>¿Olvidaste tu Contraseña?</Text>
                <Text style={styles.subtitle}>
                  Ingresa tu correo electrónico y te enviaremos un código de recuperación
                </Text>
              </View>

              <View style={styles.form}>
                <View style={styles.inputGroup}>
                  <Text style={styles.label}>Correo Electrónico</Text>
                  <View style={styles.inputContainer}>
                    <Ionicons name="mail-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      value={email}
                      onChangeText={setEmail}
                      placeholder="correo@ejemplo.com"
                      keyboardType="email-address"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                </View>

                <TouchableOpacity
                  style={[styles.submitButton, !email.trim() && styles.submitButtonDisabled]}
                  onPress={handleRequestReset}
                  disabled={loading || !email.trim()}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="paper-plane" size={20} color="#fff" />
                      <Text style={styles.submitButtonText}>Enviar Código</Text>
                    </>
                  )}
                </TouchableOpacity>

                {/* Info Card */}
                <View style={styles.infoCard}>
                  <Ionicons name="information-circle" size={20} color="#0369a1" />
                  <Text style={styles.infoText}>
                    El código se enviará a las notificaciones de tu cuenta y/o a tu correo electrónico si está configurado.
                  </Text>
                </View>
              </View>
            </>
          ) : (
            // Step 2: Enter Code and New Password
            <>
              <View style={styles.header}>
                <View style={[styles.iconContainer, { backgroundColor: '#ecfdf5' }]}>
                  <Ionicons name="key" size={48} color="#059669" />
                </View>
                <Text style={styles.title}>Restablecer Contraseña</Text>
                <Text style={styles.subtitle}>
                  Ingresa el código de recuperación y tu nueva contraseña
                </Text>
              </View>

              <View style={styles.form}>
                {/* Code Input */}
                <View style={styles.inputGroup}>
                  <Text style={styles.label}>Código de Recuperación</Text>
                  <View style={styles.inputContainer}>
                    <Ionicons name="keypad-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      value={resetToken}
                      onChangeText={setResetToken}
                      placeholder="Ingresa el código"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <Text style={styles.codeHint}>
                    Revisa las notificaciones en la app o tu correo
                  </Text>
                </View>

                {/* New Password */}
                <View style={styles.inputGroup}>
                  <Text style={styles.label}>Nueva Contraseña</Text>
                  <View style={styles.inputContainer}>
                    <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      value={newPassword}
                      onChangeText={handlePasswordChange}
                      placeholder="Ingresa tu nueva contraseña"
                      secureTextEntry={!showPassword}
                      autoCapitalize="none"
                    />
                    <TouchableOpacity onPress={() => setShowPassword(!showPassword)}>
                      <Ionicons 
                        name={showPassword ? 'eye-off-outline' : 'eye-outline'} 
                        size={20} 
                        color="#6b7280" 
                      />
                    </TouchableOpacity>
                  </View>
                </View>

                {/* Password Requirements */}
                <View style={styles.requirements}>
                  <Text style={styles.requirementsTitle}>Requisitos:</Text>
                  <RequirementItem text="Mínimo 7 caracteres" met={newPassword.length >= 7} />
                  <RequirementItem text="Al menos una letra" met={/[a-zA-Z]/.test(newPassword)} />
                  <RequirementItem text="Al menos un número" met={/[0-9]/.test(newPassword)} />
                  <RequirementItem text="Al menos un símbolo (!@#$%...)" met={/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(newPassword)} />
                </View>

                {/* Confirm Password */}
                <View style={styles.inputGroup}>
                  <Text style={styles.label}>Confirmar Contraseña</Text>
                  <View style={styles.inputContainer}>
                    <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      value={confirmPassword}
                      onChangeText={setConfirmPassword}
                      placeholder="Repite tu contraseña"
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
                  {confirmPassword.length > 0 && newPassword === confirmPassword && (
                    <Text style={styles.successText}>✓ Las contraseñas coinciden</Text>
                  )}
                </View>

                <TouchableOpacity
                  style={[styles.submitButton, styles.submitButtonGreen, !isResetValid && styles.submitButtonDisabled]}
                  onPress={handleResetPassword}
                  disabled={loading || !isResetValid}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle" size={20} color="#fff" />
                      <Text style={styles.submitButtonText}>Restablecer Contraseña</Text>
                    </>
                  )}
                </TouchableOpacity>

                {/* Resend Code */}
                <TouchableOpacity 
                  style={styles.resendButton}
                  onPress={handleRequestReset}
                  disabled={loading}
                >
                  <Text style={styles.resendText}>¿No recibiste el código? </Text>
                  <Text style={styles.resendLink}>Reenviar</Text>
                </TouchableOpacity>
              </View>
            </>
          )}

          {/* Back to Login */}
          <TouchableOpacity 
            style={styles.backToLogin}
            onPress={() => router.replace('/')}
          >
            <Ionicons name="arrow-back-circle" size={20} color="#64748b" />
            <Text style={styles.backToLoginText}>Volver al inicio de sesión</Text>
          </TouchableOpacity>
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
  topBar: {
    marginBottom: 16,
  },
  backButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  iconContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    color: '#0f172a',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 15,
    color: '#64748b',
    textAlign: 'center',
    marginTop: 10,
    paddingHorizontal: 20,
    lineHeight: 22,
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
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#e5e7eb',
    paddingHorizontal: 14,
    height: 56,
  },
  inputIcon: {
    marginRight: 12,
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: '#1f2937',
  },
  codeHint: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 4,
  },
  requirements: {
    backgroundColor: '#f9fafb',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  requirementsTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 12,
  },
  requirementItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
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
  successText: {
    fontSize: 12,
    color: '#10b981',
    marginTop: 4,
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
    marginTop: 8,
    shadowColor: '#F5A623',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  submitButtonGreen: {
    backgroundColor: '#059669',
    shadowColor: '#059669',
  },
  submitButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
    elevation: 0,
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#e0f2fe',
    borderRadius: 12,
    padding: 14,
    gap: 12,
    borderWidth: 1,
    borderColor: '#7dd3fc',
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    color: '#0369a1',
    lineHeight: 20,
  },
  resendButton: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 12,
  },
  resendText: {
    fontSize: 14,
    color: '#64748b',
  },
  resendLink: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
  backToLogin: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 20,
    marginTop: 16,
    gap: 8,
  },
  backToLoginText: {
    fontSize: 14,
    color: '#64748b',
    fontWeight: '500',
  },
});
