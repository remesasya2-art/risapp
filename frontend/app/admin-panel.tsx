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
  FlatList,
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
      
      // Get user role
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
          <Text style={styles.loadingText}>Cargando panel de administración...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#1f2937" />
        </TouchableOpacity>
        <View>
          <Text style={styles.headerTitle}>Panel de Administración</Text>
          <Text style={styles.roleText}>{userRole === 'super_admin' ? 'Super Admin' : 'Admin'}</Text>
        </View>
        <TouchableOpacity onPress={onRefresh}>
          <Ionicons name="refresh" size={24} color="#2563eb" />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabsContainer}>
        <TabButton icon="speedometer" label="Dashboard" active={activeTab === 'dashboard'} onPress={() => setActiveTab('dashboard')} />
        <TabButton icon="arrow-up-circle" label="Retiros" active={activeTab === 'withdrawals'} onPress={() => setActiveTab('withdrawals')} badge={dashboard?.transactions.pending_withdrawals} />
        <TabButton icon="arrow-down-circle" label="Recargas" active={activeTab === 'recharges'} onPress={() => setActiveTab('recharges')} badge={dashboard?.transactions.pending_recharges} />
        <TabButton icon="chatbubbles" label="Soporte" active={activeTab === 'support'} onPress={() => setActiveTab('support')} badge={dashboard?.support.open_chats} />
        <TabButton icon="people" label="Usuarios" active={activeTab === 'users'} onPress={() => setActiveTab('users')} />
        {userRole === 'super_admin' && (
          <TabButton icon="shield" label="Admins" active={activeTab === 'admins'} onPress={() => setActiveTab('admins')} />
        )}
        <TabButton icon="settings" label="Config" active={activeTab === 'settings'} onPress={() => setActiveTab('settings')} />
      </ScrollView>

      {/* Content */}
      <ScrollView
        style={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {activeTab === 'dashboard' && <DashboardTab data={dashboard} />}
        {activeTab === 'withdrawals' && <WithdrawalsTab />}
        {activeTab === 'recharges' && <RechargesTab />}
        {activeTab === 'support' && <SupportTab />}
        {activeTab === 'users' && <UsersTab />}
        {activeTab === 'admins' && userRole === 'super_admin' && <AdminsTab />}
        {activeTab === 'settings' && <SettingsTab currentRate={dashboard?.current_rate || 78} />}
      </ScrollView>
    </SafeAreaView>
  );
}

// Tab Button Component
function TabButton({ icon, label, active, onPress, badge }: { icon: string; label: string; active: boolean; onPress: () => void; badge?: number }) {
  return (
    <TouchableOpacity style={[styles.tabButton, active && styles.tabButtonActive]} onPress={onPress}>
      <View style={styles.tabIconContainer}>
        <Ionicons name={icon as any} size={20} color={active ? '#2563eb' : '#6b7280'} />
        {badge !== undefined && badge > 0 && (
          <View style={styles.tabBadge}>
            <Text style={styles.tabBadgeText}>{badge}</Text>
          </View>
        )}
      </View>
      <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

// Dashboard Tab
function DashboardTab({ data }: { data: DashboardData | null }) {
  if (!data) return null;

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Resumen General</Text>
      
      <View style={styles.statsGrid}>
        <StatCard icon="people" title="Usuarios" value={data.users.total} color="#2563eb" subtitle={`${data.users.verified} verificados`} />
        <StatCard icon="checkmark-circle" title="KYC Pendiente" value={data.users.pending_kyc} color="#f59e0b" />
        <StatCard icon="arrow-up-circle" title="Retiros Pend." value={data.transactions.pending_withdrawals} color="#ef4444" />
        <StatCard icon="arrow-down-circle" title="Recargas Pend." value={data.transactions.pending_recharges} color="#10b981" />
        <StatCard icon="chatbubbles" title="Chats Abiertos" value={data.support.open_chats} color="#8b5cf6" />
        <StatCard icon="swap-horizontal" title="Tasa Actual" value={data.current_rate} color="#06b6d4" subtitle="VES/RIS" />
      </View>

      <Text style={styles.sectionTitle}>Volumen de Transacciones</Text>
      <View style={styles.volumeCard}>
        <View style={styles.volumeRow}>
          <Text style={styles.volumeLabel}>Total Retiros:</Text>
          <Text style={styles.volumeValue}>{data.volume.withdrawals.toFixed(2)} RIS</Text>
        </View>
        <View style={styles.volumeRow}>
          <Text style={styles.volumeLabel}>Total Recargas:</Text>
          <Text style={styles.volumeValue}>{data.volume.recharges.toFixed(2)} BRL</Text>
        </View>
        <View style={styles.volumeRow}>
          <Text style={styles.volumeLabel}>Transacciones Completadas:</Text>
          <Text style={styles.volumeValue}>{data.transactions.completed}</Text>
        </View>
      </View>
    </View>
  );
}

function StatCard({ icon, title, value, color, subtitle }: { icon: string; title: string; value: number; color: string; subtitle?: string }) {
  return (
    <View style={styles.statCard}>
      <View style={[styles.statIcon, { backgroundColor: color + '20' }]}>
        <Ionicons name={icon as any} size={24} color={color} />
      </View>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statTitle}>{title}</Text>
      {subtitle && <Text style={styles.statSubtitle}>{subtitle}</Text>}
    </View>
  );
}

// Withdrawals Tab
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
      const response = await axios.get(`${BACKEND_URL}/api/admin/transactions?type=withdrawal&status=pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setWithdrawals(response.data.transactions);
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
      <Text style={styles.sectionTitle}>Retiros Pendientes ({withdrawals.length})</Text>
      
      {withdrawals.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle" size={48} color="#10b981" />
          <Text style={styles.emptyText}>No hay retiros pendientes</Text>
        </View>
      ) : (
        withdrawals.map((tx) => (
          <TouchableOpacity key={tx.transaction_id} style={styles.txCard} onPress={() => setSelectedTx(tx)}>
            <View style={styles.txHeader}>
              <Text style={styles.txAmount}>{tx.amount_input?.toFixed(2)} RIS</Text>
              <Text style={styles.txVes}>→ {tx.amount_output?.toFixed(2)} VES</Text>
            </View>
            <Text style={styles.txUser}>{tx.user_name} ({tx.user_email})</Text>
            <View style={styles.txBeneficiary}>
              <Text style={styles.txLabel}>Beneficiario: {tx.beneficiary_data?.full_name}</Text>
              <Text style={styles.txLabel}>Banco: {tx.beneficiary_data?.bank_code} - {tx.beneficiary_data?.bank}</Text>
              <Text style={styles.txLabel}>Cuenta: {tx.beneficiary_data?.account_number}</Text>
              <Text style={styles.txLabel}>Cédula: {tx.beneficiary_data?.id_document}</Text>
              <Text style={styles.txLabel}>Tel: {tx.beneficiary_data?.phone_number}</Text>
            </View>
          </TouchableOpacity>
        ))
      )}

      {/* Process Modal */}
      <Modal visible={!!selectedTx} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Procesar Retiro</Text>
              <TouchableOpacity onPress={() => { setSelectedTx(null); setProofImage(null); }}>
                <Ionicons name="close" size={24} color="#1f2937" />
              </TouchableOpacity>
            </View>

            {selectedTx && (
              <ScrollView style={styles.modalBody}>
                <Text style={styles.modalAmount}>{selectedTx.amount_input?.toFixed(2)} RIS → {selectedTx.amount_output?.toFixed(2)} VES</Text>
                <Text style={styles.modalUser}>{selectedTx.user_name}</Text>
                
                <View style={styles.beneficiaryBox}>
                  <Text style={styles.beneficiaryTitle}>Datos para Transferencia:</Text>
                  <Text style={styles.beneficiaryText}>Banco: {selectedTx.beneficiary_data?.bank_code} - {selectedTx.beneficiary_data?.bank}</Text>
                  <Text style={styles.beneficiaryText}>Cuenta: {selectedTx.beneficiary_data?.account_number}</Text>
                  <Text style={styles.beneficiaryText}>Titular: {selectedTx.beneficiary_data?.full_name}</Text>
                  <Text style={styles.beneficiaryText}>Cédula: {selectedTx.beneficiary_data?.id_document}</Text>
                  <Text style={styles.beneficiaryText}>Teléfono: {selectedTx.beneficiary_data?.phone_number}</Text>
                </View>

                <TouchableOpacity style={styles.uploadButton} onPress={pickProofImage}>
                  <Ionicons name="camera" size={24} color="#2563eb" />
                  <Text style={styles.uploadButtonText}>
                    {proofImage ? 'Cambiar Comprobante' : 'Subir Comprobante'}
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
                      <ActivityIndicator color="#fff" />
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
        </View>
      </Modal>
    </View>
  );
}

// Recharges Tab
function RechargesTab() {
  const [recharges, setRecharges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRecharges();
  }, []);

  const loadRecharges = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/pending-recharges`, {
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
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/recharge/approve`,
        { transaction_id: txId, approved },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', approved ? 'Recarga aprobada' : 'Recarga rechazada');
      loadRecharges();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Recargas Pendientes ({recharges.length})</Text>
      
      {recharges.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle" size={48} color="#10b981" />
          <Text style={styles.emptyText}>No hay recargas pendientes</Text>
        </View>
      ) : (
        recharges.map((tx) => (
          <View key={tx.transaction_id} style={styles.txCard}>
            <View style={styles.txHeader}>
              <Text style={styles.txAmount}>R$ {tx.amount_input?.toFixed(2)}</Text>
              <Text style={styles.txVes}>→ {tx.amount_output?.toFixed(2)} RIS</Text>
            </View>
            <Text style={styles.txUser}>{tx.user_name} ({tx.user_email})</Text>
            <View style={styles.actionButtons}>
              <TouchableOpacity style={[styles.actionButton, styles.rejectButton]} onPress={() => processRecharge(tx.transaction_id, false)}>
                <Text style={styles.actionButtonText}>Rechazar</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.actionButton, styles.approveButton]} onPress={() => processRecharge(tx.transaction_id, true)}>
                <Text style={styles.actionButtonText}>Aprobar</Text>
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

  return (
    <View style={styles.tabContent}>
      {!selectedChat ? (
        <>
          <Text style={styles.sectionTitle}>Chats de Soporte ({chats.length})</Text>
          {chats.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="chatbubbles-outline" size={48} color="#6b7280" />
              <Text style={styles.emptyText}>No hay chats de soporte</Text>
            </View>
          ) : (
            chats.map((chat) => (
              <TouchableOpacity key={chat.user_id} style={styles.chatCard} onPress={() => loadChatDetail(chat.user_id)}>
                <View style={styles.chatHeader}>
                  <Text style={styles.chatName}>{chat.user_name}</Text>
                  <View style={[styles.chatStatus, chat.status === 'closed' ? styles.statusClosed : styles.statusOpen]}>
                    <Text style={styles.chatStatusText}>{chat.status === 'closed' ? 'Cerrado' : 'Abierto'}</Text>
                  </View>
                </View>
                <Text style={styles.chatEmail}>{chat.user_email}</Text>
                <Text style={styles.chatPreview}>{chat.last_message}</Text>
                <Text style={styles.chatCount}>{chat.message_count} mensajes</Text>
              </TouchableOpacity>
            ))
          )}
        </>
      ) : (
        <View style={styles.chatDetail}>
          <View style={styles.chatDetailHeader}>
            <TouchableOpacity onPress={() => setSelectedChat(null)}>
              <Ionicons name="arrow-back" size={24} color="#1f2937" />
            </TouchableOpacity>
            <View style={styles.chatDetailInfo}>
              <Text style={styles.chatDetailName}>{selectedChat.user_name}</Text>
              <Text style={styles.chatDetailEmail}>{selectedChat.user_email}</Text>
            </View>
            <TouchableOpacity style={styles.closeButton} onPress={closeChat}>
              <Text style={styles.closeButtonText}>Cerrar</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.messagesContainer}>
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
              {sending ? <ActivityIndicator color="#fff" /> : <Ionicons name="send" size={20} color="#fff" />}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

// Users Tab
function UsersTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadUsers();
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
    } catch (error) {
      console.error('Error loading users:', error);
    } finally {
      setLoading(false);
    }
  };

  const doSearch = () => {
    loadUsers(search);
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Usuarios ({users.length})</Text>
      
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por nombre o email..."
          onSubmitEditing={doSearch}
        />
        <TouchableOpacity style={styles.searchButton} onPress={doSearch}>
          <Ionicons name="search" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {users.map((u) => (
        <View key={u.user_id} style={styles.userCard}>
          <View style={styles.userHeader}>
            <Text style={styles.userName}>{u.name}</Text>
            <View style={[styles.verificationBadge, u.verification_status === 'verified' ? styles.verified : styles.pending]}>
              <Text style={styles.verificationText}>{u.verification_status === 'verified' ? 'Verificado' : 'Pendiente'}</Text>
            </View>
          </View>
          <Text style={styles.userEmail}>{u.email}</Text>
          <Text style={styles.userBalance}>Balance: {u.balance_ris?.toFixed(2) || '0.00'} RIS</Text>
        </View>
      ))}
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
        <Text style={styles.sectionTitle}>Administradores ({admins.length})</Text>
        <TouchableOpacity style={styles.addButton} onPress={() => setShowCreate(true)}>
          <Ionicons name="add" size={20} color="#fff" />
          <Text style={styles.addButtonText}>Nuevo</Text>
        </TouchableOpacity>
      </View>

      {admins.map((admin) => (
        <View key={admin.user_id} style={styles.adminCard}>
          <View style={styles.adminHeader}>
            <Text style={styles.adminName}>{admin.name}</Text>
            <View style={[styles.roleBadge, admin.role === 'super_admin' && styles.superAdminBadge]}>
              <Text style={styles.roleText}>{admin.role === 'super_admin' ? 'Super Admin' : 'Admin'}</Text>
            </View>
          </View>
          <Text style={styles.adminEmail}>{admin.email}</Text>
          {admin.permissions && admin.permissions.length > 0 && (
            <Text style={styles.adminPermissions}>Permisos: {admin.permissions.length}</Text>
          )}
        </View>
      ))}

      {/* Create Admin Modal */}
      <Modal visible={showCreate} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Nuevo Administrador</Text>
              <TouchableOpacity onPress={() => setShowCreate(false)}>
                <Ionicons name="close" size={24} color="#1f2937" />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalBody}>
              <Text style={styles.inputLabel}>Email</Text>
              <TextInput
                style={styles.input}
                value={newAdmin.email}
                onChangeText={(v) => setNewAdmin(p => ({ ...p, email: v }))}
                placeholder="email@ejemplo.com"
                keyboardType="email-address"
              />
              <Text style={styles.inputLabel}>Nombre</Text>
              <TextInput
                style={styles.input}
                value={newAdmin.name}
                onChangeText={(v) => setNewAdmin(p => ({ ...p, name: v }))}
                placeholder="Nombre completo"
              />
              <Text style={styles.inputLabel}>Permisos</Text>
              {Object.entries(permissions).map(([key, label]) => (
                <TouchableOpacity key={key} style={styles.permissionRow} onPress={() => togglePermission(key)}>
                  <View style={[styles.checkbox, newAdmin.permissions.includes(key) && styles.checkboxChecked]}>
                    {newAdmin.permissions.includes(key) && <Ionicons name="checkmark" size={14} color="#fff" />}
                  </View>
                  <Text style={styles.permissionLabel}>{label}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity style={styles.createButton} onPress={createAdmin}>
                <Text style={styles.createButtonText}>Crear Administrador</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// Settings Tab
function SettingsTab({ currentRate }: { currentRate: number }) {
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
        <Text style={styles.settingTitle}>Tasa de Cambio RIS/VES</Text>
        <Text style={styles.settingDescription}>1 RIS equivale a:</Text>
        <View style={styles.rateInputContainer}>
          <TextInput
            style={styles.rateInput}
            value={rate}
            onChangeText={setRate}
            keyboardType="numeric"
          />
          <Text style={styles.rateLabel}>VES</Text>
        </View>
        <TouchableOpacity style={styles.saveButton} onPress={saveRate} disabled={saving}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveButtonText}>Guardar</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f3f4f6' },
  centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, color: '#6b7280' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  headerTitle: { fontSize: 18, fontWeight: 'bold', color: '#1f2937' },
  roleText: { fontSize: 12, color: '#6b7280' },
  tabsContainer: { backgroundColor: '#fff', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tabButton: { paddingHorizontal: 16, paddingVertical: 8, alignItems: 'center', marginHorizontal: 4 },
  tabButtonActive: { borderBottomWidth: 2, borderBottomColor: '#2563eb' },
  tabIconContainer: { position: 'relative' },
  tabBadge: { position: 'absolute', top: -4, right: -8, backgroundColor: '#ef4444', borderRadius: 8, minWidth: 16, height: 16, justifyContent: 'center', alignItems: 'center' },
  tabBadgeText: { color: '#fff', fontSize: 10, fontWeight: 'bold' },
  tabLabel: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  tabLabelActive: { color: '#2563eb', fontWeight: '600' },
  content: { flex: 1 },
  tabContent: { padding: 16 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', color: '#1f2937', marginBottom: 16 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -6 },
  statCard: { width: '46%', backgroundColor: '#fff', borderRadius: 12, padding: 16, margin: 6, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  statIcon: { width: 40, height: 40, borderRadius: 20, justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
  statValue: { fontSize: 24, fontWeight: 'bold', color: '#1f2937' },
  statTitle: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  statSubtitle: { fontSize: 11, color: '#9ca3af' },
  volumeCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16 },
  volumeRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  volumeLabel: { color: '#6b7280' },
  volumeValue: { fontWeight: '600', color: '#1f2937' },
  emptyState: { alignItems: 'center', padding: 40 },
  emptyText: { marginTop: 12, color: '#6b7280' },
  txCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12 },
  txHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  txAmount: { fontSize: 18, fontWeight: 'bold', color: '#1f2937' },
  txVes: { fontSize: 14, color: '#10b981', marginLeft: 8 },
  txUser: { fontSize: 14, color: '#6b7280', marginBottom: 8 },
  txBeneficiary: { backgroundColor: '#f9fafb', padding: 12, borderRadius: 8 },
  txLabel: { fontSize: 13, color: '#374151', marginBottom: 4 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '90%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 18, fontWeight: 'bold' },
  modalBody: { padding: 16 },
  modalAmount: { fontSize: 24, fontWeight: 'bold', color: '#1f2937', textAlign: 'center' },
  modalUser: { fontSize: 14, color: '#6b7280', textAlign: 'center', marginBottom: 16 },
  beneficiaryBox: { backgroundColor: '#f3f4f6', padding: 16, borderRadius: 12, marginBottom: 16 },
  beneficiaryTitle: { fontWeight: '600', marginBottom: 8 },
  beneficiaryText: { fontSize: 14, marginBottom: 4 },
  uploadButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 16, borderWidth: 2, borderStyle: 'dashed', borderColor: '#2563eb', borderRadius: 12, marginBottom: 16 },
  uploadButtonText: { marginLeft: 8, color: '#2563eb', fontWeight: '600' },
  proofPreview: { width: '100%', height: 200, borderRadius: 12, marginBottom: 16 },
  actionButtons: { flexDirection: 'row', gap: 12, marginTop: 8 },
  actionButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 8, gap: 6 },
  approveButton: { backgroundColor: '#10b981' },
  rejectButton: { backgroundColor: '#ef4444' },
  disabledButton: { backgroundColor: '#9ca3af' },
  actionButtonText: { color: '#fff', fontWeight: '600' },
  chatCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12 },
  chatHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  chatName: { fontSize: 16, fontWeight: '600' },
  chatStatus: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  statusOpen: { backgroundColor: '#fef3c7' },
  statusClosed: { backgroundColor: '#d1fae5' },
  chatStatusText: { fontSize: 12, fontWeight: '500' },
  chatEmail: { color: '#6b7280', marginTop: 4 },
  chatPreview: { color: '#374151', marginTop: 8 },
  chatCount: { color: '#9ca3af', fontSize: 12, marginTop: 4 },
  chatDetail: { flex: 1 },
  chatDetailHeader: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', padding: 12, borderRadius: 12, marginBottom: 12 },
  chatDetailInfo: { flex: 1, marginLeft: 12 },
  chatDetailName: { fontWeight: '600' },
  chatDetailEmail: { fontSize: 12, color: '#6b7280' },
  closeButton: { backgroundColor: '#ef4444', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  closeButtonText: { color: '#fff', fontWeight: '600' },
  messagesContainer: { flex: 1, maxHeight: 300 },
  message: { padding: 12, borderRadius: 12, marginBottom: 8, maxWidth: '80%' },
  userMessage: { backgroundColor: '#e5e7eb', alignSelf: 'flex-start' },
  adminMessage: { backgroundColor: '#2563eb', alignSelf: 'flex-end' },
  messageImage: { width: 150, height: 100, borderRadius: 8, marginBottom: 8 },
  messageText: { fontSize: 14 },
  adminMessageText: { color: '#fff' },
  responseContainer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, marginTop: 12 },
  responseInput: { flex: 1, backgroundColor: '#fff', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, maxHeight: 100 },
  sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },
  searchContainer: { flexDirection: 'row', marginBottom: 16, gap: 8 },
  searchInput: { flex: 1, backgroundColor: '#fff', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 },
  searchButton: { backgroundColor: '#2563eb', width: 44, height: 44, borderRadius: 8, justifyContent: 'center', alignItems: 'center' },
  userCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12 },
  userHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  userName: { fontSize: 16, fontWeight: '600' },
  verificationBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  verified: { backgroundColor: '#d1fae5' },
  pending: { backgroundColor: '#fef3c7' },
  verificationText: { fontSize: 12, fontWeight: '500' },
  userEmail: { color: '#6b7280', marginTop: 4 },
  userBalance: { color: '#10b981', fontWeight: '600', marginTop: 8 },
  addButton: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#2563eb', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, gap: 4 },
  addButtonText: { color: '#fff', fontWeight: '600' },
  adminCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12 },
  adminHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  adminName: { fontSize: 16, fontWeight: '600' },
  roleBadge: { backgroundColor: '#dbeafe', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  superAdminBadge: { backgroundColor: '#fef3c7' },
  roleText: { fontSize: 12, fontWeight: '600', color: '#1f2937' },
  adminEmail: { color: '#6b7280', marginTop: 4 },
  adminPermissions: { color: '#9ca3af', fontSize: 12, marginTop: 4 },
  inputLabel: { fontSize: 14, fontWeight: '600', marginBottom: 8, marginTop: 12 },
  input: { backgroundColor: '#f3f4f6', borderRadius: 8, padding: 12, fontSize: 16 },
  permissionRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8 },
  checkbox: { width: 22, height: 22, borderWidth: 2, borderColor: '#d1d5db', borderRadius: 4, marginRight: 12, justifyContent: 'center', alignItems: 'center' },
  checkboxChecked: { backgroundColor: '#2563eb', borderColor: '#2563eb' },
  permissionLabel: { flex: 1, fontSize: 14 },
  createButton: { backgroundColor: '#2563eb', padding: 16, borderRadius: 8, alignItems: 'center', marginTop: 20, marginBottom: 30 },
  createButtonText: { color: '#fff', fontWeight: '600', fontSize: 16 },
  settingCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16 },
  settingTitle: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  settingDescription: { color: '#6b7280', marginBottom: 12 },
  rateInputContainer: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rateInput: { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 8, padding: 12, fontSize: 24, fontWeight: 'bold', textAlign: 'center' },
  rateLabel: { fontSize: 18, fontWeight: '600', color: '#6b7280' },
  saveButton: { backgroundColor: '#2563eb', padding: 14, borderRadius: 8, alignItems: 'center', marginTop: 16 },
  saveButtonText: { color: '#fff', fontWeight: '600' },
});
