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

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function SetPasswordScreen() {
  const router = useRouter();
  const [password, setPassword] = useState('');
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
    setPassword(text);
    setErrors(validatePassword(text));
  };

  const handleSubmit = async () => {
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
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/auth/set-password`,
        { password, confirm_password: confirmPassword },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      showAlert('¡Listo!', 'Tu contraseña ha sido configurada exitosamente.', [
        { text: 'Continuar', onPress: () => router.replace('/') }
      ]);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo configurar la contraseña');
    } finally {
      setLoading(false);
    }
  };

  const isValid = password.length >= 7 && 
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
          <View style={styles.header}>
            <View style={styles.iconContainer}>
              <Ionicons name="lock-closed" size={48} color="#2563eb" />
            </View>
            <Text style={styles.title}>Configura tu Contraseña</Text>
            <Text style={styles.subtitle}>
              Para mayor seguridad, configura una contraseña para acceder a tu cuenta
            </Text>
          </View>

          <View style={styles.form}>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Nueva Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="key-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={password}
                  onChangeText={handlePasswordChange}
                  placeholder="Ingresa tu contraseña"
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
              <RequirementItem text="Mínimo 7 caracteres" met={password.length >= 7} />
              <RequirementItem text="Al menos una letra" met={/[a-zA-Z]/.test(password)} />
              <RequirementItem text="Al menos un número" met={/[0-9]/.test(password)} />
              <RequirementItem text="Al menos un símbolo (!@#$%...)" met={/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)} />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Confirmar Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="key-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
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

            <TouchableOpacity
              style={[styles.submitButton, !isValid && styles.submitButtonDisabled]}
              onPress={handleSubmit}
              disabled={loading || !isValid}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="shield-checkmark" size={20} color="#fff" />
                  <Text style={styles.submitButtonText}>Configurar Contraseña</Text>
                </>
              )}
            </TouchableOpacity>
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
    alignItems: 'center',
    marginBottom: 32,
  },
  iconContainer: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: '#dbeafe',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1f2937',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 8,
    paddingHorizontal: 20,
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
    padding: 16,
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
    backgroundColor: '#2563eb',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
    marginTop: 16,
  },
  submitButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
