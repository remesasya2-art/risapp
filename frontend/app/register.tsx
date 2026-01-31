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
import AsyncStorage from '@react-native-async-storage/async-storage';
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

export default function RegisterScreen() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const validatePassword = (pass: string): string[] => {
    const errs: string[] = [];
    if (pass.length < 7) errs.push('Mínimo 7 caracteres');
    if (!/[a-zA-Z]/.test(pass)) errs.push('Debe contener letras');
    if (!/[0-9]/.test(pass)) errs.push('Debe contener números');
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(pass)) errs.push('Debe contener un símbolo');
    return errs;
  };

  const handlePasswordChange = (text: string) => {
    setPassword(text);
    setErrors(validatePassword(text));
  };

  const validateEmail = (email: string) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  };

  const handleRegister = async () => {
    // Validations
    if (!name.trim() || name.trim().length < 2) {
      showAlert('Error', 'Ingresa tu nombre completo');
      return;
    }

    if (!email.trim() || !validateEmail(email)) {
      showAlert('Error', 'Ingresa un email válido');
      return;
    }

    if (password !== confirmPassword) {
      showAlert('Error', 'Las contraseñas no coinciden');
      return;
    }

    const validationErrors = validatePassword(password);
    if (validationErrors.length > 0) {
      showAlert('Error', 'La contraseña no cumple los requisitos');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${BACKEND_URL}/api/auth/register`, {
        name: name.trim(),
        email: email.toLowerCase().trim(),
        password,
        confirm_password: confirmPassword,
        phone: phone.trim() || null
      });

      // Navigate to verify email screen
      router.push({
        pathname: '/verify-email',
        params: { email: email.toLowerCase().trim() }
      });
      await refreshUser();

      showAlert('¡Registro Exitoso!', 'Tu cuenta ha sido creada. Bienvenido a RIS.', [
        { text: 'Continuar', onPress: () => router.replace('/') }
      ]);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo completar el registro');
    } finally {
      setLoading(false);
    }
  };

  const isValid = name.trim().length >= 2 && 
                  validateEmail(email) &&
                  password.length >= 7 && 
                  password === confirmPassword && 
                  errors.length === 0;

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
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity 
              style={styles.backButton} 
              onPress={() => router.back()}
            >
              <Ionicons name="arrow-back" size={24} color="#0f172a" />
            </TouchableOpacity>
          </View>

          {/* Title */}
          <View style={styles.titleSection}>
            <View style={styles.iconContainer}>
              <Ionicons name="person-add" size={40} color="#F5A623" />
            </View>
            <Text style={styles.title}>Crear Cuenta</Text>
            <Text style={styles.subtitle}>
              Regístrate para comenzar a usar RIS
            </Text>
          </View>

          {/* Form */}
          <View style={styles.form}>
            {/* Name */}
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Nombre Completo</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="person-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={name}
                  onChangeText={setName}
                  placeholder="Ej: Juan Pérez"
                  autoCapitalize="words"
                />
              </View>
            </View>

            {/* Email */}
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
              {email.length > 0 && !validateEmail(email) && (
                <Text style={styles.errorText}>Email inválido</Text>
              )}
            </View>

            {/* Phone (Optional) */}
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Teléfono <Text style={styles.optionalLabel}>(opcional)</Text></Text>
              <View style={styles.inputContainer}>
                <Ionicons name="call-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={phone}
                  onChangeText={setPhone}
                  placeholder="+55 11 99999-9999"
                  keyboardType="phone-pad"
                />
              </View>
            </View>

            {/* Password */}
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={password}
                  onChangeText={handlePasswordChange}
                  placeholder="Crea tu contraseña"
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
              <Text style={styles.requirementsTitle}>Requisitos de contraseña:</Text>
              <RequirementItem text="Mínimo 7 caracteres" met={password.length >= 7} />
              <RequirementItem text="Al menos una letra" met={/[a-zA-Z]/.test(password)} />
              <RequirementItem text="Al menos un número" met={/[0-9]/.test(password)} />
              <RequirementItem text="Al menos un símbolo (!@#$%...)" met={/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)} />
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
              {confirmPassword.length > 0 && password !== confirmPassword && (
                <Text style={styles.errorText}>Las contraseñas no coinciden</Text>
              )}
              {confirmPassword.length > 0 && password === confirmPassword && (
                <Text style={styles.successText}>✓ Las contraseñas coinciden</Text>
              )}
            </View>

            {/* Register Button */}
            <TouchableOpacity
              style={[styles.registerButton, !isValid && styles.registerButtonDisabled]}
              onPress={handleRegister}
              disabled={loading || !isValid}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={20} color="#fff" />
                  <Text style={styles.registerButtonText}>Crear Cuenta</Text>
                </>
              )}
            </TouchableOpacity>

            {/* Login Link */}
            <View style={styles.loginLinkContainer}>
              <Text style={styles.loginLinkText}>¿Ya tienes cuenta? </Text>
              <TouchableOpacity onPress={() => router.push('/login')}>
                <Text style={styles.loginLink}>Iniciar Sesión</Text>
              </TouchableOpacity>
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
  titleSection: {
    alignItems: 'center',
    marginBottom: 32,
  },
  iconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#0f172a',
  },
  subtitle: {
    fontSize: 15,
    color: '#64748b',
    marginTop: 8,
    textAlign: 'center',
  },
  form: {
    gap: 16,
  },
  inputGroup: {
    gap: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  optionalLabel: {
    fontSize: 12,
    fontWeight: '400',
    color: '#9ca3af',
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
  requirements: {
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  requirementsTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: '#64748b',
    marginBottom: 10,
  },
  requirementItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
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
  registerButton: {
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
  registerButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
    elevation: 0,
  },
  registerButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  loginLinkContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
  },
  loginLinkText: {
    fontSize: 14,
    color: '#64748b',
  },
  loginLink: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
});
