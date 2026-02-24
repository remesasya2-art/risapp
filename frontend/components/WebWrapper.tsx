import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Platform, Dimensions, Text, ActivityIndicator, TouchableOpacity, TextInput, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import { colors } from '../constants/theme';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const isWeb = Platform.OS === 'web';
const isLargeScreen = SCREEN_WIDTH >= 768;

interface WebWrapperProps {
  children: React.ReactNode;
  showBranding?: boolean;
  fullWidth?: boolean;  // Para pantallas que necesitan todo el ancho (ej: admin-panel)
}

// Modal de soporte sin login
const GuestSupportModal = ({ visible, onClose }: { visible: boolean; onClose: () => void }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');

  const handleSubmit = () => {
    if (!name || !email || !phone) {
      alert('Por favor completa todos los campos');
      return;
    }
    
    // Crear mensaje para WhatsApp
    const whatsappMessage = `🆘 *SOLICITUD DE AYUDA - USUARIO SIN ACCESO*%0A%0A👤 Nombre: ${name}%0A📧 Email: ${email}%0A📱 Teléfono: ${phone}%0A%0A💬 Mensaje: ${message || 'Necesito ayuda para acceder a mi cuenta'}`;
    
    // Número de WhatsApp de soporte
    const supportNumber = '559584098171';
    const whatsappUrl = `https://wa.me/${supportNumber}?text=${whatsappMessage}`;
    
    Linking.openURL(whatsappUrl);
    onClose();
  };

  if (!visible) return null;

  return (
    <View style={guestStyles.overlay}>
      <View style={guestStyles.modal}>
        <View style={guestStyles.modalHeader}>
          <View style={guestStyles.modalIconContainer}>
            <Ionicons name="headset" size={28} color={colors.primary.main} />
          </View>
          <Text style={guestStyles.modalTitle}>Centro de Ayuda</Text>
          <TouchableOpacity onPress={onClose} style={guestStyles.closeButton}>
            <Ionicons name="close" size={24} color={colors.text.secondary} />
          </TouchableOpacity>
        </View>
        
        <Text style={guestStyles.modalSubtitle}>
          ¿No puedes acceder a tu cuenta? Completa tus datos y te ayudaremos por WhatsApp.
        </Text>

        <View style={guestStyles.inputGroup}>
          <Text style={guestStyles.inputLabel}>Nombre completo</Text>
          <TextInput
            style={guestStyles.input}
            placeholder="Tu nombre"
            placeholderTextColor={colors.text.disabled}
            value={name}
            onChangeText={setName}
          />
        </View>

        <View style={guestStyles.inputGroup}>
          <Text style={guestStyles.inputLabel}>Correo electrónico</Text>
          <TextInput
            style={guestStyles.input}
            placeholder="tu@email.com"
            placeholderTextColor={colors.text.disabled}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
          />
        </View>

        <View style={guestStyles.inputGroup}>
          <Text style={guestStyles.inputLabel}>Teléfono (con código de país)</Text>
          <TextInput
            style={guestStyles.input}
            placeholder="+55 11 99999-9999"
            placeholderTextColor={colors.text.disabled}
            value={phone}
            onChangeText={setPhone}
            keyboardType="phone-pad"
          />
        </View>

        <View style={guestStyles.inputGroup}>
          <Text style={guestStyles.inputLabel}>¿En qué podemos ayudarte? (opcional)</Text>
          <TextInput
            style={[guestStyles.input, guestStyles.textArea]}
            placeholder="Describe tu problema..."
            placeholderTextColor={colors.text.disabled}
            value={message}
            onChangeText={setMessage}
            multiline
            numberOfLines={3}
          />
        </View>

        <TouchableOpacity style={guestStyles.submitButton} onPress={handleSubmit}>
          <Ionicons name="logo-whatsapp" size={20} color="#fff" />
          <Text style={guestStyles.submitButtonText}>Contactar por WhatsApp</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default function WebWrapper({ children, showBranding = true, fullWidth = false }: WebWrapperProps) {
  const [rate, setRate] = useState<number | null>(null);
  const [loadingRate, setLoadingRate] = useState(true);
  const [showGuestSupport, setShowGuestSupport] = useState(false);

  // Cargar tasa del backend
  useEffect(() => {
    if (isWeb && isLargeScreen && !fullWidth) {
      loadRate();
      // Actualizar cada 30 segundos
      const interval = setInterval(loadRate, 30000);
      return () => clearInterval(interval);
    }
  }, [fullWidth]);

  const loadRate = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setRate(response.data.ris_to_ves);
    } catch (error) {
      console.log('Error loading rate in WebWrapper');
    } finally {
      setLoadingRate(false);
    }
  };

  // On mobile or small screens, just render children
  if (!isWeb || !isLargeScreen) {
    return <>{children}</>;
  }

  // If fullWidth is true, render children without sidebars (for admin panel, etc)
  if (fullWidth) {
    return (
      <View style={styles.fullWidthContainer}>
        {children}
      </View>
    );
  }

  // On large web screens, center content and show branding
  return (
    <View style={styles.outerContainer}>
      {/* Left side - Branding (only for unauthenticated users) */}
      {showBranding && SCREEN_WIDTH >= 1024 && (
        <View style={styles.brandingSection}>
          <View style={styles.brandingContent}>
            <View style={styles.logoContainer}>
              <Ionicons name="swap-horizontal" size={48} color="#F5A623" />
            </View>
            <Text style={styles.brandTitle}>RIS</Text>
            <Text style={styles.brandSubtitle}>Remesas Internacionales Seguras</Text>
            
            <View style={styles.featuresList}>
              <View style={styles.featureItem}>
                <View style={styles.featureIconBg}>
                  <Ionicons name="shield-checkmark" size={16} color={colors.primary.main} />
                </View>
                <Text style={styles.featureText}>Transferencias seguras y verificadas</Text>
              </View>
              <View style={styles.featureItem}>
                <View style={styles.featureIconBg}>
                  <Ionicons name="flash" size={16} color={colors.primary.main} />
                </View>
                <Text style={styles.featureText}>Envíos rápidos a Venezuela</Text>
              </View>
              <View style={styles.featureItem}>
                <View style={styles.featureIconBg}>
                  <Ionicons name="wallet" size={16} color={colors.primary.main} />
                </View>
                <Text style={styles.featureText}>Recargas con PIX desde Brasil</Text>
              </View>
              <View style={styles.featureItem}>
                <View style={styles.featureIconBg}>
                  <Ionicons name="phone-portrait" size={16} color={colors.primary.main} />
                </View>
                <Text style={styles.featureText}>Disponible en web y móvil</Text>
              </View>
            </View>

            <TouchableOpacity 
              style={styles.guestSupportButton}
              onPress={() => setShowGuestSupport(true)}
            >
              <Ionicons name="headset-outline" size={20} color="#fff" />
              <Text style={styles.guestSupportText}>¿No puedes acceder? Solicita ayuda</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Center - App Container (full width when user is authenticated) */}
      <View style={[styles.appContainer, !showBranding && styles.appContainerFullWidth]}>
        <View style={[styles.appInner, !showBranding && styles.appInnerFullWidth]}>
          {children}
        </View>
      </View>

      {/* Right side - Live rate card only (only for unauthenticated users) */}
      {showBranding && SCREEN_WIDTH >= 1200 && (
        <View style={styles.infoSection}>
          <View style={[styles.infoCard, styles.rateCard]}>
            <View style={styles.rateHeader}>
              <Ionicons name="trending-up" size={24} color={colors.secondary.main} />
              <View style={styles.liveBadge}>
                <View style={styles.liveDot} />
                <Text style={styles.liveText}>EN VIVO</Text>
              </View>
            </View>
            <Text style={styles.infoTitle}>Tasa del día</Text>
            {loadingRate ? (
              <ActivityIndicator size="small" color={colors.secondary.main} />
            ) : (
              <Text style={styles.rateValue}>
                1 RIS = {rate?.toFixed(2) || '---'} VES
              </Text>
            )}
            <Text style={styles.infoSubtext}>Actualizado en tiempo real</Text>
          </View>
        </View>
      )}

      {/* Guest Support Modal */}
      <GuestSupportModal 
        visible={showGuestSupport} 
        onClose={() => setShowGuestSupport(false)} 
      />
    </View>
  );
}

const guestStyles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
  },
  modal: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 32,
    width: '90%',
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
    backgroundColor: colors.primary.main + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  modalTitle: {
    flex: 1,
    fontSize: 22,
    fontWeight: '700',
    color: colors.text.primary,
  },
  closeButton: {
    padding: 8,
  },
  modalSubtitle: {
    fontSize: 14,
    color: colors.text.secondary,
    lineHeight: 20,
    marginBottom: 24,
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.text.secondary,
    marginBottom: 6,
  },
  input: {
    backgroundColor: colors.background.subtle,
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  textArea: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  submitButton: {
    backgroundColor: '#25D366',
    borderRadius: 25,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginTop: 8,
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

const styles = StyleSheet.create({
  outerContainer: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: colors.background.default,
    justifyContent: 'center',
  },
  fullWidthContainer: {
    flex: 1,
    backgroundColor: colors.background.default,
    width: '100%',
  },
  
  // Branding Section (Left) - Professional dark blue style
  brandingSection: {
    width: 340,
    backgroundColor: '#1e3a5f',
    justifyContent: 'center',
    paddingHorizontal: 40,
  },
  brandingContent: {
    alignItems: 'flex-start',
  },
  logoContainer: {
    width: 80,
    height: 80,
    borderRadius: 24,
    backgroundColor: 'rgba(245, 166, 35, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  brandTitle: {
    fontSize: 48,
    fontWeight: '800',
    color: '#fff',
    letterSpacing: 3,
  },
  brandSubtitle: {
    fontSize: 15,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 8,
    marginBottom: 48,
  },
  featuresList: {
    gap: 18,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  featureIconBg: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  featureText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.95)',
    fontWeight: '500',
  },
  guestSupportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#F5A623',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 25,
    marginTop: 48,
  },
  guestSupportText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
  },
  
  // App Container (Center)
  appContainer: {
    flex: 1,
    maxWidth: 480,
    backgroundColor: colors.background.paper,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: '#e2e8f0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
  },
  appInner: {
    flex: 1,
  },
  
  // Info Section (Right)
  infoSection: {
    width: 280,
    padding: 24,
    justifyContent: 'center',
    gap: 20,
  },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
  },
  rateCard: {
    borderWidth: 2,
    borderColor: colors.secondary.main,
  },
  rateHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  liveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef3c7',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
    gap: 5,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#10b981',
  },
  liveText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#92400e',
  },
  rateValue: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.secondary.main,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text.primary,
    marginTop: 12,
    marginBottom: 8,
  },
  infoText: {
    fontSize: 14,
    color: colors.text.secondary,
    lineHeight: 20,
  },
  infoSubtext: {
    fontSize: 12,
    color: colors.text.disabled,
    marginTop: 8,
  },
});
