import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  Image,
  Dimensions,
  Platform,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import axios from 'axios';
import { format } from 'date-fns';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system/legacy';
import GlobalHeader from '../components/GlobalHeader';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

const showAlert = (title: string, message: string) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
};

interface Transaction {
  transaction_id: string;
  type: 'recharge' | 'withdrawal';
  status: string;
  amount_input: number;
  amount_output: number;
  created_at: string;
  completed_at?: string;
  proof_image?: string;
  beneficiary_data?: {
    full_name: string;
  };
}

export default function HistoryScreen() {
  const { user, login } = useAuth();
  const [filter, setFilter] = useState<'all' | 'recharge' | 'withdrawal'>('all');
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [proofModalVisible, setProofModalVisible] = useState(false);
  const [selectedProof, setSelectedProof] = useState<{
    image: string;
    transactionId: string;
    amount: string;
    completedAt: string;
  } | null>(null);
  const [loadingProof, setLoadingProof] = useState(false);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    if (user) {
      loadTransactions();
    }
  }, [user, filter]);

  const loadTransactions = async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      const token = await AsyncStorage.getItem('session_token');
      const url = filter === 'all' 
        ? `${BACKEND_URL}/api/transactions`
        : `${BACKEND_URL}/api/transactions?type=${filter}`;
      
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTransactions(response.data);
    } catch (error) {
      console.error('Error loading transactions:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const onRefresh = () => loadTransactions(true);

  const shareProof = async () => {
    if (!selectedProof) return;

    setSharing(true);
    try {
      if (Platform.OS === 'web') {
        const link = document.createElement('a');
        link.href = selectedProof.image;
        link.download = `comprobante_${selectedProof.transactionId.substring(0, 8)}.jpg`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showAlert('Descargado', 'La imagen del comprobante se ha descargado');
      } else {
        const isAvailable = await Sharing.isAvailableAsync();
        
        if (isAvailable) {
          const base64Data = selectedProof.image.replace(/^data:image\/\w+;base64,/, '');
          const fileName = `comprobante_RIS_${selectedProof.transactionId.substring(0, 8)}.jpg`;
          const fileUri = `${FileSystem.cacheDirectory}${fileName}`;
          
          await FileSystem.writeAsStringAsync(fileUri, base64Data, {
            encoding: 'base64',
          });

          await Sharing.shareAsync(fileUri, {
            mimeType: 'image/jpeg',
            dialogTitle: 'Compartir Comprobante',
          });
        } else {
          showAlert('No disponible', 'La función de compartir no está disponible en este dispositivo');
        }
      }
    } catch (error: any) {
      console.error('Error sharing:', error);
      if (error.message !== 'User did not share' && error.message !== 'Share action was cancelled') {
        showAlert('Error', 'No se pudo compartir la imagen del comprobante');
      }
    } finally {
      setSharing(false);
    }
  };

  const viewProof = async (transactionId: string) => {
    try {
      setLoadingProof(true);
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(
        `${BACKEND_URL}/api/transaction/${transactionId}/proof`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      if (response.data.proof_image) {
        setSelectedProof({
          image: response.data.proof_image,
          transactionId: transactionId,
          amount: `${response.data.amount_input?.toFixed(2) || '0.00'} RIS → ${response.data.amount_output?.toFixed(2) || '0.00'} VES`,
          completedAt: response.data.completed_at ? format(new Date(response.data.completed_at), 'dd/MM/yyyy HH:mm') : 'N/A'
        });
        setProofModalVisible(true);
      } else {
        showAlert('Sin comprobante', 'Esta transacción aún no tiene comprobante adjunto.');
      }
    } catch (error: any) {
      console.error('Error loading proof:', error);
      showAlert('Error', error.response?.data?.detail || 'No se pudo cargar el comprobante');
    } finally {
      setLoadingProof(false);
    }
  };

  // Calculate totals
  const totalRecharges = transactions
    .filter(t => t.type === 'recharge' && t.status === 'completed')
    .reduce((sum, t) => sum + t.amount_output, 0);
  
  const totalWithdrawals = transactions
    .filter(t => t.type === 'withdrawal' && t.status === 'completed')
    .reduce((sum, t) => sum + t.amount_input, 0);

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <View style={styles.emptyIconContainer}>
            <Ionicons name="lock-closed" size={48} color="#94a3b8" />
          </View>
          <Text style={styles.emptyTitle}>Acceso Restringido</Text>
          <Text style={styles.emptyText}>Inicia sesión para ver tu historial de transacciones</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Ionicons name="log-in" size={20} color="#fff" />
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const renderTransaction = ({ item }: { item: Transaction }) => {
    const isRecharge = item.type === 'recharge';
    const iconName = isRecharge ? 'arrow-down' : 'arrow-up';
    const iconBgColor = isRecharge ? '#ecfdf5' : '#fef3c7';
    const iconColor = isRecharge ? '#059669' : '#d97706';
    const amountColor = isRecharge ? '#059669' : '#dc2626';
    
    const statusConfig = {
      completed: { color: '#059669', bg: '#ecfdf5', label: 'Completado', icon: 'checkmark-circle' },
      pending: { color: '#d97706', bg: '#fef3c7', label: 'Pendiente', icon: 'time' },
      pending_review: { color: '#2563eb', bg: '#eff6ff', label: 'En Revisión', icon: 'eye' },
      cancelled: { color: '#6b7280', bg: '#f3f4f6', label: 'Cancelado', icon: 'close-circle' },
      rejected: { color: '#dc2626', bg: '#fef2f2', label: 'Rechazado', icon: 'close-circle' },
    };
    
    const status = statusConfig[item.status as keyof typeof statusConfig] || statusConfig.pending;
    const canViewProof = !isRecharge && item.status === 'completed';

    return (
      <TouchableOpacity 
        style={styles.transactionCard}
        onPress={() => canViewProof && viewProof(item.transaction_id)}
        activeOpacity={canViewProof ? 0.7 : 1}
      >
        <View style={styles.transactionRow}>
          {/* Icon */}
          <View style={[styles.transactionIcon, { backgroundColor: iconBgColor }]}>
            <Ionicons name={iconName} size={20} color={iconColor} />
          </View>
          
          {/* Info */}
          <View style={styles.transactionInfo}>
            <Text style={styles.transactionType}>
              {isRecharge ? 'Recarga PIX' : 'Envío a Venezuela'}
            </Text>
            <Text style={styles.transactionDate}>
              {format(new Date(item.created_at), 'dd MMM yyyy • HH:mm')}
            </Text>
            {item.beneficiary_data && (
              <Text style={styles.beneficiaryName}>
                → {item.beneficiary_data.full_name}
              </Text>
            )}
          </View>
          
          {/* Amount */}
          <View style={styles.transactionAmounts}>
            <Text style={[styles.transactionAmount, { color: amountColor }]}>
              {isRecharge ? '+' : '-'}{item.amount_input.toFixed(2)}
            </Text>
            <Text style={styles.transactionCurrency}>
              {isRecharge ? 'BRL' : 'RIS'}
            </Text>
          </View>
        </View>
        
        {/* Footer */}
        <View style={styles.transactionFooter}>
          <View style={[styles.statusBadge, { backgroundColor: status.bg }]}>
            <Ionicons name={status.icon as any} size={12} color={status.color} />
            <Text style={[styles.statusText, { color: status.color }]}>
              {status.label}
            </Text>
          </View>
          
          <View style={styles.transactionMeta}>
            <Text style={styles.transactionId}>
              #{item.transaction_id.substring(0, 8)}
            </Text>
            {canViewProof && (
              <View style={styles.viewProofHint}>
                <Ionicons name="receipt-outline" size={14} color="#2563eb" />
              </View>
            )}
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header with back and home buttons */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <View>
            <Text style={styles.headerTitle}>Historial</Text>
            <Text style={styles.headerSubtitle}>Tus movimientos recientes</Text>
          </View>
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={() => router.replace('/')} style={styles.headerBtn}>
            <Ionicons name="home" size={22} color="#0f172a" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/notifications')} style={styles.headerBtn}>
            <Ionicons name="notifications-outline" size={22} color="#0f172a" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Stats Cards */}
      <View style={styles.statsContainer}>
        <View style={[styles.statCard, { backgroundColor: '#ecfdf5' }]}>
          <View style={styles.statIconContainer}>
            <Ionicons name="arrow-down" size={18} color="#059669" />
          </View>
          <Text style={styles.statLabel}>Ingresos</Text>
          <Text style={[styles.statAmount, { color: '#059669' }]}>
            +{totalRecharges.toFixed(0)} RIS
          </Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#fef3c7' }]}>
          <View style={styles.statIconContainer}>
            <Ionicons name="arrow-up" size={18} color="#d97706" />
          </View>
          <Text style={styles.statLabel}>Egresos</Text>
          <Text style={[styles.statAmount, { color: '#d97706' }]}>
            -{totalWithdrawals.toFixed(0)} RIS
          </Text>
        </View>
      </View>

      {/* Filter Tabs */}
      <View style={styles.filterContainer}>
        {[
          { key: 'all', label: 'Todos', icon: 'list' },
          { key: 'recharge', label: 'Ingresos', icon: 'arrow-down' },
          { key: 'withdrawal', label: 'Egresos', icon: 'arrow-up' },
        ].map((item) => (
          <TouchableOpacity
            key={item.key}
            style={[styles.filterTab, filter === item.key && styles.filterTabActive]}
            onPress={() => setFilter(item.key as any)}
          >
            <Ionicons 
              name={item.icon as any} 
              size={16} 
              color={filter === item.key ? '#fff' : '#64748b'} 
            />
            <Text style={[styles.filterText, filter === item.key && styles.filterTextActive]}>
              {item.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Transactions List */}
      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#F5A623" />
          <Text style={styles.loadingText}>Cargando transacciones...</Text>
        </View>
      ) : transactions.length === 0 ? (
        <View style={styles.centerContainer}>
          <View style={styles.emptyIconContainer}>
            <Ionicons name="receipt-outline" size={48} color="#94a3b8" />
          </View>
          <Text style={styles.emptyTitle}>Sin transacciones</Text>
          <Text style={styles.emptyText}>
            {filter === 'all' 
              ? 'Aún no tienes movimientos registrados' 
              : filter === 'recharge' 
                ? 'No tienes recargas registradas'
                : 'No tienes envíos registrados'}
          </Text>
        </View>
      ) : (
        <FlatList
          data={transactions}
          renderItem={renderTransaction}
          keyExtractor={(item) => item.transaction_id}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#F5A623"
              colors={['#F5A623']}
            />
          }
        />
      )}

      {/* Proof Image Modal */}
      <Modal
        visible={proofModalVisible}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setProofModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            {/* Modal Header */}
            <View style={styles.modalHeader}>
              <View style={styles.modalHeaderLeft}>
                <View style={styles.modalIconContainer}>
                  <Ionicons name="receipt" size={24} color="#059669" />
                </View>
                <View>
                  <Text style={styles.modalTitle}>Comprobante</Text>
                  <Text style={styles.modalSubtitle}>Transferencia completada</Text>
                </View>
              </View>
              <TouchableOpacity 
                style={styles.modalCloseButton}
                onPress={() => setProofModalVisible(false)}
              >
                <Ionicons name="close" size={24} color="#64748b" />
              </TouchableOpacity>
            </View>
            
            {selectedProof && (
              <>
                {/* Info */}
                <View style={styles.proofInfoSection}>
                  <View style={styles.proofInfoRow}>
                    <Text style={styles.proofInfoLabel}>ID Transacción</Text>
                    <Text style={styles.proofInfoValue}>
                      #{selectedProof.transactionId.substring(0, 12)}
                    </Text>
                  </View>
                  <View style={styles.proofInfoRow}>
                    <Text style={styles.proofInfoLabel}>Monto</Text>
                    <Text style={[styles.proofInfoValue, { color: '#059669', fontWeight: '700' }]}>
                      {selectedProof.amount}
                    </Text>
                  </View>
                  <View style={styles.proofInfoRow}>
                    <Text style={styles.proofInfoLabel}>Fecha</Text>
                    <Text style={styles.proofInfoValue}>{selectedProof.completedAt}</Text>
                  </View>
                </View>
                
                {/* Image */}
                <View style={styles.proofImageContainer}>
                  <Image 
                    source={{ uri: selectedProof.image }} 
                    style={styles.proofImage}
                    resizeMode="contain"
                  />
                </View>

                {/* Actions */}
                <View style={styles.modalActions}>
                  <TouchableOpacity 
                    style={styles.shareButton}
                    onPress={shareProof}
                    disabled={sharing}
                  >
                    {sharing ? (
                      <ActivityIndicator size="small" color="#fff" />
                    ) : (
                      <>
                        <Ionicons name="share-social" size={20} color="#fff" />
                        <Text style={styles.shareButtonText}>Compartir</Text>
                      </>
                    )}
                  </TouchableOpacity>
                  
                  <TouchableOpacity 
                    style={styles.closeButton}
                    onPress={() => setProofModalVisible(false)}
                  >
                    <Text style={styles.closeButtonText}>Cerrar</Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
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
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#0f172a',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 4,
  },
  statsContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    gap: 12,
    marginBottom: 16,
  },
  statCard: {
    flex: 1,
    borderRadius: 16,
    padding: 16,
  },
  statIconContainer: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#64748b',
    fontWeight: '500',
  },
  statAmount: {
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    gap: 8,
    marginBottom: 16,
  },
  filterTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#fff',
    gap: 6,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  filterTabActive: {
    backgroundColor: '#0f172a',
    borderColor: '#0f172a',
  },
  filterText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748b',
  },
  filterTextActive: {
    color: '#fff',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  emptyIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#0f172a',
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 24,
  },
  loadingText: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 12,
  },
  loginButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0f172a',
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 32,
  },
  transactionCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  transactionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  transactionIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  transactionInfo: {
    flex: 1,
  },
  transactionType: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0f172a',
  },
  transactionDate: {
    fontSize: 12,
    color: '#94a3b8',
    marginTop: 2,
  },
  beneficiaryName: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 4,
    fontWeight: '500',
  },
  transactionAmounts: {
    alignItems: 'flex-end',
  },
  transactionAmount: {
    fontSize: 17,
    fontWeight: '700',
  },
  transactionCurrency: {
    fontSize: 11,
    color: '#94a3b8',
    fontWeight: '500',
    marginTop: 2,
  },
  transactionFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 20,
    gap: 5,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
  transactionMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  transactionId: {
    fontSize: 11,
    color: '#94a3b8',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  viewProofHint: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  // Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    maxHeight: '90%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  modalIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: '#ecfdf5',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  modalSubtitle: {
    fontSize: 13,
    color: '#64748b',
    marginTop: 2,
  },
  modalCloseButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  proofInfoSection: {
    backgroundColor: '#f8fafc',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  proofInfoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  proofInfoLabel: {
    fontSize: 13,
    color: '#64748b',
  },
  proofInfoValue: {
    fontSize: 13,
    fontWeight: '600',
    color: '#0f172a',
  },
  proofImageContainer: {
    backgroundColor: '#f1f5f9',
    borderRadius: 16,
    overflow: 'hidden',
    marginBottom: 20,
  },
  proofImage: {
    width: '100%',
    height: 280,
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
  },
  shareButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    paddingVertical: 16,
    borderRadius: 14,
    gap: 8,
  },
  shareButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  closeButton: {
    flex: 1,
    backgroundColor: '#f1f5f9',
    paddingVertical: 16,
    borderRadius: 14,
    alignItems: 'center',
  },
  closeButtonText: {
    color: '#64748b',
    fontSize: 16,
    fontWeight: '600',
  },
});
