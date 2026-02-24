import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import { useRouter } from 'expo-router';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function PoliciesScreen() {
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [policiesContent, setPoliciesContent] = useState('');
  const [policiesVersion, setPoliciesVersion] = useState('');
  const [accepted, setAccepted] = useState(false);
  const router = useRouter();

  useEffect(() => {
    loadPolicies();
  }, []);

  const loadPolicies = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/policies`);
      setPoliciesContent(response.data.content);
      setPoliciesVersion(response.data.version);
    } catch (error) {
      console.error('Error loading policies:', error);
      Alert.alert('Error', 'No se pudieron cargar las políticas. Intente nuevamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async () => {
    if (!accepted) {
      Alert.alert('Atención', 'Debe aceptar los términos para continuar.');
      return;
    }

    setAccepting(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/policies/accept`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );

      Alert.alert(
        'Políticas Aceptadas',
        'Gracias por aceptar nuestras políticas. Ahora puede continuar usando la aplicación.',
        [{ text: 'Continuar', onPress: () => router.replace('/') }]
      );
    } catch (error) {
      console.error('Error accepting policies:', error);
      Alert.alert('Error', 'No se pudieron aceptar las políticas. Intente nuevamente.');
    } finally {
      setAccepting(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#2563eb" />
        <Text style={styles.loadingText}>Cargando políticas...</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Ionicons name="shield-checkmark" size={40} color="#2563eb" />
        <Text style={styles.headerTitle}>Políticas y Términos</Text>
        <Text style={styles.headerSubtitle}>
          Por favor lea y acepte nuestras políticas para continuar
        </Text>
        <View style={styles.versionBadge}>
          <Text style={styles.versionText}>Versión {policiesVersion}</Text>
        </View>
      </View>

      {/* Policies Content */}
      <View style={styles.policiesContainer}>
        <ScrollView 
          style={styles.policiesScroll}
          showsVerticalScrollIndicator={true}
        >
          <Text style={styles.policiesText}>{policiesContent}</Text>
        </ScrollView>
      </View>

      {/* Single Checkbox */}
      <View style={styles.checkboxContainer}>
        <TouchableOpacity 
          style={styles.checkItem} 
          onPress={() => setAccepted(!accepted)} 
          activeOpacity={0.7}
        >
          <View style={[styles.checkbox, accepted && styles.checkboxChecked]}>
            {accepted && <Ionicons name="checkmark" size={18} color="#fff" />}
          </View>
          <Text style={styles.checkLabel}>
            He leído y acepto la <Text style={styles.boldText}>Política de Privacidad</Text>, 
            los <Text style={styles.boldText}>Términos y Condiciones</Text>, y la 
            <Text style={styles.boldText}> Política de Prevención de Lavado de Dinero</Text>. 
            Declaro ser mayor de 18 años, que los fondos utilizados serán de origen lícito, 
            y que utilizaré únicamente métodos de pago de mi titularidad.
          </Text>
        </TouchableOpacity>
      </View>

      {/* Accept Button */}
      <View style={styles.buttonContainer}>
        <TouchableOpacity
          style={[styles.acceptButton, !accepted && styles.acceptButtonDisabled]}
          onPress={handleAccept}
          disabled={!accepted || accepting}
        >
          {accepting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={24} color="#fff" />
              <Text style={styles.acceptButtonText}>Aceptar y Continuar</Text>
            </>
          )}
        </TouchableOpacity>
        
        <Text style={styles.legalNote}>
          Al aceptar, usted confirma que ha leído y acepta estar legalmente
          vinculado por estos términos conforme a la LGPD (Lei N° 13.709/2018).
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
    color: '#64748b',
  },
  header: {
    alignItems: 'center',
    paddingVertical: 20,
    paddingHorizontal: 20,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1e293b',
    marginTop: 12,
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
    marginTop: 8,
  },
  versionBadge: {
    backgroundColor: '#e0f2fe',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginTop: 8,
  },
  versionText: {
    fontSize: 12,
    color: '#0369a1',
    fontWeight: '600',
  },
  policiesContainer: {
    flex: 1,
    margin: 16,
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    overflow: 'hidden',
  },
  policiesScroll: {
    flex: 1,
    padding: 16,
  },
  policiesText: {
    fontSize: 13,
    lineHeight: 20,
    color: '#334155',
  },
  checkboxContainer: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  checkItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  checkbox: {
    width: 26,
    height: 26,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#cbd5e1',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    marginTop: 2,
  },
  checkboxChecked: {
    backgroundColor: '#2563eb',
    borderColor: '#2563eb',
  },
  checkLabel: {
    flex: 1,
    fontSize: 14,
    color: '#475569',
    lineHeight: 22,
  },
  boldText: {
    fontWeight: '600',
    color: '#1e293b',
  },
  buttonContainer: {
    padding: 16,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  acceptButton: {
    backgroundColor: '#2563eb',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
  },
  acceptButtonDisabled: {
    backgroundColor: '#94a3b8',
  },
  acceptButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  legalNote: {
    fontSize: 11,
    color: '#94a3b8',
    textAlign: 'center',
    marginTop: 12,
    lineHeight: 16,
  },
});
