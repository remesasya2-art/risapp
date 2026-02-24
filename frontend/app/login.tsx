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
  Modal,
  Linking,
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

export default function LoginScreen() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showSupportModal, setShowSupportModal] = useState(false);
  
  // Support form state
  const [supportName, setSupportName] = useState('');
  const [supportEmail, setSupportEmail] = useState('');
  const [supportPhone, setSupportPhone] = useState('');
  const [supportMessage, setSupportMessage] = useState('');

  const handleSupportSubmit = () => {
    if (!supportName || !supportEmail || !supportPhone) {
      showAlert('Error', 'Por favor completa todos los campos obligatorios');
      return;
    }
    
    // Crear mensaje para WhatsApp
    const whatsappMessage = `🆘 *SOLICITUD DE AYUDA - USUARIO SIN ACCESO*%0A%0A👤 Nombre: ${supportName}%0A📧 Email: ${supportEmail}%0A📱 Teléfono: ${supportPhone}%0A%0A💬 Mensaje: ${supportMessage || 'Necesito ayuda para acceder a mi cuenta'}`;
    
    // Número de WhatsApp de soporte
    const supportNumber = '559584098171';
    const whatsappUrl = `https://wa.me/${supportNumber}?text=${whatsappMessage}`;
    
    Linking.openURL(whatsappUrl);
    setShowSupportModal(false);
    
    // Limpiar formulario
    setSupportName('');
    setSupportEmail('');
    setSupportPhone('');
    setSupportMessage('');
  };

  const handleLogin = async () => {
    if (!email.trim()) {
      showAlert('Error', 'Ingresa tu correo electrónico');
      return;
    }

    if (!password) {
      showAlert('Error', 'Ingresa tu contraseña');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${BACKEND_URL}/api/auth/login-password`, {
        email: email.toLowerCase().trim(),
        password
      });

      // Save session token
      await AsyncStorage.setItem('session_token', response.data.session_token);
      
      // Refresh user data
      await refreshUser();

      // Navigate to home
      router.replace('/');
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Error al iniciar sesión';
      showAlert('Error', detail);
    } finally {
      setLoading(false);
    }
  };

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
              <Ionicons name="log-in" size={40} color="#F5A623" />
            </View>
            <Text style={styles.title}>Iniciar Sesión</Text>
            <Text style={styles.subtitle}>
              Ingresa tus credenciales para continuar
            </Text>
          </View>

          {/* Form */}
          <View style={styles.form}>
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
            </View>

            {/* Password */}
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Contraseña</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="lock-closed-outline" size={20} color="#9ca3af" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={password}
                  onChangeText={setPassword}
                  placeholder="Tu contraseña"
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

            {/* Forgot Password */}
            <TouchableOpacity 
              style={styles.forgotPasswordLink}
              onPress={() => router.push('/forgot-password')}
            >
              <Text style={styles.forgotPasswordText}>¿Olvidaste tu contraseña?</Text>
            </TouchableOpacity>

            {/* Login Button */}
            <TouchableOpacity
              style={[styles.loginButton, (!email.trim() || !password) && styles.loginButtonDisabled]}
              onPress={handleLogin}
              disabled={loading || !email.trim() || !password}
              testID="login-submit-button"
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="arrow-forward-circle" size={20} color="#fff" />
                  <Text style={styles.loginButtonText}>Iniciar Sesión</Text>
                </>
              )}
            </TouchableOpacity>

            {/* Register Link */}
            <View style={styles.registerLinkContainer}>
              <Text style={styles.registerLinkText}>¿No tienes cuenta? </Text>
              <TouchableOpacity onPress={() => router.push('/register')}>
                <Text style={styles.registerLink}>Regístrate</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Security Badge */}
          <View style={styles.securityBadge}>
            <Ionicons name="shield-checkmark" size={16} color="#059669" />
            <Text style={styles.securityText}>Conexión segura y encriptada</Text>
          </View>

          {/* Support Button for users without access */}
          <TouchableOpacity 
            style={styles.supportButton}
            onPress={() => setShowSupportModal(true)}
            data-testid="login-support-button"
          >
            <Ionicons name="headset-outline" size={20} color="#fff" />
            <Text style={styles.supportButtonText}>¿No puedes acceder? Solicita ayuda</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Support Modal */}
      <Modal
        visible={showSupportModal}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowSupportModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <View style={styles.modalIconContainer}>
                <Ionicons name="headset" size={28} color="#2563eb" />
              </View>
              <Text style={styles.modalTitle}>Centro de Ayuda</Text>
              <TouchableOpacity 
                onPress={() => setShowSupportModal(false)} 
                style={styles.modalCloseButton}
              >
                <Ionicons name="close" size={24} color="#6b7280" />
              </TouchableOpacity>
            </View>
            
            <Text style={styles.modalSubtitle}>
              ¿No puedes acceder a tu cuenta? Completa tus datos y te ayudaremos por WhatsApp.
            </Text>

            <View style={styles.modalInputGroup}>
              <Text style={styles.modalLabel}>Nombre completo *</Text>
              <TextInput
                style={styles.modalInput}
                placeholder="Tu nombre"
                placeholderTextColor="#9ca3af"
                value={supportName}
                onChangeText={setSupportName}
              />
            </View>

            <View style={styles.modalInputGroup}>
              <Text style={styles.modalLabel}>Correo electrónico *</Text>
              <TextInput
                style={styles.modalInput}
                placeholder="tu@email.com"
                placeholderTextColor="#9ca3af"
                value={supportEmail}
                onChangeText={setSupportEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <View style={styles.modalInputGroup}>
              <Text style={styles.modalLabel}>Teléfono (con código de país) *</Text>
              <TextInput
                style={styles.modalInput}
                placeholder="+55 11 99999-9999"
                placeholderTextColor="#9ca3af"
                value={supportPhone}
                onChangeText={setSupportPhone}
                keyboardType="phone-pad"
              />
            </View>

            <View style={styles.modalInputGroup}>
              <Text style={styles.modalLabel}>¿En qué podemos ayudarte? (opcional)</Text>
              <TextInput
                style={[styles.modalInput, styles.modalTextArea]}
                placeholder="Describe tu problema..."
                placeholderTextColor="#9ca3af"
                value={supportMessage}
                onChangeText={setSupportMessage}
                multiline
                numberOfLines={3}
              />
            </View>

            <TouchableOpacity 
              style={styles.whatsappButton} 
              onPress={handleSupportSubmit}
              data-testid="support-whatsapp-button"
            >
              <Ionicons name="logo-whatsapp" size={20} color="#fff" />
              <Text style={styles.whatsappButtonText}>Contactar por WhatsApp</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
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
    marginBottom: 40,
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
  forgotPasswordLink: {
    alignSelf: 'flex-end',
  },
  forgotPasswordText: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
  loginButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0f172a',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 10,
    marginTop: 8,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
  loginButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
    elevation: 0,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  registerLinkContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
  },
  registerLinkText: {
    fontSize: 14,
    color: '#64748b',
  },
  registerLink: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
  securityBadge: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 40,
    gap: 6,
  },
  securityText: {
    fontSize: 12,
    color: '#059669',
    fontWeight: '500',
  },
  // Support Button Styles
  supportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F5A623',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 14,
    gap: 10,
    marginTop: 24,
    marginBottom: 20,
  },
  supportButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  // Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 24,
    width: '100%',
    maxWidth: 420,
    maxHeight: '90%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#dbeafe',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0f172a',
    flex: 1,
  },
  modalCloseButton: {
    padding: 4,
  },
  modalSubtitle: {
    fontSize: 14,
    color: '#64748b',
    marginBottom: 20,
    lineHeight: 20,
  },
  modalInputGroup: {
    marginBottom: 16,
  },
  modalLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 6,
  },
  modalInput: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#1f2937',
  },
  modalTextArea: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  whatsappButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
    marginTop: 8,
  },
  whatsappButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
