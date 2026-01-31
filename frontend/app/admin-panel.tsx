import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  Modal,
  Alert,
  Platform,
  Image,
  Dimensions,
  KeyboardAvoidingView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import { useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

type TabType = 'dashboard' | 'withdrawals' | 'recharges' | 'support' | 'users' | 'admins' | 'settings';

interface DashboardData {
  users: { total: number; verified: number; pending_kyc: number };
  transactions: { total: number; completed: number; pending_withdrawals: number; pending_recharges: number };
  support: { open_chats: number };
  volume: { withdrawals: number; recharges: number };
  current_rate: number;
}

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons?.[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function AdminPanelScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [userRole, setUserRole] = useState<string>('user');

  useFocusEffect(
    useCallback(() => {
      checkAdminAccess();
    }, [])
  );

  const checkAdminAccess = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDashboard(response.data);
      
      const userResponse = await axios.get(`${BACKEND_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setUserRole(userResponse.data.role || 'admin');
      setLoading(false);
    } catch (error: any) {
      console.error('Admin access error:', error);
      if (error.response?.status === 403) {
        showAlert('Acceso Denegado', 'No tienes permisos de administrador');
        router.back();
      }
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await checkAdminAccess();
    setRefreshing(false);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#2563eb" />
          <Text style={styles.loadingText}>Cargando panel...</Text>
        </View>
      </SafeAreaView>
    );
  }

  const tabs = [
    { key: 'dashboard', icon: 'grid', label: 'Inicio' },
    { key: 'withdrawals', icon: 'arrow-up-circle', label: 'Retiros', badge: dashboard?.transactions.pending_withdrawals },
    { key: 'recharges', icon: 'arrow-down-circle', label: 'Recargas', badge: dashboard?.transactions.pending_recharges },
    { key: 'support', icon: 'chatbubbles', label: 'Soporte', badge: dashboard?.support.open_chats },
    { key: 'users', icon: 'people', label: 'Usuarios' },
    ...(userRole === 'super_admin' ? [{ key: 'admins', icon: 'shield', label: 'Admins' }] : []),
    { key: 'settings', icon: 'settings', label: 'Config' },
  ];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Compact Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color="#1f2937" />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle}>Admin</Text>
          <View style={[styles.roleBadge, userRole === 'super_admin' && styles.superBadge]}>
            <Text style={styles.roleBadgeText}>{userRole === 'super_admin' ? 'Super' : 'Admin'}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={onRefresh} style={styles.refreshButton}>
          <Ionicons name="refresh" size={22} color="#2563eb" />
        </TouchableOpacity>
      </View>

      {/* Main Content - Takes full remaining space */}
      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentContainer}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        showsVerticalScrollIndicator={false}
      >
        {activeTab === 'dashboard' && <DashboardTab data={dashboard} />}
        {activeTab === 'withdrawals' && <WithdrawalsTab />}
        {activeTab === 'recharges' && <RechargesTab />}
        {activeTab === 'support' && <SupportTab />}
        {activeTab === 'users' && <UsersTab />}
        {activeTab === 'admins' && userRole === 'super_admin' && <AdminsTab />}
        {activeTab === 'settings' && <SettingsTab currentRate={dashboard?.current_rate || 78} onRateUpdated={onRefresh} />}
      </ScrollView>

      {/* Bottom Navigation - Fixed at bottom */}
      <View style={styles.bottomNav}>
        <ScrollView 
          horizontal 
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.bottomNavContent}
        >
          {tabs.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.navItem, activeTab === tab.key && styles.navItemActive]}
              onPress={() => setActiveTab(tab.key as TabType)}
            >
              <View style={styles.navIconContainer}>
                <Ionicons 
                  name={tab.icon as any} 
                  size={22} 
                  color={activeTab === tab.key ? '#2563eb' : '#6b7280'} 
                />
                {tab.badge !== undefined && tab.badge > 0 && (
                  <View style={styles.navBadge}>
                    <Text style={styles.navBadgeText}>{tab.badge > 9 ? '9+' : tab.badge}</Text>
                  </View>
                )}
              </View>
              <Text style={[styles.navLabel, activeTab === tab.key && styles.navLabelActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

// Dashboard Tab - Optimized layout
function DashboardTab({ data }: { data: DashboardData | null }) {
  if (!data) return null;

  return (
    <View style={styles.tabContent}>
      {/* Quick Stats Row */}
      <View style={styles.quickStatsRow}>
        <QuickStat icon="arrow-up" value={data.transactions.pending_withdrawals} label="Retiros" color="#ef4444" />
        <QuickStat icon="arrow-down" value={data.transactions.pending_recharges} label="Recargas" color="#10b981" />
        <QuickStat icon="chatbubble" value={data.support.open_chats} label="Soporte" color="#8b5cf6" />
        <QuickStat icon="person-add" value={data.users.pending_kyc} label="KYC" color="#f59e0b" />
      </View>

      {/* Stats Cards */}
      <Text style={styles.sectionTitle}>Estadísticas</Text>
      <View style={styles.statsGrid}>
        <StatCard icon="people" title="Total Usuarios" value={data.users.total} color="#2563eb" />
        <StatCard icon="checkmark-circle" title="Verificados" value={data.users.verified} color="#10b981" />
        <StatCard icon="swap-horizontal" title="Tasa RIS/VES" value={data.current_rate} color="#06b6d4" />
        <StatCard icon="receipt" title="Transacciones" value={data.transactions.completed} color="#8b5cf6" />
      </View>

      {/* Volume Summary */}
      <View style={styles.volumeCard}>
        <Text style={styles.volumeTitle}>Volumen Total</Text>
        <View style={styles.volumeGrid}>
          <View style={styles.volumeItem}>
            <Text style={styles.volumeValue}>{data.volume.withdrawals.toFixed(0)}</Text>
            <Text style={styles.volumeLabel}>RIS Enviados</Text>
          </View>
          <View style={styles.volumeDivider} />
          <View style={styles.volumeItem}>
            <Text style={styles.volumeValue}>{data.volume.recharges.toFixed(0)}</Text>
            <Text style={styles.volumeLabel}>BRL Recargados</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

function QuickStat({ icon, value, label, color }: { icon: string; value: number; label: string; color: string }) {
  return (
    <View style={styles.quickStat}>
      <View style={[styles.quickStatIcon, { backgroundColor: color + '20' }]}>
        <Ionicons name={icon as any} size={18} color={color} />
        {value > 0 && <View style={[styles.quickStatDot, { backgroundColor: color }]} />}
      </View>
      <Text style={styles.quickStatValue}>{value}</Text>
      <Text style={styles.quickStatLabel}>{label}</Text>
    </View>
  );
}

function StatCard({ icon, title, value, color }: { icon: string; title: string; value: number; color: string }) {
  return (
    <View style={styles.statCard}>
      <Ionicons name={icon as any} size={24} color={color} />
      <Text style={styles.statValue}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
      <Text style={styles.statTitle}>{title}</Text>
    </View>
  );
}

// Withdrawals Tab - Full screen
function WithdrawalsTab() {
  const [withdrawals, setWithdrawals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState<any>(null);
  const [proofImage, setProofImage] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    loadWithdrawals();
  }, []);

  const loadWithdrawals = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/withdrawals/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setWithdrawals(response.data || []);
    } catch (error) {
      console.error('Error loading withdrawals:', error);
    } finally {
      setLoading(false);
    }
  };

  const pickProofImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.7,
      base64: true,
    });

    if (!result.canceled && result.assets[0]) {
      setProofImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
    }
  };

  const processWithdrawal = async (action: 'approve' | 'reject') => {
    if (!selectedTx) return;
    if (action === 'approve' && !proofImage) {
      showAlert('Error', 'Debes adjuntar el comprobante de pago');
      return;
    }

    setProcessing(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/withdrawals/process`,
        {
          transaction_id: selectedTx.transaction_id,
          action,
          proof_image: proofImage,
          rejection_reason: action === 'reject' ? 'Rechazado por administrador' : undefined,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      showAlert('Éxito', action === 'approve' ? 'Retiro aprobado' : 'Retiro rechazado');
      setSelectedTx(null);
      setProofImage(null);
      loadWithdrawals();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    } finally {
      setProcessing(false);
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Retiros Pendientes</Text>
        <View style={styles.countBadge}>
          <Text style={styles.countText}>{withdrawals.length}</Text>
        </View>
      </View>
      
      {withdrawals.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle" size={64} color="#10b981" />
          <Text style={styles.emptyTitle}>¡Todo al día!</Text>
          <Text style={styles.emptyText}>No hay retiros pendientes</Text>
        </View>
      ) : (
        withdrawals.map((tx) => (
          <TouchableOpacity key={tx.transaction_id} style={styles.txCard} onPress={() => setSelectedTx(tx)}>
            <View style={styles.txCardHeader}>
              <View>
                <Text style={styles.txAmount}>{tx.amount_input?.toFixed(2)} RIS</Text>
                <Text style={styles.txConversion}>→ {tx.amount_output?.toFixed(2)} VES</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
            </View>
            <View style={styles.txCardBody}>
              <View style={styles.txInfoRow}>
                <Ionicons name="person" size={14} color="#6b7280" />
                <Text style={styles.txInfoText}>{tx.user_name}</Text>
              </View>
              <View style={styles.txInfoRow}>
                <Ionicons name="business" size={14} color="#6b7280" />
                <Text style={styles.txInfoText}>{tx.beneficiary_data?.bank_code} - {tx.beneficiary_data?.bank}</Text>
              </View>
              <View style={styles.txInfoRow}>
                <Ionicons name="card" size={14} color="#6b7280" />
                <Text style={styles.txInfoText}>{tx.beneficiary_data?.account_number}</Text>
              </View>
            </View>
          </TouchableOpacity>
        ))
      )}

      {/* Process Modal */}
      <Modal visible={!!selectedTx} animationType="slide" transparent>
        <KeyboardAvoidingView style={styles.modalOverlay} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Procesar Retiro</Text>
              <TouchableOpacity onPress={() => { setSelectedTx(null); setProofImage(null); }} style={styles.modalClose}>
                <Ionicons name="close" size={24} color="#6b7280" />
              </TouchableOpacity>
            </View>

            {selectedTx && (
              <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
                <View style={styles.amountBox}>
                  <Text style={styles.amountLabel}>Monto a Transferir</Text>
                  <Text style={styles.amountValue}>{selectedTx.amount_output?.toFixed(2)} VES</Text>
                  <Text style={styles.amountSub}>{selectedTx.amount_input?.toFixed(2)} RIS</Text>
                </View>
                
                <View style={styles.beneficiaryBox}>
                  <Text style={styles.beneficiaryTitle}>Datos del Beneficiario</Text>
                  <View style={styles.beneficiaryRow}>
                    <Text style={styles.beneficiaryLabel}>Banco:</Text>
                    <Text style={styles.beneficiaryValue}>{selectedTx.beneficiary_data?.bank_code} - {selectedTx.beneficiary_data?.bank}</Text>
                  </View>
                  <View style={styles.beneficiaryRow}>
                    <Text style={styles.beneficiaryLabel}>Cuenta:</Text>
                    <Text style={styles.beneficiaryValue}>{selectedTx.beneficiary_data?.account_number}</Text>
                  </View>
                  <View style={styles.beneficiaryRow}>
                    <Text style={styles.beneficiaryLabel}>Titular:</Text>
                    <Text style={styles.beneficiaryValue}>{selectedTx.beneficiary_data?.full_name}</Text>
                  </View>
                  <View style={styles.beneficiaryRow}>
                    <Text style={styles.beneficiaryLabel}>Cédula:</Text>
                    <Text style={styles.beneficiaryValue}>{selectedTx.beneficiary_data?.id_document}</Text>
                  </View>
                  <View style={styles.beneficiaryRow}>
                    <Text style={styles.beneficiaryLabel}>Teléfono:</Text>
                    <Text style={styles.beneficiaryValue}>{selectedTx.beneficiary_data?.phone_number}</Text>
                  </View>
                </View>

                <TouchableOpacity style={styles.uploadButton} onPress={pickProofImage}>
                  <Ionicons name={proofImage ? 'checkmark-circle' : 'camera'} size={24} color={proofImage ? '#10b981' : '#2563eb'} />
                  <Text style={[styles.uploadButtonText, proofImage && { color: '#10b981' }]}>
                    {proofImage ? 'Comprobante Cargado ✓' : 'Subir Comprobante'}
                  </Text>
                </TouchableOpacity>

                {proofImage && (
                  <Image source={{ uri: proofImage }} style={styles.proofPreview} resizeMode="contain" />
                )}

                <View style={styles.actionButtons}>
                  <TouchableOpacity
                    style={[styles.actionButton, styles.rejectButton]}
                    onPress={() => processWithdrawal('reject')}
                    disabled={processing}
                  >
                    <Ionicons name="close-circle" size={20} color="#fff" />
                    <Text style={styles.actionButtonText}>Rechazar</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.actionButton, styles.approveButton, !proofImage && styles.disabledButton]}
                    onPress={() => processWithdrawal('approve')}
                    disabled={processing || !proofImage}
                  >
                    {processing ? (
                      <ActivityIndicator color="#fff" size="small" />
                    ) : (
                      <>
                        <Ionicons name="checkmark-circle" size={20} color="#fff" />
                        <Text style={styles.actionButtonText}>Aprobar</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              </ScrollView>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

// Recharges Tab
function RechargesTab() {
  const [recharges, setRecharges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);

  useEffect(() => {
    loadRecharges();
  }, []);

  const loadRecharges = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/recharges/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setRecharges(response.data.recharges || []);
    } catch (error) {
      console.error('Error loading recharges:', error);
    } finally {
      setLoading(false);
    }
  };

  const processRecharge = async (txId: string, approved: boolean) => {
    setProcessing(txId);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/recharges/approve`,
        { transaction_id: txId, approved },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', approved ? 'Recarga aprobada' : 'Recarga rechazada');
      loadRecharges();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    } finally {
      setProcessing(null);
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recargas Pendientes</Text>
        <View style={styles.countBadge}>
          <Text style={styles.countText}>{recharges.length}</Text>
        </View>
      </View>
      
      {recharges.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle" size={64} color="#10b981" />
          <Text style={styles.emptyTitle}>¡Todo al día!</Text>
          <Text style={styles.emptyText}>No hay recargas pendientes</Text>
        </View>
      ) : (
        recharges.map((tx) => (
          <View key={tx.transaction_id} style={styles.rechargeCard}>
            <View style={styles.rechargeHeader}>
              <View>
                <Text style={styles.rechargeAmount}>R$ {tx.amount_input?.toFixed(2)}</Text>
                <Text style={styles.rechargeUser}>{tx.user_name}</Text>
              </View>
              <Text style={styles.rechargeRis}>+{tx.amount_output?.toFixed(2)} RIS</Text>
            </View>
            <View style={styles.rechargeActions}>
              <TouchableOpacity 
                style={[styles.rechargeBtn, styles.rejectBtn]} 
                onPress={() => processRecharge(tx.transaction_id, false)}
                disabled={processing === tx.transaction_id}
              >
                {processing === tx.transaction_id ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.rechargeBtnText}>Rechazar</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.rechargeBtn, styles.approveBtn]} 
                onPress={() => processRecharge(tx.transaction_id, true)}
                disabled={processing === tx.transaction_id}
              >
                {processing === tx.transaction_id ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.rechargeBtnText}>Aprobar</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        ))
      )}
    </View>
  );
}

// Support Tab
function SupportTab() {
  const [chats, setChats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedChat, setSelectedChat] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [responseText, setResponseText] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/support/chats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setChats(response.data);
    } catch (error) {
      console.error('Error loading chats:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadChatDetail = async (userId: string) => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/support/chat/${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSelectedChat(response.data);
      setMessages(response.data.messages);
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  };

  const sendResponse = async () => {
    if (!responseText.trim() || !selectedChat) return;

    setSending(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/support/respond`,
        { user_id: selectedChat.user_id, message: responseText.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setResponseText('');
      loadChatDetail(selectedChat.user_id);
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo enviar');
    } finally {
      setSending(false);
    }
  };

  const closeChat = async () => {
    if (!selectedChat) return;
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/support/close`,
        { user_id: selectedChat.user_id },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', 'Chat cerrado');
      setSelectedChat(null);
      loadChats();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo cerrar');
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  if (selectedChat) {
    return (
      <View style={styles.chatDetail}>
        <View style={styles.chatDetailHeader}>
          <TouchableOpacity onPress={() => setSelectedChat(null)} style={styles.chatBackBtn}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <View style={styles.chatDetailInfo}>
            <Text style={styles.chatDetailName}>{selectedChat.user_name}</Text>
            <Text style={styles.chatDetailEmail}>{selectedChat.user_email}</Text>
          </View>
          <TouchableOpacity style={styles.closeChatBtn} onPress={closeChat}>
            <Text style={styles.closeChatBtnText}>Cerrar</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.messagesContainer} contentContainerStyle={styles.messagesContent}>
          {messages.map((msg) => (
            <View key={msg.id} style={[styles.message, msg.sender === 'admin' ? styles.adminMessage : styles.userMessage]}>
              {msg.image && <Image source={{ uri: msg.image }} style={styles.messageImage} />}
              <Text style={[styles.messageText, msg.sender === 'admin' && styles.adminMessageText]}>{msg.text}</Text>
            </View>
          ))}
        </ScrollView>

        <View style={styles.responseContainer}>
          <TextInput
            style={styles.responseInput}
            value={responseText}
            onChangeText={setResponseText}
            placeholder="Escribe tu respuesta..."
            multiline
          />
          <TouchableOpacity style={styles.sendButton} onPress={sendResponse} disabled={sending}>
            {sending ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="send" size={20} color="#fff" />}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Chats de Soporte</Text>
        <View style={styles.countBadge}>
          <Text style={styles.countText}>{chats.length}</Text>
        </View>
      </View>
      
      {chats.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="chatbubbles-outline" size={64} color="#9ca3af" />
          <Text style={styles.emptyTitle}>Sin mensajes</Text>
          <Text style={styles.emptyText}>No hay chats de soporte</Text>
        </View>
      ) : (
        chats.map((chat) => (
          <TouchableOpacity key={chat.user_id} style={styles.chatCard} onPress={() => loadChatDetail(chat.user_id)}>
            <View style={styles.chatCardHeader}>
              <View style={styles.chatAvatar}>
                <Text style={styles.chatAvatarText}>{chat.user_name?.charAt(0)?.toUpperCase()}</Text>
              </View>
              <View style={styles.chatCardInfo}>
                <Text style={styles.chatCardName}>{chat.user_name}</Text>
                <Text style={styles.chatCardPreview} numberOfLines={1}>{chat.last_message}</Text>
              </View>
              <View style={styles.chatCardMeta}>
                <View style={[styles.chatStatusBadge, chat.status === 'closed' ? styles.statusClosed : styles.statusOpen]}>
                  <Text style={styles.chatStatusText}>{chat.status === 'closed' ? 'Cerrado' : 'Abierto'}</Text>
                </View>
                <Text style={styles.chatCardCount}>{chat.message_count} msgs</Text>
              </View>
            </View>
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}

// Users Tab
function UsersTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [stats, setStats] = useState<{ total: number; online: number; verified: number }>({ total: 0, online: 0, verified: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadUsers();
    // Auto-refresh every 30 seconds for online status
    const interval = setInterval(loadUsers, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadUsers = async (searchTerm?: string) => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const url = searchTerm 
        ? `${BACKEND_URL}/api/admin/users?search=${searchTerm}`
        : `${BACKEND_URL}/api/admin/users`;
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setUsers(response.data.users);
      setStats(response.data.stats);
    } catch (error) {
      console.error('Error loading users:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatLastSeen = (lastSeen: string) => {
    if (!lastSeen) return 'Nunca';
    const date = new Date(lastSeen);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 2) return 'Ahora';
    if (diffMins < 60) return `Hace ${diffMins} min`;
    if (diffMins < 1440) return `Hace ${Math.floor(diffMins / 60)} hrs`;
    return `Hace ${Math.floor(diffMins / 1440)} días`;
  };

  return (
    <View style={styles.tabContent}>
      {/* Stats Cards */}
      <View style={styles.userStatsRow}>
        <View style={[styles.userStatCard, { backgroundColor: '#eff6ff' }]}>
          <Ionicons name="people" size={20} color="#2563eb" />
          <Text style={[styles.userStatValue, { color: '#2563eb' }]}>{stats.total}</Text>
          <Text style={styles.userStatLabel}>Total</Text>
        </View>
        <View style={[styles.userStatCard, { backgroundColor: '#ecfdf5' }]}>
          <View style={styles.onlineDotLarge} />
          <Text style={[styles.userStatValue, { color: '#059669' }]}>{stats.online}</Text>
          <Text style={styles.userStatLabel}>En línea</Text>
        </View>
        <View style={[styles.userStatCard, { backgroundColor: '#fef3c7' }]}>
          <Ionicons name="shield-checkmark" size={20} color="#d97706" />
          <Text style={[styles.userStatValue, { color: '#d97706' }]}>{stats.verified}</Text>
          <Text style={styles.userStatLabel}>Verificados</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>Lista de Usuarios</Text>
      
      <View style={styles.searchBox}>
        <Ionicons name="search" size={20} color="#9ca3af" />
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por nombre o email..."
          onSubmitEditing={() => loadUsers(search)}
          returnKeyType="search"
        />
        {search.length > 0 && (
          <TouchableOpacity onPress={() => { setSearch(''); loadUsers(); }}>
            <Ionicons name="close-circle" size={20} color="#9ca3af" />
          </TouchableOpacity>
        )}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 20 }} />
      ) : users.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="people-outline" size={48} color="#9ca3af" />
          <Text style={styles.emptyStateText}>No hay usuarios registrados</Text>
        </View>
      ) : (
        users.map((u) => (
          <View key={u.user_id} style={styles.userCard}>
            <View style={styles.userCardHeader}>
              <View style={styles.userAvatarContainer}>
                <View style={styles.userAvatar}>
                  <Text style={styles.userAvatarText}>{u.name?.charAt(0)?.toUpperCase() || '?'}</Text>
                </View>
                {u.is_online && <View style={styles.onlineIndicator} />}
              </View>
              <View style={styles.userCardInfo}>
                <View style={styles.userNameRow}>
                  <Text style={styles.userCardName}>{u.name || 'Sin nombre'}</Text>
                  {u.role === 'super_admin' && (
                    <View style={styles.adminBadge}>
                      <Text style={styles.adminBadgeText}>Super</Text>
                    </View>
                  )}
                  {u.role === 'admin' && (
                    <View style={[styles.adminBadge, { backgroundColor: '#dbeafe' }]}>
                      <Text style={[styles.adminBadgeText, { color: '#2563eb' }]}>Admin</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.userCardEmail}>{u.email}</Text>
                <Text style={styles.userLastSeen}>
                  {u.is_online ? '🟢 En línea' : `⚫ ${formatLastSeen(u.last_seen)}`}
                </Text>
              </View>
            </View>
            <View style={styles.userCardFooter}>
              <View style={styles.userFooterLeft}>
                <Text style={styles.userBalance}>{u.balance_ris?.toFixed(2) || '0.00'} RIS</Text>
                {u.email_verified && (
                  <View style={styles.emailVerifiedBadge}>
                    <Ionicons name="mail" size={10} color="#059669" />
                    <Text style={styles.emailVerifiedText}>Email</Text>
                  </View>
                )}
              </View>
              <View style={[
                styles.verificationBadge, 
                u.verification_status === 'verified' ? styles.badgeVerified : 
                u.verification_status === 'pending' ? styles.badgePending : styles.badgeNone
              ]}>
                <Text style={[
                  styles.verificationBadgeText,
                  u.verification_status === 'verified' ? styles.textVerified : 
                  u.verification_status === 'pending' ? styles.textPending : styles.textNone
                ]}>
                  {u.verification_status === 'verified' ? '✓ KYC Verificado' : 
                   u.verification_status === 'pending' ? '⏳ KYC Pendiente' : '○ Sin KYC'}
                </Text>
              </View>
            </View>
          </View>
        ))
      )}
    </View>
  );
}

// Admins Tab (Super Admin Only)
function AdminsTab() {
  const [admins, setAdmins] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [permissions, setPermissions] = useState<Record<string, string>>({});
  const [showCreate, setShowCreate] = useState(false);
  const [newAdmin, setNewAdmin] = useState({ email: '', name: '', permissions: [] as string[] });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadAdmins();
    loadPermissions();
  }, []);

  const loadAdmins = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/sub-admins`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAdmins(response.data);
    } catch (error) {
      console.error('Error loading admins:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadPermissions = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/permissions-list`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPermissions(response.data);
    } catch (error) {
      console.error('Error loading permissions:', error);
    }
  };

  const createAdmin = async () => {
    if (!newAdmin.email || !newAdmin.name) {
      showAlert('Error', 'Completa todos los campos');
      return;
    }
    setCreating(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/sub-admins`,
        newAdmin,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', 'Administrador creado');
      setShowCreate(false);
      setNewAdmin({ email: '', name: '', permissions: [] });
      loadAdmins();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo crear');
    } finally {
      setCreating(false);
    }
  };

  const togglePermission = (perm: string) => {
    setNewAdmin(prev => ({
      ...prev,
      permissions: prev.permissions.includes(perm)
        ? prev.permissions.filter(p => p !== perm)
        : [...prev.permissions, perm]
    }));
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Administradores</Text>
        <TouchableOpacity style={styles.addButton} onPress={() => setShowCreate(true)}>
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {admins.map((admin) => (
        <View key={admin.user_id} style={styles.adminCard}>
          <View style={styles.adminCardHeader}>
            <View style={[styles.adminAvatar, admin.role === 'super_admin' && styles.superAdminAvatar]}>
              <Ionicons name={admin.role === 'super_admin' ? 'shield' : 'person'} size={20} color="#fff" />
            </View>
            <View style={styles.adminCardInfo}>
              <Text style={styles.adminCardName}>{admin.name}</Text>
              <Text style={styles.adminCardEmail}>{admin.email}</Text>
            </View>
            <View style={[styles.adminRoleBadge, admin.role === 'super_admin' && styles.superBadge]}>
              <Text style={styles.adminRoleText}>{admin.role === 'super_admin' ? 'Super' : 'Admin'}</Text>
            </View>
          </View>
        </View>
      ))}

      {/* Create Admin Modal */}
      <Modal visible={showCreate} animationType="slide" transparent>
        <KeyboardAvoidingView style={styles.modalOverlay} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Nuevo Admin</Text>
              <TouchableOpacity onPress={() => setShowCreate(false)} style={styles.modalClose}>
                <Ionicons name="close" size={24} color="#6b7280" />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalBody}>
              <Text style={styles.inputLabel}>Email</Text>
              <TextInput
                style={styles.textInput}
                value={newAdmin.email}
                onChangeText={(v) => setNewAdmin(p => ({ ...p, email: v }))}
                placeholder="email@ejemplo.com"
                keyboardType="email-address"
                autoCapitalize="none"
              />
              <Text style={styles.inputLabel}>Nombre</Text>
              <TextInput
                style={styles.textInput}
                value={newAdmin.name}
                onChangeText={(v) => setNewAdmin(p => ({ ...p, name: v }))}
                placeholder="Nombre completo"
              />
              <Text style={styles.inputLabel}>Permisos ({newAdmin.permissions.length} seleccionados)</Text>
              <View style={styles.permissionsGrid}>
                {Object.entries(permissions).map(([key, label]) => (
                  <TouchableOpacity 
                    key={key} 
                    style={[styles.permissionChip, newAdmin.permissions.includes(key) && styles.permissionChipActive]} 
                    onPress={() => togglePermission(key)}
                  >
                    <Text style={[styles.permissionChipText, newAdmin.permissions.includes(key) && styles.permissionChipTextActive]}>
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity style={styles.createButton} onPress={createAdmin} disabled={creating}>
                {creating ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.createButtonText}>Crear Administrador</Text>
                )}
              </TouchableOpacity>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

// Settings Tab
function SettingsTab({ currentRate, onRateUpdated }: { currentRate: number; onRateUpdated: () => void }) {
  const [rate, setRate] = useState(currentRate.toString());
  const [saving, setSaving] = useState(false);

  const saveRate = async () => {
    const newRate = parseFloat(rate);
    if (isNaN(newRate) || newRate <= 0) {
      showAlert('Error', 'Ingresa una tasa válida');
      return;
    }
    setSaving(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/rate`,
        { ris_to_ves: newRate },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', 'Tasa actualizada');
      onRateUpdated();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Configuración</Text>
      
      <View style={styles.settingCard}>
        <View style={styles.settingHeader}>
          <Ionicons name="swap-horizontal" size={24} color="#2563eb" />
          <Text style={styles.settingTitle}>Tasa de Cambio</Text>
        </View>
        <Text style={styles.settingDesc}>1 RIS equivale a:</Text>
        <View style={styles.rateInputRow}>
          <TextInput
            style={styles.rateInput}
            value={rate}
            onChangeText={setRate}
            keyboardType="numeric"
            placeholder="0"
          />
          <Text style={styles.rateUnit}>VES</Text>
        </View>
        <TouchableOpacity style={styles.saveButton} onPress={saveRate} disabled={saving}>
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="save" size={18} color="#fff" />
              <Text style={styles.saveButtonText}>Guardar</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, color: '#6b7280', fontSize: 14 },
  
  // Header
  header: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between', 
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#fff', 
    borderBottomWidth: 1, 
    borderBottomColor: '#e5e7eb' 
  },
  backButton: { padding: 8 },
  headerCenter: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#1f2937' },
  roleBadge: { backgroundColor: '#dbeafe', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  superBadge: { backgroundColor: '#fef3c7' },
  roleBadgeText: { fontSize: 11, fontWeight: '600', color: '#1f2937' },
  refreshButton: { padding: 8 },

  // Content
  content: { flex: 1 },
  contentContainer: { paddingBottom: 100 },
  tabContent: { padding: 16 },

  // Bottom Navigation
  bottomNav: { 
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#fff', 
    borderTopWidth: 1, 
    borderTopColor: '#e5e7eb',
    paddingBottom: Platform.OS === 'ios' ? 20 : 8,
  },
  bottomNavContent: { 
    flexDirection: 'row',
    paddingHorizontal: 8,
    paddingTop: 8,
  },
  navItem: { 
    alignItems: 'center', 
    paddingHorizontal: 12,
    paddingVertical: 6,
    minWidth: 60,
  },
  navItemActive: {},
  navIconContainer: { position: 'relative' },
  navBadge: { 
    position: 'absolute', 
    top: -6, 
    right: -10, 
    backgroundColor: '#ef4444', 
    borderRadius: 10, 
    minWidth: 18, 
    height: 18, 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  navBadgeText: { color: '#fff', fontSize: 10, fontWeight: 'bold' },
  navLabel: { fontSize: 11, color: '#6b7280', marginTop: 4 },
  navLabelActive: { color: '#2563eb', fontWeight: '600' },

  // Section Headers
  sectionTitle: { fontSize: 20, fontWeight: '700', color: '#1f2937', marginBottom: 16 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  countBadge: { backgroundColor: '#2563eb', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  countText: { color: '#fff', fontSize: 12, fontWeight: '600' },

  // Quick Stats
  quickStatsRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 24 },
  quickStat: { alignItems: 'center', flex: 1 },
  quickStatIcon: { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center', marginBottom: 6, position: 'relative' },
  quickStatDot: { position: 'absolute', top: 0, right: 0, width: 10, height: 10, borderRadius: 5, borderWidth: 2, borderColor: '#fff' },
  quickStatValue: { fontSize: 18, fontWeight: '700', color: '#1f2937' },
  quickStatLabel: { fontSize: 11, color: '#6b7280' },

  // Stats Grid
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -6, marginBottom: 16 },
  statCard: { 
    width: (SCREEN_WIDTH - 56) / 2, 
    backgroundColor: '#fff', 
    borderRadius: 12, 
    padding: 16, 
    margin: 6,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  statValue: { fontSize: 28, fontWeight: '700', color: '#1f2937', marginTop: 8 },
  statTitle: { fontSize: 12, color: '#6b7280', marginTop: 4, textAlign: 'center' },

  // Volume Card
  volumeCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginTop: 8 },
  volumeTitle: { fontSize: 14, fontWeight: '600', color: '#6b7280', marginBottom: 12 },
  volumeGrid: { flexDirection: 'row', alignItems: 'center' },
  volumeItem: { flex: 1, alignItems: 'center' },
  volumeValue: { fontSize: 24, fontWeight: '700', color: '#1f2937' },
  volumeLabel: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  volumeDivider: { width: 1, height: 40, backgroundColor: '#e5e7eb', marginHorizontal: 16 },

  // Empty State
  emptyState: { alignItems: 'center', paddingVertical: 48 },
  emptyTitle: { fontSize: 18, fontWeight: '600', color: '#1f2937', marginTop: 16 },
  emptyText: { fontSize: 14, color: '#6b7280', marginTop: 4 },

  // Transaction Cards
  txCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  txCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  txAmount: { fontSize: 20, fontWeight: '700', color: '#1f2937' },
  txConversion: { fontSize: 14, color: '#10b981', fontWeight: '500' },
  txCardBody: { gap: 6 },
  txInfoRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  txInfoText: { fontSize: 13, color: '#4b5563' },

  // Recharge Cards
  rechargeCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12 },
  rechargeHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  rechargeAmount: { fontSize: 20, fontWeight: '700', color: '#1f2937' },
  rechargeUser: { fontSize: 13, color: '#6b7280' },
  rechargeRis: { fontSize: 16, fontWeight: '600', color: '#10b981' },
  rechargeActions: { flexDirection: 'row', gap: 12 },
  rechargeBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  rejectBtn: { backgroundColor: '#fef2f2', borderWidth: 1, borderColor: '#fecaca' },
  approveBtn: { backgroundColor: '#10b981' },
  rechargeBtnText: { fontWeight: '600', color: '#fff' },

  // Modals
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: '#fff', borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '92%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  modalTitle: { fontSize: 18, fontWeight: '700', color: '#1f2937' },
  modalClose: { padding: 4 },
  modalBody: { padding: 16 },

  // Amount Box
  amountBox: { backgroundColor: '#f0fdf4', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 16 },
  amountLabel: { fontSize: 12, color: '#6b7280' },
  amountValue: { fontSize: 32, fontWeight: '700', color: '#10b981', marginTop: 4 },
  amountSub: { fontSize: 14, color: '#6b7280', marginTop: 4 },

  // Beneficiary Box
  beneficiaryBox: { backgroundColor: '#f8fafc', borderRadius: 12, padding: 16, marginBottom: 16 },
  beneficiaryTitle: { fontSize: 14, fontWeight: '600', color: '#1f2937', marginBottom: 12 },
  beneficiaryRow: { flexDirection: 'row', marginBottom: 8 },
  beneficiaryLabel: { width: 80, fontSize: 13, color: '#6b7280' },
  beneficiaryValue: { flex: 1, fontSize: 13, color: '#1f2937', fontWeight: '500' },

  // Upload Button
  uploadButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 16, borderWidth: 2, borderStyle: 'dashed', borderColor: '#d1d5db', borderRadius: 12, marginBottom: 16, gap: 8 },
  uploadButtonText: { fontSize: 14, fontWeight: '600', color: '#6b7280' },
  proofPreview: { width: '100%', height: 180, borderRadius: 12, marginBottom: 16, backgroundColor: '#f3f4f6' },

  // Action Buttons
  actionButtons: { flexDirection: 'row', gap: 12, marginBottom: 24 },
  actionButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 10, gap: 6 },
  approveButton: { backgroundColor: '#10b981' },
  rejectButton: { backgroundColor: '#ef4444' },
  disabledButton: { backgroundColor: '#d1d5db' },
  actionButtonText: { color: '#fff', fontWeight: '600', fontSize: 15 },

  // Chat
  chatCard: { backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 10 },
  chatCardHeader: { flexDirection: 'row', alignItems: 'center' },
  chatAvatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },
  chatAvatarText: { color: '#fff', fontSize: 18, fontWeight: '600' },
  chatCardInfo: { flex: 1, marginLeft: 12 },
  chatCardName: { fontSize: 15, fontWeight: '600', color: '#1f2937' },
  chatCardPreview: { fontSize: 13, color: '#6b7280', marginTop: 2 },
  chatCardMeta: { alignItems: 'flex-end' },
  chatStatusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 },
  statusOpen: { backgroundColor: '#fef3c7' },
  statusClosed: { backgroundColor: '#d1fae5' },
  chatStatusText: { fontSize: 11, fontWeight: '500' },
  chatCardCount: { fontSize: 11, color: '#9ca3af', marginTop: 4 },

  // Chat Detail
  chatDetail: { flex: 1 },
  chatDetailHeader: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  chatBackBtn: { padding: 4 },
  chatDetailInfo: { flex: 1, marginLeft: 12 },
  chatDetailName: { fontSize: 16, fontWeight: '600', color: '#1f2937' },
  chatDetailEmail: { fontSize: 12, color: '#6b7280' },
  closeChatBtn: { backgroundColor: '#ef4444', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  closeChatBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  messagesContainer: { flex: 1, padding: 16 },
  messagesContent: { paddingBottom: 16 },
  message: { padding: 12, borderRadius: 16, marginBottom: 8, maxWidth: '85%' },
  userMessage: { backgroundColor: '#f3f4f6', alignSelf: 'flex-start', borderBottomLeftRadius: 4 },
  adminMessage: { backgroundColor: '#2563eb', alignSelf: 'flex-end', borderBottomRightRadius: 4 },
  messageImage: { width: 180, height: 120, borderRadius: 8, marginBottom: 8 },
  messageText: { fontSize: 14, color: '#1f2937', lineHeight: 20 },
  adminMessageText: { color: '#fff' },
  responseContainer: { flexDirection: 'row', alignItems: 'flex-end', padding: 12, gap: 8, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e5e7eb' },
  responseInput: { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, maxHeight: 100, fontSize: 14 },
  sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },

  // Users
  searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 10, paddingHorizontal: 12, marginBottom: 16, height: 44 },
  searchInput: { flex: 1, marginLeft: 8, fontSize: 14 },
  userCard: { backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 10 },
  userCardHeader: { flexDirection: 'row', alignItems: 'center' },
  userAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#e5e7eb', justifyContent: 'center', alignItems: 'center' },
  userAvatarText: { color: '#6b7280', fontSize: 16, fontWeight: '600' },
  userCardInfo: { flex: 1, marginLeft: 12 },
  userCardName: { fontSize: 15, fontWeight: '600', color: '#1f2937' },
  userCardEmail: { fontSize: 12, color: '#6b7280' },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  dotVerified: { backgroundColor: '#10b981' },
  dotPending: { backgroundColor: '#f59e0b' },
  userCardFooter: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#f3f4f6' },
  userBalance: { fontSize: 14, fontWeight: '600', color: '#2563eb' },
  userStatus: { fontSize: 12, color: '#6b7280' },

  // Admins
  addButton: { backgroundColor: '#2563eb', width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
  adminCard: { backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 10 },
  adminCardHeader: { flexDirection: 'row', alignItems: 'center' },
  adminAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },
  superAdminAvatar: { backgroundColor: '#f59e0b' },
  adminCardInfo: { flex: 1, marginLeft: 12 },
  adminCardName: { fontSize: 15, fontWeight: '600', color: '#1f2937' },
  adminCardEmail: { fontSize: 12, color: '#6b7280' },
  adminRoleBadge: { backgroundColor: '#dbeafe', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  adminRoleText: { fontSize: 12, fontWeight: '600', color: '#1f2937' },

  // Forms
  inputLabel: { fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 8, marginTop: 16 },
  textInput: { backgroundColor: '#f9fafb', borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 10, padding: 14, fontSize: 15 },
  permissionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  permissionChip: { backgroundColor: '#f3f4f6', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#e5e7eb' },
  permissionChipActive: { backgroundColor: '#dbeafe', borderColor: '#2563eb' },
  permissionChipText: { fontSize: 12, color: '#6b7280' },
  permissionChipTextActive: { color: '#2563eb', fontWeight: '500' },
  createButton: { backgroundColor: '#2563eb', padding: 16, borderRadius: 10, alignItems: 'center', marginTop: 24, marginBottom: 32, flexDirection: 'row', justifyContent: 'center', gap: 8 },
  createButtonText: { color: '#fff', fontWeight: '600', fontSize: 16 },

  // Settings
  settingCard: { backgroundColor: '#fff', borderRadius: 12, padding: 20 },
  settingHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
  settingTitle: { fontSize: 18, fontWeight: '600', color: '#1f2937' },
  settingDesc: { fontSize: 14, color: '#6b7280', marginBottom: 12 },
  rateInputRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  rateInput: { flex: 1, backgroundColor: '#f9fafb', borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 10, padding: 16, fontSize: 28, fontWeight: '700', textAlign: 'center' },
  rateUnit: { fontSize: 20, fontWeight: '600', color: '#6b7280' },
  saveButton: { backgroundColor: '#2563eb', padding: 14, borderRadius: 10, alignItems: 'center', marginTop: 20, flexDirection: 'row', justifyContent: 'center', gap: 8 },
  saveButtonText: { color: '#fff', fontWeight: '600', fontSize: 15 },

  // Users Tab - Enhanced
  userStatsRow: { flexDirection: 'row', gap: 10, marginBottom: 20 },
  userStatCard: { flex: 1, borderRadius: 12, padding: 12, alignItems: 'center' },
  userStatValue: { fontSize: 24, fontWeight: '700', marginTop: 4 },
  userStatLabel: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  onlineDotLarge: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#10b981' },
  userAvatarContainer: { position: 'relative' },
  onlineIndicator: { position: 'absolute', bottom: 0, right: 0, width: 14, height: 14, borderRadius: 7, backgroundColor: '#10b981', borderWidth: 2, borderColor: '#fff' },
  userNameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  adminBadge: { backgroundColor: '#fef3c7', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  adminBadgeText: { fontSize: 9, fontWeight: '700', color: '#d97706' },
  userLastSeen: { fontSize: 11, color: '#9ca3af', marginTop: 2 },
  userFooterLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  emailVerifiedBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: '#ecfdf5', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  emailVerifiedText: { fontSize: 9, color: '#059669', fontWeight: '600' },
  verificationBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  badgeVerified: { backgroundColor: '#ecfdf5' },
  badgePending: { backgroundColor: '#fef3c7' },
  badgeNone: { backgroundColor: '#f3f4f6' },
  verificationBadgeText: { fontSize: 11, fontWeight: '600' },
  textVerified: { color: '#059669' },
  textPending: { color: '#d97706' },
  textNone: { color: '#6b7280' },
  emptyStateText: { fontSize: 14, color: '#6b7280', marginTop: 12 },
});
