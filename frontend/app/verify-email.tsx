import React, { useState, useRef, useEffect } from 'react';
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
import { useRouter, useLocalSearchParams } from 'expo-router';
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

export default function VerifyEmailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const email = params.email as string || '';
  const { refreshUser } = useAuth();
  
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [countdown, setCountdown] = useState(0);
  
  const inputRefs = useRef<(TextInput | null)[]>([]);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleCodeChange = (text: string, index: number) => {
    const newCode = [...code];
    
    // Handle paste (multiple digits)
    if (text.length > 1) {
      const digits = text.replace(/\D/g, '').slice(0, 6).split('');
      digits.forEach((digit, i) => {
        if (i < 6) newCode[i] = digit;
      });
      setCode(newCode);
      // Focus last filled or next empty
      const lastIndex = Math.min(digits.length - 1, 5);
      inputRefs.current[lastIndex]?.focus();
      return;
    }
    
    // Single digit
    newCode[index] = text.replace(/\D/g, '');
    setCode(newCode);
    
    // Auto-focus next input
    if (text && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyPress = (e: any, index: number) => {
    if (e.nativeEvent.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleVerify = async () => {
    const fullCode = code.join('');
    
    if (fullCode.length !== 6) {
      showAlert('Código Incompleto', 'Ingresa los 6 dígitos del código');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${BACKEND_URL}/api/auth/verify-email`, {
        email,
        code: fullCode
      });

      // Save session token
      await AsyncStorage.setItem('session_token', response.data.session_token);
      
      // Refresh user data
      await refreshUser();

      showAlert('✅ ¡Email Verificado!', 'Ahora debes verificar tu identidad para poder operar.', [
        { text: 'Verificar Identidad', onPress: () => router.replace('/verification') }
      ]);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'Código inválido');
      setCode(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (countdown > 0) return;
    
    setResending(true);
    try {
      await axios.post(`${BACKEND_URL}/api/auth/resend-verification-code`, {
        email
      });
      
      showAlert('Código Enviado', 'Revisa tus mensajes SMS');
      setCountdown(60);
      setCode(['', '', '', '', '', '']);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo reenviar el código');
    } finally {
      setResending(false);
    }
  };

  const isComplete = code.every(digit => digit !== '');

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

          {/* Icon and Title */}
          <View style={styles.titleSection}>
            <View style={styles.iconContainer}>
              <Ionicons name="chatbubble-ellipses" size={48} color="#F5A623" />
            </View>
            <Text style={styles.title}>Verificar Teléfono</Text>
            <Text style={styles.subtitle}>
              Enviamos un código de 6 dígitos por SMS a tu teléfono
            </Text>
            <Text style={styles.emailText}>{email}</Text>
          </View>

          {/* Code Input */}
          <View style={styles.codeContainer}>
            {code.map((digit, index) => (
              <TextInput
                key={index}
                ref={(ref) => inputRefs.current[index] = ref}
                style={[
                  styles.codeInput,
                  digit && styles.codeInputFilled
                ]}
                value={digit}
                onChangeText={(text) => handleCodeChange(text, index)}
                onKeyPress={(e) => handleKeyPress(e, index)}
                keyboardType="number-pad"
                maxLength={1}
                selectTextOnFocus
                autoFocus={index === 0}
              />
            ))}
          </View>

          {/* Timer / Resend */}
          <View style={styles.resendContainer}>
            {countdown > 0 ? (
              <Text style={styles.countdownText}>
                Reenviar código en {countdown}s
              </Text>
            ) : (
              <TouchableOpacity 
                style={styles.resendButton}
                onPress={handleResend}
                disabled={resending}
              >
                {resending ? (
                  <ActivityIndicator size="small" color="#F5A623" />
                ) : (
                  <>
                    <Ionicons name="refresh" size={16} color="#F5A623" />
                    <Text style={styles.resendText}>Reenviar código</Text>
                  </>
                )}
              </TouchableOpacity>
            )}
          </View>

          {/* Info Card */}
          <View style={styles.infoCard}>
            <Ionicons name="information-circle" size={20} color="#0369a1" />
            <Text style={styles.infoText}>
              El código expira en 15 minutos. Revisa tu bandeja de entrada y spam.
            </Text>
          </View>

          {/* Verify Button */}
          <TouchableOpacity
            style={[styles.verifyButton, !isComplete && styles.verifyButtonDisabled]}
            onPress={handleVerify}
            disabled={loading || !isComplete}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="checkmark-circle" size={20} color="#fff" />
                <Text style={styles.verifyButtonText}>Verificar Email</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Change Email */}
          <TouchableOpacity 
            style={styles.changeEmailButton}
            onPress={() => router.back()}
          >
            <Text style={styles.changeEmailText}>¿Email incorrecto? </Text>
            <Text style={styles.changeEmailLink}>Cambiar email</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
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
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 15,
    color: '#64748b',
  },
  emailText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#0f172a',
    marginTop: 4,
  },
  codeContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 10,
    marginBottom: 32,
  },
  codeInput: {
    width: 50,
    height: 60,
    borderRadius: 14,
    backgroundColor: '#fff',
    borderWidth: 2,
    borderColor: '#e2e8f0',
    fontSize: 24,
    fontWeight: '700',
    textAlign: 'center',
    color: '#0f172a',
  },
  codeInputFilled: {
    borderColor: '#F5A623',
    backgroundColor: '#fffbeb',
  },
  resendContainer: {
    alignItems: 'center',
    marginBottom: 24,
  },
  countdownText: {
    fontSize: 14,
    color: '#64748b',
  },
  resendButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  resendText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F5A623',
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#e0f2fe',
    borderRadius: 14,
    padding: 16,
    gap: 12,
    marginBottom: 32,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    color: '#0369a1',
    lineHeight: 20,
  },
  verifyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    paddingVertical: 18,
    borderRadius: 16,
    gap: 10,
    shadowColor: '#059669',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  verifyButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
    elevation: 0,
  },
  verifyButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  changeEmailButton: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 20,
  },
  changeEmailText: {
    fontSize: 14,
    color: '#64748b',
  },
  changeEmailLink: {
    fontSize: 14,
    color: '#F5A623',
    fontWeight: '600',
  },
});
