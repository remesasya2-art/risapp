import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Platform, Dimensions, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const isWeb = Platform.OS === 'web';
const isLargeScreen = SCREEN_WIDTH >= 768;

interface WebWrapperProps {
  children: React.ReactNode;
  showBranding?: boolean;
}

export default function WebWrapper({ children, showBranding = true }: WebWrapperProps) {
  const [rate, setRate] = useState<number | null>(null);
  const [loadingRate, setLoadingRate] = useState(true);

  // Cargar tasa del backend
  useEffect(() => {
    if (isWeb && isLargeScreen) {
      loadRate();
      // Actualizar cada 30 segundos
      const interval = setInterval(loadRate, 30000);
      return () => clearInterval(interval);
    }
  }, []);

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

  // On large web screens, center content and show branding
  return (
    <View style={styles.outerContainer}>
      {/* Left side - Branding */}
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
                <Ionicons name="shield-checkmark" size={20} color="#10b981" />
                <Text style={styles.featureText}>Transferencias seguras y verificadas</Text>
              </View>
              <View style={styles.featureItem}>
                <Ionicons name="flash" size={20} color="#f59e0b" />
                <Text style={styles.featureText}>Envíos rápidos a Venezuela</Text>
              </View>
              <View style={styles.featureItem}>
                <Ionicons name="wallet" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>Recargas con PIX desde Brasil</Text>
              </View>
              <View style={styles.featureItem}>
                <Ionicons name="phone-portrait" size={20} color="#8b5cf6" />
                <Text style={styles.featureText}>Disponible en web y móvil</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Center - App Container */}
      <View style={styles.appContainer}>
        <View style={styles.appInner}>
          {children}
        </View>
      </View>

      {/* Right side - Info cards with live rate */}
      {SCREEN_WIDTH >= 1200 && (
        <View style={styles.infoSection}>
          <View style={styles.infoCard}>
            <Ionicons name="help-circle" size={24} color="#64748b" />
            <Text style={styles.infoTitle}>¿Necesitas ayuda?</Text>
            <Text style={styles.infoText}>
              Nuestro equipo de soporte está disponible para asistirte.
            </Text>
          </View>
          <View style={[styles.infoCard, styles.rateCard]}>
            <View style={styles.rateHeader}>
              <Ionicons name="trending-up" size={24} color="#F5A623" />
              <View style={styles.liveBadge}>
                <View style={styles.liveDot} />
                <Text style={styles.liveText}>EN VIVO</Text>
              </View>
            </View>
            <Text style={styles.infoTitle}>Tasa del día</Text>
            {loadingRate ? (
              <ActivityIndicator size="small" color="#F5A623" />
            ) : (
              <Text style={styles.rateValue}>
                1 RIS = {rate?.toFixed(2) || '---'} VES
              </Text>
            )}
            <Text style={styles.infoSubtext}>Actualizado en tiempo real</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  outerContainer: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
  },
  
  // Branding Section (Left)
  brandingSection: {
    width: 320,
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
    borderRadius: 20,
    backgroundColor: 'rgba(245, 166, 35, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  brandTitle: {
    fontSize: 42,
    fontWeight: '800',
    color: '#fff',
    letterSpacing: 2,
  },
  brandSubtitle: {
    fontSize: 16,
    color: 'rgba(255,255,255,0.7)',
    marginTop: 8,
    marginBottom: 48,
  },
  featuresList: {
    gap: 20,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  featureText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.9)',
  },
  
  // App Container (Center)
  appContainer: {
    flex: 1,
    maxWidth: 480,
    backgroundColor: '#f8fafc',
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
    borderRadius: 16,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
  },
  rateCard: {
    borderWidth: 2,
    borderColor: '#F5A623',
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
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    gap: 4,
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
    fontSize: 20,
    fontWeight: '700',
    color: '#F5A623',
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#0f172a',
    marginTop: 12,
    marginBottom: 8,
  },
  infoText: {
    fontSize: 14,
    color: '#64748b',
    lineHeight: 20,
  },
  infoSubtext: {
    fontSize: 12,
    color: '#94a3b8',
    marginTop: 8,
  },
});
