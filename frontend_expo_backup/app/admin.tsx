import React, { useState, useEffect } from 'react';
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
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuth } from '../contexts/AuthContext';
import * as ImagePicker from 'expo-image-picker';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface PendingUser {
  user_id: string;
  name: string;
  email: string;
  full_name: string;
  document_number: string;
  cpf_number: string;
  id_document_image: string;
  cpf_image: string;
  selfie_image?: string;
  created_at: string;
}

interface PendingWithdrawal {
  transaction_id: string;
  user_id: string;
  amount_input: number;
  amount_output: number;
  beneficiary_data: {
    full_name: string;
    account_number: string;
    id_document: string;
    phone_number: string;
    bank: string;
  };
  created_at: string;
}

export default function AdminScreen() {
  const { user } = useAuth();
  const [tab, setTab] = useState<'verifications' | 'withdrawals' | 'rate'>('verifications');
  const [loading, setLoading] = useState(false);
  
  // Verifications
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<PendingUser | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  
  // Withdrawals
  const [pendingWithdrawals, setPendingWithdrawals] = useState<PendingWithdrawal[]>([]);
  const [selectedWithdrawal, setSelectedWithdrawal] = useState<PendingWithdrawal | null>(null);
  const [proofImage, setProofImage] = useState<string | null>(null);
  
  // Rate
  const [currentRate, setCurrentRate] = useState(78);
  const [newRate, setNewRate] = useState('');

  useEffect(() => {
    if (tab === 'verifications') {
      loadPendingVerifications();
    } else if (tab === 'withdrawals') {
      loadPendingWithdrawals();
    } else if (tab === 'rate') {
      loadRate();
    }
  }, [tab]);

  const loadPendingVerifications = async () => {
    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/verifications/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPendingUsers(response.data);
    } catch (error: any) {
      console.error('Error:', error);
      if (error.response?.status === 403) {
        Alert.alert('Acceso Denegado', 'No tienes permisos de administrador');
      }
    } finally {
      setLoading(false);
    }
  };

  const loadPendingWithdrawals = async () => {
    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/withdrawal/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPendingWithdrawals(response.data);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadRate = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setCurrentRate(response.data.ris_to_ves);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const handleApprove = async (userId: string) => {
    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/verifications/decide`,
        { user_id: userId, approved: true },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      Alert.alert('Éxito', 'Usuario aprobado');
      setSelectedUser(null);
      loadPendingVerifications();
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo aprobar');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (userId: string) => {
    if (!rejectionReason.trim()) {
      Alert.alert('Error', 'Ingresa un motivo de rechazo');
      return;
    }

    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/verifications/decide`,
        { user_id: userId, approved: false, rejection_reason: rejectionReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      Alert.alert('Éxito', 'Usuario rechazado');
      setSelectedUser(null);
      setRejectionReason('');
      loadPendingVerifications();
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo rechazar');
    } finally {
      setLoading(false);
    }
  };

  const takeProofPhoto = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Permiso requerido', 'Necesitamos acceso a la cámara');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      quality: 0.8,
      base64: true,
    });

    if (!result.canceled && result.assets[0].base64) {
      setProofImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
    }
  };

  const handleCompleteWithdrawal = async () => {
    if (!proofImage) {
      Alert.alert('Error', 'Toma una foto del comprobante de transferencia');
      return;
    }

    if (!selectedWithdrawal) return;

    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/withdrawal/process`,
        {
          transaction_id: selectedWithdrawal.transaction_id,
          proof_image: proofImage,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      Alert.alert('Éxito', 'Retiro completado y usuario notificado');
      setSelectedWithdrawal(null);
      setProofImage(null);
      loadPendingWithdrawals();
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo completar');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRate = async () => {
    const rate = parseFloat(newRate);
    if (!rate || rate <= 0) {
      Alert.alert('Error', 'Ingresa una tasa válida');
      return;
    }

    try {
      setLoading(true);
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/rate`,
        { ris_to_ves: rate },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      Alert.alert('Éxito', `Tasa actualizada a 1 RIS = ${rate} VES`);
      setCurrentRate(rate);
      setNewRate('');
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo actualizar');
    } finally {
      setLoading(false);
    }
  };

  if (!user || !user.email.includes('admin')) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="lock-closed" size={60} color="#ef4444" />
          <Text style={styles.errorText}>Acceso Denegado</Text>
          <Text style={styles.errorSubtext}>Solo administradores pueden acceder</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Tabs */}
      <View style={styles.tabsContainer}>
        <TouchableOpacity
          style={[styles.tab, tab === 'verifications' && styles.tabActive]}
          onPress={() => setTab('verifications')}
        >
          <Ionicons name="shield-checkmark" size={20} color={tab === 'verifications' ? '#2563eb' : '#6b7280'} />
          <Text style={[styles.tabText, tab === 'verifications' && styles.tabTextActive]}>
            Verificaciones
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tab, tab === 'withdrawals' && styles.tabActive]}
          onPress={() => setTab('withdrawals')}
        >
          <Ionicons name="cash" size={20} color={tab === 'withdrawals' ? '#2563eb' : '#6b7280'} />
          <Text style={[styles.tabText, tab === 'withdrawals' && styles.tabTextActive]}>
            Retiros
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tab, tab === 'rate' && styles.tabActive]}
          onPress={() => setTab('rate')}
        >
          <Ionicons name="trending-up" size={20} color={tab === 'rate' ? '#2563eb' : '#6b7280'} />
          <Text style={[styles.tabText, tab === 'rate' && styles.tabTextActive]}>
            Tasa
          </Text>
        </TouchableOpacity>
      </View>

      {/* Content */}
      <ScrollView style={styles.content}>
        {loading && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#2563eb" />
          </View>
        )}

        {/* Verifications Tab */}
        {tab === 'verifications' && !loading && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>
              Verificaciones Pendientes ({pendingUsers.length})
            </Text>
            {pendingUsers.length === 0 ? (
              <View style={styles.emptyState}>
                <Ionicons name="checkmark-done-circle" size={60} color="#10b981" />
                <Text style={styles.emptyText}>No hay verificaciones pendientes</Text>
              </View>
            ) : (
              pendingUsers.map((user) => (
                <TouchableOpacity
                  key={user.user_id}
                  style={styles.card}
                  onPress={() => setSelectedUser(user)}
                >
                  <View style={styles.cardHeader}>
                    <Ionicons name="person-circle" size={40} color="#2563eb" />
                    <View style={styles.cardInfo}>
                      <Text style={styles.cardTitle}>{user.full_name}</Text>
                      <Text style={styles.cardSubtitle}>{user.email}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={24} color="#6b7280" />
                  </View>
                </TouchableOpacity>
              ))
            )}
          </View>
        )}

        {/* Withdrawals Tab */}
        {tab === 'withdrawals' && !loading && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>
              Retiros Pendientes ({pendingWithdrawals.length})
            </Text>
            {pendingWithdrawals.length === 0 ? (
              <View style={styles.emptyState}>
                <Ionicons name="checkmark-done-circle" size={60} color="#10b981" />
                <Text style={styles.emptyText}>No hay retiros pendientes</Text>
              </View>
            ) : (
              pendingWithdrawals.map((withdrawal) => (
                <TouchableOpacity
                  key={withdrawal.transaction_id}
                  style={styles.card}
                  onPress={() => setSelectedWithdrawal(withdrawal)}
                >
                  <View style={styles.cardHeader}>
                    <Ionicons name="arrow-up-circle" size={40} color="#f59e0b" />
                    <View style={styles.cardInfo}>
                      <Text style={styles.cardTitle}>
                        {withdrawal.amount_input} RIS → {withdrawal.amount_output} VES
                      </Text>
                      <Text style={styles.cardSubtitle}>
                        Para: {withdrawal.beneficiary_data.full_name}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={24} color="#6b7280" />
                  </View>
                </TouchableOpacity>
              ))
            )}
          </View>
        )}

        {/* Rate Tab */}
        {tab === 'rate' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Tasa de Cambio RIS/VES</Text>
            
            <View style={styles.rateCard}>
              <Text style={styles.rateLabel}>Tasa Actual</Text>
              <Text style={styles.rateValue}>1 RIS = {currentRate.toFixed(2)} VES</Text>
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Actualizar Tasa</Text>
              <TextInput
                style={styles.input}
                value={newRate}
                onChangeText={setNewRate}
                keyboardType="numeric"
                placeholder={`Ej: ${currentRate}`}
              />
              <TouchableOpacity
                style={styles.updateButton}
                onPress={handleUpdateRate}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.updateButtonText}>Actualizar Tasa</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </ScrollView>

      {/* User Detail Modal */}
      <Modal visible={!!selectedUser} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <ScrollView>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>Verificar Usuario</Text>
                <TouchableOpacity onPress={() => setSelectedUser(null)}>
                  <Ionicons name="close" size={28} color="#6b7280" />
                </TouchableOpacity>
              </View>

              {selectedUser && (
                <>
                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Nombre Completo</Text>
                    <Text style={styles.modalValue}>{selectedUser.full_name}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Documento</Text>
                    <Text style={styles.modalValue}>{selectedUser.document_number}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>CPF</Text>
                    <Text style={styles.modalValue}>{selectedUser.cpf_number}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Foto Documento</Text>
                    <Image source={{ uri: selectedUser.id_document_image }} style={styles.docImage} />
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Foto CPF</Text>
                    <Image source={{ uri: selectedUser.cpf_image }} style={styles.docImage} />
                  </View>

                  {selectedUser.selfie_image && (
                    <View style={styles.modalSection}>
                      <Text style={styles.modalLabel}>Selfie</Text>
                      <Image source={{ uri: selectedUser.selfie_image }} style={styles.docImage} />
                    </View>
                  )}

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Motivo de Rechazo (opcional)</Text>
                    <TextInput
                      style={styles.textArea}
                      value={rejectionReason}
                      onChangeText={setRejectionReason}
                      placeholder="Documento ilegible, información no coincide, etc."
                      multiline
                      numberOfLines={3}
                    />
                  </View>

                  <View style={styles.modalActions}>
                    <TouchableOpacity
                      style={[styles.actionButton, styles.rejectButton]}
                      onPress={() => handleReject(selectedUser.user_id)}
                      disabled={loading}
                    >
                      <Text style={styles.actionButtonText}>Rechazar</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.actionButton, styles.approveButton]}
                      onPress={() => handleApprove(selectedUser.user_id)}
                      disabled={loading}
                    >
                      <Text style={styles.actionButtonText}>Aprobar</Text>
                    </TouchableOpacity>
                  </View>
                </>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Withdrawal Detail Modal */}
      <Modal visible={!!selectedWithdrawal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <ScrollView>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>Completar Retiro</Text>
                <TouchableOpacity onPress={() => { setSelectedWithdrawal(null); setProofImage(null); }}>
                  <Ionicons name="close" size={28} color="#6b7280" />
                </TouchableOpacity>
              </View>

              {selectedWithdrawal && (
                <>
                  <View style={styles.amountCard}>
                    <Text style={styles.amountLabel}>Monto a Transferir</Text>
                    <Text style={styles.amountValue}>{selectedWithdrawal.amount_output.toFixed(2)} VES</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Beneficiario</Text>
                    <Text style={styles.modalValue}>{selectedWithdrawal.beneficiary_data.full_name}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Banco</Text>
                    <Text style={styles.modalValue}>{selectedWithdrawal.beneficiary_data.bank}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Cuenta</Text>
                    <Text style={styles.modalValue}>{selectedWithdrawal.beneficiary_data.account_number}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Cédula</Text>
                    <Text style={styles.modalValue}>{selectedWithdrawal.beneficiary_data.id_document}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Teléfono</Text>
                    <Text style={styles.modalValue}>{selectedWithdrawal.beneficiary_data.phone_number}</Text>
                  </View>

                  <View style={styles.modalSection}>
                    <Text style={styles.modalLabel}>Comprobante de Transferencia *</Text>
                    {proofImage ? (
                      <>
                        <Image source={{ uri: proofImage }} style={styles.docImage} />
                        <TouchableOpacity style={styles.retakeButton} onPress={takeProofPhoto}>
                          <Text style={styles.retakeButtonText}>Tomar nueva foto</Text>
                        </TouchableOpacity>
                      </>
                    ) : (
                      <TouchableOpacity style={styles.takePhotoButton} onPress={takeProofPhoto}>
                        <Ionicons name="camera" size={40} color="#2563eb" />
                        <Text style={styles.takePhotoText}>Tomar foto del comprobante</Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  <TouchableOpacity
                    style={[styles.completeButton, (!proofImage || loading) && styles.completeButtonDisabled]}
                    onPress={handleCompleteWithdrawal}
                    disabled={!proofImage || loading}
                  >
                    {loading ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.completeButtonText}>Marcar como Completado</Text>
                    )}
                  </TouchableOpacity>
                </>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f3f4f6',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  errorText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1f2937',
    marginTop: 16,
  },
  errorSubtext: {
    fontSize: 16,
    color: '#6b7280',
    marginTop: 8,
  },
  tabsContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    gap: 8,
    borderBottomWidth: 3,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: '#2563eb',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  tabTextActive: {
    color: '#2563eb',
  },
  content: {
    flex: 1,
  },
  loadingContainer: {
    padding: 40,
    alignItems: 'center',
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  cardInfo: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 14,
    color: '#6b7280',
  },
  emptyState: {
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    fontSize: 16,
    color: '#6b7280',
    marginTop: 16,
  },
  rateCard: {
    backgroundColor: '#2563eb',
    borderRadius: 16,
    padding: 24,
    marginBottom: 16,
    alignItems: 'center',
  },
  rateLabel: {
    color: '#dbeafe',
    fontSize: 14,
    marginBottom: 8,
  },
  rateValue: {
    color: '#fff',
    fontSize: 32,
    fontWeight: 'bold',
  },
  input: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    marginBottom: 16,
  },
  updateButton: {
    backgroundColor: '#10b981',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  updateButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '90%',
    padding: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  modalSection: {
    marginBottom: 20,
  },
  modalLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: 8,
  },
  modalValue: {
    fontSize: 16,
    color: '#1f2937',
  },
  docImage: {
    width: '100%',
    height: 200,
    borderRadius: 12,
    resizeMode: 'contain',
    backgroundColor: '#f3f4f6',
  },
  textArea: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    height: 80,
    textAlignVertical: 'top',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 24,
  },
  actionButton: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  rejectButton: {
    backgroundColor: '#ef4444',
  },
  approveButton: {
    backgroundColor: '#10b981',
  },
  actionButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  amountCard: {
    backgroundColor: '#f59e0b',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    marginBottom: 20,
  },
  amountLabel: {
    color: '#fef3c7',
    fontSize: 14,
    marginBottom: 4,
  },
  amountValue: {
    color: '#fff',
    fontSize: 28,
    fontWeight: 'bold',
  },
  takePhotoButton: {
    borderWidth: 2,
    borderColor: '#2563eb',
    borderStyle: 'dashed',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    backgroundColor: '#eff6ff',
  },
  takePhotoText: {
    fontSize: 14,
    color: '#2563eb',
    fontWeight: '600',
    marginTop: 8,
  },
  retakeButton: {
    backgroundColor: '#f3f4f6',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 12,
  },
  retakeButtonText: {
    fontSize: 14,
    color: '#2563eb',
    fontWeight: '600',
  },
  completeButton: {
    backgroundColor: '#10b981',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 24,
  },
  completeButtonDisabled: {
    backgroundColor: '#9ca3af',
  },
  completeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
