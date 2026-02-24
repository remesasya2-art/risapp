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
const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const IS_LARGE_SCREEN = SCREEN_WIDTH >= 1024;
const IS_DESKTOP = Platform.OS === 'web' && SCREEN_WIDTH >= 768;

type TabType = 'dashboard' | 'withdrawals' | 'recharges' | 'kyc' | 'support' | 'users' | 'admins' | 'settings';

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
    { key: 'dashboard', icon: 'grid-outline', label: 'Dashboard' },
    { key: 'withdrawals', icon: 'trending-up-outline', label: 'Retiros', badge: dashboard?.transactions.pending_withdrawals },
    { key: 'recharges', icon: 'trending-down-outline', label: 'Recargas', badge: dashboard?.transactions.pending_recharges },
    { key: 'kyc', icon: 'shield-checkmark-outline', label: 'KYC', badge: dashboard?.users.pending_kyc },
    { key: 'support', icon: 'chatbubble-ellipses-outline', label: 'Soporte', badge: dashboard?.support.open_chats },
    { key: 'users', icon: 'people-outline', label: 'Usuarios' },
    ...(userRole === 'super_admin' ? [{ key: 'admins', icon: 'key-outline', label: 'Admins' }] : []),
    { key: 'settings', icon: 'cash-outline', label: 'Tasas' },
  ];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Modern Header */}
      <View style={[styles.header, IS_DESKTOP && styles.headerDesktop]}>
        <View style={styles.headerLeft}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
            <Ionicons name="chevron-back" size={24} color="#fff" />
          </TouchableOpacity>
        </View>
        <View style={styles.headerCenter}>
          <Text style={[styles.headerTitle, IS_DESKTOP && styles.headerTitleDesktop]}>Panel de Control</Text>
          <View style={[styles.roleBadge, userRole === 'super_admin' && styles.superBadge]}>
            <Ionicons name={userRole === 'super_admin' ? 'diamond' : 'shield'} size={12} color="#fff" />
            <Text style={styles.roleBadgeText}>{userRole === 'super_admin' ? 'Super Admin' : 'Admin'}</Text>
          </View>
        </View>
        <View style={styles.headerRight}>
          <TouchableOpacity onPress={onRefresh} style={styles.refreshButton}>
            <Ionicons name="sync-outline" size={22} color="#fff" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Navigation Tabs */}
      <View style={[styles.tabsWrapper, IS_DESKTOP && styles.tabsWrapperDesktop]}>
        <ScrollView 
          horizontal 
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={[styles.tabsContainer, IS_DESKTOP && styles.tabsContainerDesktop]}
        >
          {tabs.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tabItem, activeTab === tab.key && styles.tabItemActive, IS_DESKTOP && styles.tabItemDesktop]}
              onPress={() => setActiveTab(tab.key as TabType)}
            >
              <Ionicons 
                name={tab.icon as any} 
                size={IS_DESKTOP ? 20 : 18} 
                color={activeTab === tab.key ? '#fff' : '#64748b'} 
              />
              <Text style={[styles.tabLabel, activeTab === tab.key && styles.tabLabelActive, IS_DESKTOP && styles.tabLabelDesktop]}>
                {tab.label}
              </Text>
              {tab.badge !== undefined && tab.badge > 0 && (
                <View style={[styles.tabBadge, activeTab === tab.key && styles.tabBadgeActive]}>
                  <Text style={[styles.tabBadgeText, activeTab === tab.key && styles.tabBadgeTextActive]}>
                    {tab.badge > 99 ? '99+' : tab.badge}
                  </Text>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Main Content - Full Width on Desktop */}
      <ScrollView
        style={[styles.content, IS_DESKTOP && styles.contentDesktop]}
        contentContainerStyle={[styles.contentContainer, IS_DESKTOP && styles.contentContainerDesktop]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2563eb" />}
        showsVerticalScrollIndicator={false}
      >
        {activeTab === 'dashboard' && <DashboardTab data={dashboard} onNavigateToRates={() => setActiveTab('settings')} />}
        {activeTab === 'withdrawals' && <WithdrawalsTab />}
        {activeTab === 'recharges' && <RechargesTab />}
        {activeTab === 'kyc' && <KYCVerificationsTab />}
        {activeTab === 'support' && <SupportTab />}
        {activeTab === 'users' && <UsersTab />}
        {activeTab === 'admins' && userRole === 'super_admin' && <AdminsTab />}
        {activeTab === 'settings' && <SettingsTab currentRate={dashboard?.current_rate || 78} onRateUpdated={onRefresh} />}
      </ScrollView>
    </SafeAreaView>
  );
}

// Dashboard Tab - Professional layout
function DashboardTab({ data, onNavigateToRates }: { data: DashboardData | null; onNavigateToRates: () => void }) {
  if (!data) return null;

  return (
    <View style={styles.tabContent}>
      {/* Quick Access to Rates */}
      <TouchableOpacity style={styles.ratesQuickAccess} onPress={onNavigateToRates}>
        <View style={styles.ratesQuickAccessLeft}>
          <View style={styles.ratesQuickAccessIcon}>
            <Ionicons name="cash" size={24} color="#fff" />
          </View>
          <View>
            <Text style={styles.ratesQuickAccessTitle}>Configurar Tasas</Text>
            <Text style={styles.ratesQuickAccessSubtitle}>Tasa actual: {data.current_rate} VES/RIS</Text>
          </View>
        </View>
        <Ionicons name="chevron-forward" size={24} color="#fff" />
      </TouchableOpacity>

      {/* Welcome Card */}
      <View style={styles.welcomeCard}>
        <View style={styles.welcomeContent}>
          <Text style={styles.welcomeTitle}>Panel de Administración</Text>
          <Text style={styles.welcomeSubtitle}>Gestiona tu plataforma RIS</Text>
        </View>
        <View style={styles.welcomeIcon}>
          <Ionicons name="analytics" size={32} color="#2563eb" />
        </View>
      </View>

      {/* Pending Actions - Alert Style */}
      <View style={styles.pendingSection}>
        <Text style={styles.pendingSectionTitle}>Acciones Pendientes</Text>
        <View style={styles.pendingGrid}>
          <View style={[styles.pendingCard, { borderLeftColor: '#ef4444' }]}>
            <View style={styles.pendingCardIcon}>
              <Ionicons name="trending-up" size={20} color="#ef4444" />
            </View>
            <View style={styles.pendingCardContent}>
              <Text style={styles.pendingCardValue}>{data.transactions.pending_withdrawals}</Text>
              <Text style={styles.pendingCardLabel}>Retiros</Text>
            </View>
          </View>
          <View style={[styles.pendingCard, { borderLeftColor: '#10b981' }]}>
            <View style={styles.pendingCardIcon}>
              <Ionicons name="trending-down" size={20} color="#10b981" />
            </View>
            <View style={styles.pendingCardContent}>
              <Text style={styles.pendingCardValue}>{data.transactions.pending_recharges}</Text>
              <Text style={styles.pendingCardLabel}>Recargas</Text>
            </View>
          </View>
          <View style={[styles.pendingCard, { borderLeftColor: '#f59e0b' }]}>
            <View style={styles.pendingCardIcon}>
              <Ionicons name="shield-checkmark" size={20} color="#f59e0b" />
            </View>
            <View style={styles.pendingCardContent}>
              <Text style={styles.pendingCardValue}>{data.users.pending_kyc}</Text>
              <Text style={styles.pendingCardLabel}>KYC</Text>
            </View>
          </View>
          <View style={[styles.pendingCard, { borderLeftColor: '#8b5cf6' }]}>
            <View style={styles.pendingCardIcon}>
              <Ionicons name="chatbubble-ellipses" size={20} color="#8b5cf6" />
            </View>
            <View style={styles.pendingCardContent}>
              <Text style={styles.pendingCardValue}>{data.support.open_chats}</Text>
              <Text style={styles.pendingCardLabel}>Soporte</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Stats Overview */}
      <View style={styles.statsSection}>
        <Text style={styles.statsSectionTitle}>Resumen General</Text>
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <View style={[styles.statBoxIcon, { backgroundColor: '#eff6ff' }]}>
              <Ionicons name="people" size={22} color="#2563eb" />
            </View>
            <Text style={styles.statBoxValue}>{data.users.total}</Text>
            <Text style={styles.statBoxLabel}>Usuarios</Text>
          </View>
          <View style={styles.statBox}>
            <View style={[styles.statBoxIcon, { backgroundColor: '#ecfdf5' }]}>
              <Ionicons name="checkmark-done" size={22} color="#10b981" />
            </View>
            <Text style={styles.statBoxValue}>{data.users.verified}</Text>
            <Text style={styles.statBoxLabel}>Verificados</Text>
          </View>
          <View style={styles.statBox}>
            <View style={[styles.statBoxIcon, { backgroundColor: '#fef3c7' }]}>
              <Ionicons name="swap-horizontal" size={22} color="#f59e0b" />
            </View>
            <Text style={styles.statBoxValue}>{data.current_rate}</Text>
            <Text style={styles.statBoxLabel}>Tasa RIS/VES</Text>
          </View>
        </View>
      </View>

      {/* Volume Summary */}
      <View style={styles.volumeSection}>
        <Text style={styles.volumeSectionTitle}>Volumen de Operaciones</Text>
        <View style={styles.volumeCards}>
          <View style={styles.volumeCardNew}>
            <Ionicons name="arrow-up-circle" size={28} color="#ef4444" />
            <Text style={styles.volumeCardValue}>{data.volume.withdrawals.toFixed(0)}</Text>
            <Text style={styles.volumeCardLabel}>RIS Enviados</Text>
          </View>
          <View style={styles.volumeCardNew}>
            <Ionicons name="arrow-down-circle" size={28} color="#10b981" />
            <Text style={styles.volumeCardValue}>{data.volume.recharges.toFixed(0)}</Text>
            <Text style={styles.volumeCardLabel}>BRL Recargados</Text>
          </View>
          <View style={styles.volumeCardNew}>
            <Ionicons name="receipt" size={28} color="#2563eb" />
            <Text style={styles.volumeCardValue}>{data.transactions.completed}</Text>
            <Text style={styles.volumeCardLabel}>Completadas</Text>
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

// VENEZUELA BANKS for filtering
const BANK_FILTERS = [
  { code: '0102', name: 'BANCO DE VENEZUELA S.A' },
  { code: '0105', name: 'BANCO MERCANTIL C.A' },
  { code: '0108', name: 'BANCO PROVINCIAL BBVA' },
  { code: '0134', name: 'BANESCO BANCO UNIVERSAL' },
];

// Status types for remittances
type RemittanceStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'claimed' | 'refunded';

// Withdrawals Tab - Full Professional Interface
function WithdrawalsTab() {
  const [allWithdrawals, setAllWithdrawals] = useState<any[]>([]);
  const [filteredWithdrawals, setFilteredWithdrawals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState<any>(null);
  const [proofImage, setProofImage] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  
  // Filter states
  const [activeStatus, setActiveStatus] = useState<RemittanceStatus | 'all'>('pending');
  const [selectedBank, setSelectedBank] = useState<string | null>(null);
  const [searchId, setSearchId] = useState('');
  const [searchName, setSearchName] = useState('');
  const [searchDate, setSearchDate] = useState('');
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  
  // Selection for bulk actions
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  
  // Detail/Edit modal
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);

  useEffect(() => {
    loadAllWithdrawals();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [allWithdrawals, activeStatus, selectedBank, searchId, searchName, searchDate]);

  const loadAllWithdrawals = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      // Load all withdrawals (pending, processing, completed, etc.)
      const response = await axios.get(`${BACKEND_URL}/api/admin/withdrawals/all`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAllWithdrawals(response.data || []);
    } catch (error) {
      console.error('Error loading withdrawals:', error);
      // Fallback to pending only if /all endpoint doesn't exist
      try {
        const token = await AsyncStorage.getItem('session_token');
        const response = await axios.get(`${BACKEND_URL}/api/admin/withdrawals/pending`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setAllWithdrawals(response.data || []);
      } catch (e) {
        console.error('Error loading pending withdrawals:', e);
      }
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let result = [...allWithdrawals];
    
    // Filter by status
    if (activeStatus !== 'all') {
      result = result.filter(tx => tx.status === activeStatus);
    }
    
    // Filter by bank
    if (selectedBank) {
      result = result.filter(tx => tx.beneficiary_data?.bank_code === selectedBank);
    }
    
    // Filter by ID
    if (searchId.trim()) {
      result = result.filter(tx => 
        tx.transaction_id?.toLowerCase().includes(searchId.toLowerCase())
      );
    }
    
    // Filter by name
    if (searchName.trim()) {
      result = result.filter(tx => 
        tx.user_name?.toLowerCase().includes(searchName.toLowerCase()) ||
        tx.beneficiary_data?.full_name?.toLowerCase().includes(searchName.toLowerCase())
      );
    }
    
    // Filter by date
    if (searchDate.trim()) {
      result = result.filter(tx => {
        const txDate = new Date(tx.created_at).toLocaleDateString('es-ES');
        return txDate.includes(searchDate);
      });
    }
    
    setFilteredWithdrawals(result);
    setCurrentPage(1);
  };

  const clearFilters = () => {
    setSearchId('');
    setSearchName('');
    setSearchDate('');
    setSelectedBank(null);
    setActiveStatus('pending');
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
      
      showAlert('Éxito', action === 'approve' ? 'Remesa procesada correctamente' : 'Remesa rechazada');
      setSelectedTx(null);
      setProofImage(null);
      setShowDetailModal(false);
      loadAllWithdrawals();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    } finally {
      setProcessing(false);
    }
  };

  const processQuickPayment = async (tx: any) => {
    setSelectedTx(tx);
    setShowDetailModal(true);
  };

  const exportToExcel = () => {
    // Create CSV content
    const headers = ['ID', 'Fecha', 'Pagador', 'Cantidad Enviada', 'Comisión', 'Importe Pagado', 'Tasa', 'Banco', 'Beneficiario', 'CI/CPF', 'Nro. Cuenta', 'Moneda', 'Cantidad a Enviar', 'Estado'];
    const rows = filteredWithdrawals.map(tx => [
      tx.transaction_id,
      new Date(tx.created_at).toLocaleString('es-ES'),
      tx.user_name || '',
      tx.amount_input?.toFixed(2) || '',
      tx.commission?.toFixed(2) || '0.00',
      tx.amount_input?.toFixed(2) || '',
      tx.rate?.toFixed(2) || '',
      tx.beneficiary_data?.bank || '',
      tx.beneficiary_data?.full_name || '',
      tx.beneficiary_data?.id_document || '',
      tx.beneficiary_data?.account_number || '',
      'VES',
      tx.amount_output?.toFixed(2) || '',
      tx.status || ''
    ]);
    
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    
    // Download
    if (Platform.OS === 'web') {
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `remesas_${new Date().toISOString().split('T')[0]}.csv`;
      link.click();
    } else {
      showAlert('Exportar', 'La exportación a Excel está disponible solo en la versión web');
    }
  };

  const toggleSelectItem = (id: string) => {
    setSelectedItems(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    const pageItems = getCurrentPageItems();
    if (selectedItems.length === pageItems.length) {
      setSelectedItems([]);
    } else {
      setSelectedItems(pageItems.map(tx => tx.transaction_id));
    }
  };

  // Pagination helpers
  const totalPages = Math.ceil(filteredWithdrawals.length / itemsPerPage);
  const getCurrentPageItems = () => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredWithdrawals.slice(start, start + itemsPerPage);
  };

  // Count by status
  const getStatusCount = (status: string) => {
    if (status === 'all') return allWithdrawals.length;
    return allWithdrawals.filter(tx => tx.status === status).length;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return '#f59e0b';
      case 'processing': return '#3b82f6';
      case 'completed': return '#10b981';
      case 'failed': return '#ef4444';
      case 'claimed': return '#8b5cf6';
      case 'refunded': return '#ec4899';
      default: return '#6b7280';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'pending': return 'Pendiente';
      case 'processing': return 'Procesando';
      case 'completed': return 'Completada';
      case 'failed': return 'No completada';
      case 'claimed': return 'En reclamación';
      case 'refunded': return 'En reembolso';
      default: return status;
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getWaitTime = (dateString: string) => {
    const created = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - created.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 60) return `${diffMins} min`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} h`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} d`;
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  const statusTabs = [
    { key: 'pending', label: 'Remesas Pendiente', color: '#f59e0b' },
    { key: 'processing', label: 'Remesas Procesando', color: '#f59e0b' },
    { key: 'completed', label: 'Remesa Completada', color: '#6b7280' },
    { key: 'failed', label: 'Remesas No completada', color: '#6b7280' },
    { key: 'claimed', label: 'Remesa En reclamación', color: '#ef4444' },
    { key: 'refunded', label: 'Remesas En reembolso', color: '#ef4444' },
  ];

  return (
    <View style={wdStyles.container}>
      {/* Status Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={wdStyles.statusTabsContainer}>
        <View style={wdStyles.statusTabs}>
          {statusTabs.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[
                wdStyles.statusTab,
                activeStatus === tab.key && { backgroundColor: tab.color }
              ]}
              onPress={() => setActiveStatus(tab.key as RemittanceStatus)}
            >
              <Text style={[
                wdStyles.statusTabText,
                activeStatus === tab.key && { color: '#fff' }
              ]}>
                {tab.label}
              </Text>
              {tab.key === 'claimed' && getStatusCount('claimed') > 0 && (
                <View style={wdStyles.statusBadge}>
                  <Text style={wdStyles.statusBadgeText}>{getStatusCount('claimed')}</Text>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Bank Filters */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={wdStyles.bankFiltersContainer}>
        <View style={wdStyles.bankFilters}>
          {BANK_FILTERS.map((bank) => (
            <TouchableOpacity
              key={bank.code}
              style={[
                wdStyles.bankFilter,
                selectedBank === bank.code && wdStyles.bankFilterActive
              ]}
              onPress={() => setSelectedBank(selectedBank === bank.code ? null : bank.code)}
            >
              <Text style={[
                wdStyles.bankFilterText,
                selectedBank === bank.code && wdStyles.bankFilterTextActive
              ]}>
                {bank.name}
              </Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity
            style={[wdStyles.bankFilter, !selectedBank && wdStyles.bankFilterActive]}
            onPress={() => setSelectedBank(null)}
          >
            <Text style={[wdStyles.bankFilterText, !selectedBank && wdStyles.bankFilterTextActive]}>
              Todos
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={wdStyles.bankFilter}
            onPress={() => setSelectedBank('otros')}
          >
            <Text style={wdStyles.bankFilterText}>Otros</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Search Filters */}
      <View style={wdStyles.searchFilters}>
        <TextInput
          style={wdStyles.searchInput}
          placeholder="ID"
          placeholderTextColor="#9ca3af"
          value={searchId}
          onChangeText={setSearchId}
        />
        <TextInput
          style={[wdStyles.searchInput, { flex: 1.5 }]}
          placeholder="Nombre"
          placeholderTextColor="#9ca3af"
          value={searchName}
          onChangeText={setSearchName}
        />
        <TextInput
          style={wdStyles.searchInput}
          placeholder="dd/mm/aaaa"
          placeholderTextColor="#9ca3af"
          value={searchDate}
          onChangeText={setSearchDate}
        />
        <TouchableOpacity style={wdStyles.searchButton} onPress={applyFilters}>
          <Ionicons name="search" size={20} color="#fff" />
        </TouchableOpacity>
        <TouchableOpacity style={wdStyles.clearButton} onPress={clearFilters}>
          <Ionicons name="close" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Export Button */}
      <TouchableOpacity style={wdStyles.exportButton} onPress={exportToExcel}>
        <Ionicons name="download-outline" size={18} color="#fff" />
        <Text style={wdStyles.exportButtonText}>Excel</Text>
      </TouchableOpacity>

      {/* Data Table */}
      <ScrollView horizontal showsHorizontalScrollIndicator={true}>
        <View style={wdStyles.table}>
          {/* Table Header */}
          <View style={wdStyles.tableHeader}>
            <TouchableOpacity style={wdStyles.checkboxCell} onPress={toggleSelectAll}>
              <Ionicons 
                name={selectedItems.length === getCurrentPageItems().length && selectedItems.length > 0 ? "checkbox" : "square-outline"} 
                size={20} 
                color="#6b7280" 
              />
            </TouchableOpacity>
            <Text style={[wdStyles.headerCell, { width: 70 }]}>Id</Text>
            <Text style={[wdStyles.headerCell, { width: 80 }]}>Espera</Text>
            <Text style={[wdStyles.headerCell, { width: 100 }]}>Acción</Text>
            <Text style={[wdStyles.headerCell, { width: 100 }]}>Historial</Text>
            <Text style={[wdStyles.headerCell, { width: 150 }]}>Fecha</Text>
            <Text style={[wdStyles.headerCell, { width: 200 }]}>Pagador</Text>
            <Text style={[wdStyles.headerCell, { width: 100 }]}>Enviado</Text>
            <Text style={[wdStyles.headerCell, { width: 80 }]}>Comisión</Text>
            <Text style={[wdStyles.headerCell, { width: 100 }]}>Pagado</Text>
            <Text style={[wdStyles.headerCell, { width: 80 }]}>Tasa</Text>
            <Text style={[wdStyles.headerCell, { width: 180 }]}>Banco</Text>
            <Text style={[wdStyles.headerCell, { width: 180 }]}>Beneficiario</Text>
            <Text style={[wdStyles.headerCell, { width: 120 }]}>CI/CPF</Text>
            <Text style={[wdStyles.headerCell, { width: 180 }]}>Nro. Cuenta</Text>
            <Text style={[wdStyles.headerCell, { width: 70 }]}>Moneda</Text>
            <Text style={[wdStyles.headerCell, { width: 120 }]}>A enviar</Text>
          </View>

          {/* Table Body */}
          {getCurrentPageItems().length === 0 ? (
            <View style={wdStyles.emptyRow}>
              <Text style={wdStyles.emptyText}>No hay remesas que coincidan con los filtros</Text>
            </View>
          ) : (
            getCurrentPageItems().map((tx) => (
              <View key={tx.transaction_id} style={wdStyles.tableRow}>
                <TouchableOpacity 
                  style={wdStyles.checkboxCell} 
                  onPress={() => toggleSelectItem(tx.transaction_id)}
                >
                  <Ionicons 
                    name={selectedItems.includes(tx.transaction_id) ? "checkbox" : "square-outline"} 
                    size={20} 
                    color="#6b7280" 
                  />
                </TouchableOpacity>
                <Text style={[wdStyles.cell, { width: 70 }]}>{tx.transaction_id?.substring(0, 6)}</Text>
                <Text style={[wdStyles.cell, { width: 80 }]}>{getWaitTime(tx.created_at)}</Text>
                
                {/* Action Button */}
                <View style={[wdStyles.cell, { width: 100 }]}>
                  {tx.status === 'pending' && (
                    <TouchableOpacity 
                      style={wdStyles.payNowButton}
                      onPress={() => processQuickPayment(tx)}
                    >
                      <Text style={wdStyles.payNowText}>pago ahora</Text>
                    </TouchableOpacity>
                  )}
                </View>
                
                {/* History/Actions */}
                <View style={[wdStyles.cell, wdStyles.actionsCell, { width: 100 }]}>
                  <TouchableOpacity onPress={() => { setSelectedTx(tx); setShowDetailModal(true); }}>
                    <Ionicons name="create-outline" size={18} color="#3b82f6" />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => { setSelectedTx(tx); setShowHistoryModal(true); }}>
                    <Ionicons name="eye-outline" size={18} color="#10b981" />
                  </TouchableOpacity>
                  <TouchableOpacity>
                    <Ionicons name="alert-circle-outline" size={18} color="#f59e0b" />
                  </TouchableOpacity>
                  <View style={[wdStyles.statusDot, { backgroundColor: getStatusColor(tx.status) }]} />
                </View>
                
                {/* Status Badge */}
                <View style={[wdStyles.cell, { width: 100 }]}>
                  <View style={[wdStyles.statusBadgeInline, { backgroundColor: getStatusColor(tx.status) + '20' }]}>
                    <Text style={[wdStyles.statusBadgeInlineText, { color: getStatusColor(tx.status) }]}>
                      {getStatusLabel(tx.status)}
                    </Text>
                  </View>
                </View>
                
                <Text style={[wdStyles.cell, { width: 150 }]}>{formatDate(tx.created_at)}</Text>
                <Text style={[wdStyles.cell, { width: 200 }]} numberOfLines={1}>{tx.user_name || 'N/A'}</Text>
                <Text style={[wdStyles.cell, { width: 100 }]}>{tx.amount_input?.toFixed(2)} $</Text>
                <Text style={[wdStyles.cell, { width: 80 }]}>{tx.commission?.toFixed(2) || '0.00'} $</Text>
                <Text style={[wdStyles.cell, { width: 100 }]}>{tx.amount_input?.toFixed(2)} $</Text>
                <Text style={[wdStyles.cell, { width: 80 }]}>{tx.rate?.toFixed(2) || '---'}</Text>
                <Text style={[wdStyles.cell, { width: 180 }]} numberOfLines={1}>{tx.beneficiary_data?.bank || 'N/A'}</Text>
                <Text style={[wdStyles.cell, { width: 180 }]} numberOfLines={1}>{tx.beneficiary_data?.full_name || 'N/A'}</Text>
                <Text style={[wdStyles.cell, { width: 120 }]}>{tx.beneficiary_data?.id_document || 'N/A'}</Text>
                <Text style={[wdStyles.cell, { width: 180 }]}>{tx.beneficiary_data?.account_number || 'N/A'}</Text>
                <Text style={[wdStyles.cell, { width: 70 }]}>Bs</Text>
                <Text style={[wdStyles.cell, { width: 120, fontWeight: '600', color: '#10b981' }]}>
                  {tx.amount_output?.toFixed(2)}
                </Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      {/* Pagination */}
      <View style={wdStyles.pagination}>
        <Text style={wdStyles.paginationInfo}>
          {selectedItems.length} de {filteredWithdrawals.length} fila(s) seleccionadas
        </Text>
        <Text style={wdStyles.paginationInfo}>Total de registros: {filteredWithdrawals.length}</Text>
        
        <View style={wdStyles.paginationRight}>
          <Text style={wdStyles.paginationLabel}>Filas Por Página</Text>
          <TouchableOpacity 
            style={wdStyles.paginationSelect}
            onPress={() => setItemsPerPage(itemsPerPage === 10 ? 25 : itemsPerPage === 25 ? 50 : 10)}
          >
            <Text style={wdStyles.paginationSelectText}>{itemsPerPage}</Text>
            <Ionicons name="chevron-down" size={16} color="#6b7280" />
          </TouchableOpacity>
          
          <Text style={wdStyles.paginationLabel}>Página {currentPage} de {totalPages || 1}</Text>
          
          <View style={wdStyles.paginationButtons}>
            <TouchableOpacity 
              style={wdStyles.paginationButton}
              onPress={() => setCurrentPage(1)}
              disabled={currentPage === 1}
            >
              <Ionicons name="play-back" size={16} color={currentPage === 1 ? '#d1d5db' : '#6b7280'} />
            </TouchableOpacity>
            <TouchableOpacity 
              style={wdStyles.paginationButton}
              onPress={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              <Ionicons name="chevron-back" size={16} color={currentPage === 1 ? '#d1d5db' : '#6b7280'} />
            </TouchableOpacity>
            <TouchableOpacity 
              style={wdStyles.paginationButton}
              onPress={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages || totalPages === 0}
            >
              <Ionicons name="chevron-forward" size={16} color={currentPage === totalPages ? '#d1d5db' : '#6b7280'} />
            </TouchableOpacity>
            <TouchableOpacity 
              style={wdStyles.paginationButton}
              onPress={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages || totalPages === 0}
            >
              <Ionicons name="play-forward" size={16} color={currentPage === totalPages ? '#d1d5db' : '#6b7280'} />
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* Detail/Process Modal */}
      <Modal visible={showDetailModal} animationType="slide" transparent>
        <KeyboardAvoidingView style={styles.modalOverlay} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.modalContent, { maxWidth: 500 }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Procesar Remesa</Text>
              <TouchableOpacity onPress={() => { setShowDetailModal(false); setSelectedTx(null); setProofImage(null); }} style={styles.modalClose}>
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

      {/* History Modal */}
      <Modal visible={showHistoryModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, { maxWidth: 500 }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Historial de la Remesa</Text>
              <TouchableOpacity onPress={() => { setShowHistoryModal(false); setSelectedTx(null); }} style={styles.modalClose}>
                <Ionicons name="close" size={24} color="#6b7280" />
              </TouchableOpacity>
            </View>

            {selectedTx && (
              <ScrollView style={styles.modalBody}>
                <View style={wdStyles.historyItem}>
                  <View style={wdStyles.historyDot} />
                  <View style={wdStyles.historyContent}>
                    <Text style={wdStyles.historyTitle}>Remesa creada</Text>
                    <Text style={wdStyles.historyDate}>{formatDate(selectedTx.created_at)}</Text>
                  </View>
                </View>
                {selectedTx.status !== 'pending' && (
                  <View style={wdStyles.historyItem}>
                    <View style={[wdStyles.historyDot, { backgroundColor: getStatusColor(selectedTx.status) }]} />
                    <View style={wdStyles.historyContent}>
                      <Text style={wdStyles.historyTitle}>Estado: {getStatusLabel(selectedTx.status)}</Text>
                      <Text style={wdStyles.historyDate}>{formatDate(selectedTx.updated_at || selectedTx.created_at)}</Text>
                    </View>
                  </View>
                )}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

// Styles for WithdrawalsTab
const wdStyles = StyleSheet.create({
  container: {
    flex: 1,
  },
  statusTabsContainer: {
    marginBottom: 12,
  },
  statusTabs: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 4,
  },
  statusTab: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#f1f5f9',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusTabText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#374151',
  },
  statusBadge: {
    backgroundColor: '#ef4444',
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
  },
  statusBadgeText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
  },
  bankFiltersContainer: {
    marginBottom: 12,
  },
  bankFilters: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 4,
  },
  bankFilter: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
    backgroundColor: '#e2e8f0',
  },
  bankFilterActive: {
    backgroundColor: '#f59e0b',
  },
  bankFilterText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#475569',
  },
  bankFilterTextActive: {
    color: '#fff',
  },
  searchFilters: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  searchInput: {
    flex: 1,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#1f2937',
  },
  searchButton: {
    backgroundColor: '#f59e0b',
    paddingHorizontal: 14,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  clearButton: {
    backgroundColor: '#ef4444',
    paddingHorizontal: 14,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  exportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#10b981',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    alignSelf: 'flex-start',
    marginBottom: 12,
    gap: 6,
    marginLeft: 4,
  },
  exportButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  table: {
    minWidth: SCREEN_WIDTH > 1200 ? 1800 : 1400,
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    overflow: 'hidden',
  },
  tableHeader: {
    flexDirection: 'row',
    backgroundColor: '#f8fafc',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    paddingVertical: 12,
  },
  headerCell: {
    fontSize: 12,
    fontWeight: '600',
    color: '#475569',
    paddingHorizontal: 8,
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    paddingVertical: 12,
    alignItems: 'center',
  },
  cell: {
    fontSize: 13,
    color: '#374151',
    paddingHorizontal: 8,
  },
  checkboxCell: {
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionsCell: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  statusBadgeInline: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusBadgeInlineText: {
    fontSize: 11,
    fontWeight: '600',
  },
  payNowButton: {
    backgroundColor: '#10b981',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  payNowText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  emptyRow: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    color: '#9ca3af',
    fontSize: 14,
  },
  pagination: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
    paddingHorizontal: 4,
    flexWrap: 'wrap',
    gap: 12,
  },
  paginationInfo: {
    fontSize: 13,
    color: '#6b7280',
  },
  paginationRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flexWrap: 'wrap',
  },
  paginationLabel: {
    fontSize: 13,
    color: '#6b7280',
  },
  paginationSelect: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  paginationSelectText: {
    fontSize: 13,
    color: '#374151',
  },
  paginationButtons: {
    flexDirection: 'row',
    gap: 4,
  },
  paginationButton: {
    padding: 8,
    borderRadius: 6,
    backgroundColor: '#f1f5f9',
  },
  historyItem: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  historyDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#10b981',
    marginTop: 4,
  },
  historyContent: {
    flex: 1,
  },
  historyTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
  },
  historyDate: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 2,
  },
});

// Recharges Tab - Now includes both PIX and VES recharges
function RechargesTab() {
  const [pixRecharges, setPixRecharges] = useState<any[]>([]);
  const [vesRecharges, setVesRecharges] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);
  const [selectedVES, setSelectedVES] = useState<any>(null);
  const [voucherFullscreen, setVoucherFullscreen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [activeSubTab, setActiveSubTab] = useState<'ves' | 'pix'>('ves');

  useEffect(() => {
    loadAllRecharges();
  }, []);

  const loadAllRecharges = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      
      // Load PIX recharges
      const pixResponse = await axios.get(`${BACKEND_URL}/api/admin/recharges/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPixRecharges(pixResponse.data.recharges || []);
      
      // Load VES recharges
      const vesResponse = await axios.get(`${BACKEND_URL}/api/admin/recharges/ves/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setVesRecharges(vesResponse.data.recharges || []);
    } catch (error) {
      console.error('Error loading recharges:', error);
    } finally {
      setLoading(false);
    }
  };

  const processPixRecharge = async (txId: string, approved: boolean) => {
    setProcessing(txId);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/recharges/approve`,
        { transaction_id: txId, approved },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', approved ? 'Recarga PIX aprobada' : 'Recarga PIX rechazada');
      loadAllRecharges();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    } finally {
      setProcessing(null);
    }
  };

  const processVESRecharge = async (approved: boolean) => {
    if (!selectedVES) return;
    if (!approved && !rejectionReason.trim()) {
      showAlert('Error', 'Ingresa el motivo del rechazo');
      return;
    }
    
    setProcessing(selectedVES.transaction_id);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/recharges/ves/approve`,
        { 
          transaction_id: selectedVES.transaction_id, 
          approved,
          rejection_reason: approved ? null : rejectionReason.trim()
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', approved ? 'Recarga VES aprobada - RIS acreditados' : 'Recarga VES rechazada');
      setSelectedVES(null);
      setRejectionReason('');
      loadAllRecharges();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo procesar');
    } finally {
      setProcessing(null);
    }
  };

  const formatDate = (date: string) => {
    if (!date) return 'N/A';
    return new Date(date).toLocaleString('es', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  // Fullscreen Voucher Modal
  if (voucherFullscreen && selectedVES?.voucher_image) {
    return (
      <Modal visible={true} animationType="fade" transparent>
        <View style={styles.voucherFullscreenOverlay}>
          <TouchableOpacity 
            style={styles.voucherFullscreenClose} 
            onPress={() => setVoucherFullscreen(false)}
          >
            <Ionicons name="close-circle" size={40} color="#fff" />
          </TouchableOpacity>
          <Image 
            source={{ uri: selectedVES.voucher_image }} 
            style={styles.voucherFullscreenImage} 
            resizeMode="contain" 
          />
          <View style={styles.voucherFullscreenInfo}>
            <Text style={styles.voucherFullscreenAmount}>{selectedVES.amount_input?.toLocaleString()} VES</Text>
            <Text style={styles.voucherFullscreenRef}>Ref: {selectedVES.reference_number}</Text>
          </View>
        </View>
      </Modal>
    );
  }

  // VES Recharge Detail Modal
  if (selectedVES) {
    return (
      <View style={styles.tabContent}>
        <View style={styles.vesDetailHeader}>
          <TouchableOpacity onPress={() => { setSelectedVES(null); setRejectionReason(''); }} style={styles.vesBackBtn}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.vesDetailTitle}>Revisar Recarga VES</Text>
        </View>

        <ScrollView showsVerticalScrollIndicator={false}>
          {/* User Info */}
          <View style={styles.vesUserCard}>
            {selectedVES.user_picture ? (
              <Image source={{ uri: selectedVES.user_picture }} style={styles.vesUserAvatar} />
            ) : (
              <View style={styles.vesUserAvatarPlaceholder}>
                <Text style={styles.vesUserAvatarText}>{selectedVES.user_name?.charAt(0)?.toUpperCase()}</Text>
              </View>
            )}
            <View style={styles.vesUserInfo}>
              <Text style={styles.vesUserName}>{selectedVES.user_name}</Text>
              <Text style={styles.vesUserEmail}>{selectedVES.user_email}</Text>
              <Text style={styles.vesDate}>{formatDate(selectedVES.created_at)}</Text>
            </View>
          </View>

          {/* Amount Summary */}
          <View style={styles.vesAmountCard}>
            <View style={styles.vesAmountRow}>
              <View style={styles.vesAmountItem}>
                <Text style={styles.vesAmountLabel}>Pagó</Text>
                <Text style={styles.vesAmountValue}>{selectedVES.amount_input?.toLocaleString()} VES</Text>
              </View>
              <Ionicons name="arrow-forward" size={24} color="#F5A623" />
              <View style={styles.vesAmountItem}>
                <Text style={styles.vesAmountLabel}>Recibirá</Text>
                <Text style={[styles.vesAmountValue, { color: '#059669' }]}>{selectedVES.amount_output?.toFixed(2)} RIS</Text>
              </View>
            </View>
          </View>

          {/* Payment Details */}
          <View style={styles.vesDetailsCard}>
            <Text style={styles.vesDetailsTitle}>Detalles del Pago</Text>
            <View style={styles.vesDetailRow}>
              <Text style={styles.vesDetailLabel}>Método:</Text>
              <Text style={styles.vesDetailValue}>
                {selectedVES.payment_method === 'pago_movil' ? 'Pago Móvil' : 'Transferencia Bancaria'}
              </Text>
            </View>
            <View style={styles.vesDetailRow}>
              <Text style={styles.vesDetailLabel}>Referencia:</Text>
              <Text style={[styles.vesDetailValue, { fontWeight: '700', color: '#2563eb' }]}>{selectedVES.reference_number}</Text>
            </View>
            <View style={styles.vesDetailRow}>
              <Text style={styles.vesDetailLabel}>ID Transacción:</Text>
              <Text style={styles.vesDetailValue}>{selectedVES.transaction_id?.substring(0, 12)}...</Text>
            </View>
          </View>

          {/* Voucher Image - Tap to fullscreen */}
          <Text style={styles.voucherSectionTitle}>📸 Comprobante de Pago</Text>
          <Text style={styles.voucherTapHint}>Toca la imagen para verla en pantalla completa</Text>
          <TouchableOpacity 
            style={styles.voucherContainer} 
            onPress={() => setVoucherFullscreen(true)}
            activeOpacity={0.9}
          >
            <Image 
              source={{ uri: selectedVES.voucher_image }} 
              style={styles.voucherPreviewImage} 
              resizeMode="contain" 
            />
            <View style={styles.voucherExpandIcon}>
              <Ionicons name="expand" size={24} color="#fff" />
            </View>
          </TouchableOpacity>

          {/* Rejection Reason */}
          <View style={styles.vesRejectSection}>
            <Text style={styles.vesRejectLabel}>Motivo de rechazo (si aplica):</Text>
            <TextInput
              style={styles.vesRejectInput}
              value={rejectionReason}
              onChangeText={setRejectionReason}
              placeholder="Ej: Monto incorrecto, referencia no coincide..."
              multiline
            />
          </View>

          {/* Action Buttons */}
          <View style={styles.vesActionButtons}>
            <TouchableOpacity
              style={styles.vesRejectBtn}
              onPress={() => processVESRecharge(false)}
              disabled={processing === selectedVES.transaction_id}
            >
              {processing === selectedVES.transaction_id ? (
                <ActivityIndicator color="#dc2626" size="small" />
              ) : (
                <>
                  <Ionicons name="close-circle" size={20} color="#dc2626" />
                  <Text style={styles.vesRejectBtnText}>Rechazar</Text>
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.vesApproveBtn}
              onPress={() => processVESRecharge(true)}
              disabled={processing === selectedVES.transaction_id}
            >
              {processing === selectedVES.transaction_id ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={20} color="#fff" />
                  <Text style={styles.vesApproveBtnText}>Aprobar y Acreditar</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    );
  }

  const totalPending = pixRecharges.length + vesRecharges.length;

  return (
    <View style={styles.tabContent}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recargas Pendientes</Text>
        <View style={styles.countBadge}>
          <Text style={styles.countText}>{totalPending}</Text>
        </View>
      </View>

      {/* Sub-tabs for PIX vs VES */}
      <View style={styles.subTabsContainer}>
        <TouchableOpacity 
          style={[styles.subTab, activeSubTab === 'ves' && styles.subTabActive]}
          onPress={() => setActiveSubTab('ves')}
        >
          <Ionicons name="cash" size={18} color={activeSubTab === 'ves' ? '#F5A623' : '#6b7280'} />
          <Text style={[styles.subTabText, activeSubTab === 'ves' && styles.subTabTextActive]}>
            VES ({vesRecharges.length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={[styles.subTab, activeSubTab === 'pix' && styles.subTabActive]}
          onPress={() => setActiveSubTab('pix')}
        >
          <Ionicons name="qr-code" size={18} color={activeSubTab === 'pix' ? '#F5A623' : '#6b7280'} />
          <Text style={[styles.subTabText, activeSubTab === 'pix' && styles.subTabTextActive]}>
            PIX ({pixRecharges.length})
          </Text>
        </TouchableOpacity>
      </View>
      
      {totalPending === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle" size={64} color="#10b981" />
          <Text style={styles.emptyTitle}>¡Todo al día!</Text>
          <Text style={styles.emptyText}>No hay recargas pendientes</Text>
        </View>
      ) : activeSubTab === 'ves' ? (
        // VES Recharges List
        vesRecharges.length === 0 ? (
          <View style={styles.emptyStateSmall}>
            <Ionicons name="cash-outline" size={40} color="#9ca3af" />
            <Text style={styles.emptyTextSmall}>No hay recargas VES pendientes</Text>
          </View>
        ) : (
          vesRecharges.map((tx) => (
            <TouchableOpacity 
              key={tx.transaction_id} 
              style={styles.vesRechargeCard}
              onPress={() => setSelectedVES(tx)}
            >
              <View style={styles.vesRechargeHeader}>
                <View style={styles.vesRechargeUser}>
                  {tx.user_picture ? (
                    <Image source={{ uri: tx.user_picture }} style={styles.vesRechargeAvatar} />
                  ) : (
                    <View style={styles.vesRechargeAvatarPlaceholder}>
                      <Text style={styles.vesRechargeAvatarText}>{tx.user_name?.charAt(0)?.toUpperCase()}</Text>
                    </View>
                  )}
                  <View>
                    <Text style={styles.vesRechargeName}>{tx.user_name}</Text>
                    <Text style={styles.vesRechargeDate}>{formatDate(tx.created_at)}</Text>
                  </View>
                </View>
                <View style={styles.vesRechargeAmounts}>
                  <Text style={styles.vesRechargeVES}>{tx.amount_input?.toLocaleString()} VES</Text>
                  <Text style={styles.vesRechargeRIS}>+{tx.amount_output?.toFixed(2)} RIS</Text>
                </View>
              </View>
              <View style={styles.vesRechargeFooter}>
                <View style={styles.vesRechargeMethod}>
                  <Ionicons name={tx.payment_method === 'pago_movil' ? 'phone-portrait' : 'business'} size={14} color="#6b7280" />
                  <Text style={styles.vesRechargeMethodText}>
                    {tx.payment_method === 'pago_movil' ? 'Pago Móvil' : 'Transferencia'}
                  </Text>
                </View>
                <View style={styles.vesRechargeRef}>
                  <Text style={styles.vesRechargeRefText}>Ref: {tx.reference_number}</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
              </View>
            </TouchableOpacity>
          ))
        )
      ) : (
        // PIX Recharges List
        pixRecharges.length === 0 ? (
          <View style={styles.emptyStateSmall}>
            <Ionicons name="qr-code-outline" size={40} color="#9ca3af" />
            <Text style={styles.emptyTextSmall}>No hay recargas PIX pendientes</Text>
          </View>
        ) : (
          pixRecharges.map((tx) => (
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
                  onPress={() => processPixRecharge(tx.transaction_id, false)}
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
                  onPress={() => processPixRecharge(tx.transaction_id, true)}
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
        )
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
  const [responseImage, setResponseImage] = useState<string | null>(null);
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

  const pickImage = async () => {
    try {
      const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permissionResult.granted) {
        showAlert('Permiso Requerido', 'Necesitamos acceso a tu galería');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: false,
        quality: 0.7,
        base64: true,
      });

      if (!result.canceled && result.assets[0].base64) {
        setResponseImage(`data:image/jpeg;base64,${result.assets[0].base64}`);
      }
    } catch (error) {
      console.error('Error picking image:', error);
    }
  };

  const sendResponse = async () => {
    if ((!responseText.trim() && !responseImage) || !selectedChat) return;

    setSending(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/support/respond`,
        { 
          user_id: selectedChat.user_id, 
          message: responseText.trim(),
          image: responseImage 
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setResponseText('');
      setResponseImage(null);
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
          {responseImage && (
            <View style={styles.imagePreviewContainer}>
              <Image source={{ uri: responseImage }} style={styles.imagePreview} />
              <TouchableOpacity style={styles.removeImageBtn} onPress={() => setResponseImage(null)}>
                <Ionicons name="close-circle" size={24} color="#dc2626" />
              </TouchableOpacity>
            </View>
          )}
          <View style={styles.inputRow}>
            <TouchableOpacity style={styles.attachImageBtn} onPress={pickImage}>
              <Ionicons name="image-outline" size={24} color="#6b7280" />
            </TouchableOpacity>
            <TextInput
              style={styles.responseInput}
              value={responseText}
              onChangeText={setResponseText}
              placeholder="Escribe tu respuesta..."
              multiline
            />
            <TouchableOpacity 
              style={[styles.sendButton, (!responseText.trim() && !responseImage) && styles.sendButtonDisabled]} 
              onPress={sendResponse} 
              disabled={sending || (!responseText.trim() && !responseImage)}
            >
              {sending ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="send" size={20} color="#fff" />}
            </TouchableOpacity>
          </View>
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

// Users Tab - Complete User Management
function UsersTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [stats, setStats] = useState<{ total: number; online: number; verified: number }>({ total: 0, online: 0, verified: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [userDetails, setUserDetails] = useState<any>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [activeDetailTab, setActiveDetailTab] = useState<'info' | 'recharges' | 'withdrawals' | 'beneficiaries' | 'kyc'>('info');
  const [deletingUser, setDeletingUser] = useState(false);
  const [showDeletedUsers, setShowDeletedUsers] = useState(false);
  const [deletedUsers, setDeletedUsers] = useState<any[]>([]);
  const [loadingDeleted, setLoadingDeleted] = useState(false);

  useEffect(() => {
    loadUsers();
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

  const loadDeletedUsers = async () => {
    setLoadingDeleted(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/users/deleted`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDeletedUsers(response.data.users);
    } catch (error) {
      console.error('Error loading deleted users:', error);
    } finally {
      setLoadingDeleted(false);
    }
  };

  const deleteUser = async (userId: string, userName: string) => {
    if (Platform.OS === 'web') {
      if (!confirm(`¿Estás seguro de eliminar a ${userName}?\n\nEsta acción se puede revertir desde "Usuarios Eliminados".`)) {
        return;
      }
    } else {
      // For native, use Alert
      Alert.alert(
        'Eliminar Usuario',
        `¿Estás seguro de eliminar a ${userName}?\n\nEsta acción se puede revertir desde "Usuarios Eliminados".`,
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Eliminar', style: 'destructive', onPress: () => performDelete(userId) }
        ]
      );
      return;
    }
    await performDelete(userId);
  };

  const performDelete = async (userId: string) => {
    setDeletingUser(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.delete(`${BACKEND_URL}/api/admin/users/${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      showAlert('Éxito', 'Usuario eliminado correctamente');
      setSelectedUser(null);
      setUserDetails(null);
      loadUsers();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo eliminar el usuario');
    } finally {
      setDeletingUser(false);
    }
  };

  const restoreUser = async (userId: string, userName: string) => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(`${BACKEND_URL}/api/admin/users/${userId}/restore`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      showAlert('Éxito', `Usuario ${userName} restaurado correctamente`);
      loadDeletedUsers();
      loadUsers();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo restaurar el usuario');
    }
  };

  const loadUserDetails = async (userId: string) => {
    setLoadingDetails(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/users/${userId}/complete`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setUserDetails(response.data);
    } catch (error) {
      console.error('Error loading user details:', error);
      showAlert('Error', 'No se pudo cargar la información del usuario');
    } finally {
      setLoadingDetails(false);
    }
  };

  const openUserDetail = (user: any) => {
    setSelectedUser(user);
    setActiveDetailTab('info');
    loadUserDetails(user.user_id);
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

  const formatDate = (date: string) => {
    if (!date) return 'N/A';
    return new Date(date).toLocaleString('es', { 
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' 
    });
  };

  const formatShortDate = (date: string) => {
    if (!date) return 'N/A';
    return new Date(date).toLocaleDateString('es', { day: '2-digit', month: 'short', year: '2-digit' });
  };

  // ============ USER DETAIL VIEW ============
  if (selectedUser && userDetails) {
    return (
      <View style={styles.tabContent}>
        {/* Header */}
        <View style={styles.userDetailHeader}>
          <TouchableOpacity onPress={() => { setSelectedUser(null); setUserDetails(null); }} style={styles.userDetailBackBtn}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.userDetailTitle}>Perfil Completo</Text>
          <TouchableOpacity onPress={() => loadUserDetails(selectedUser.user_id)} style={styles.userDetailRefresh}>
            <Ionicons name="refresh" size={20} color="#2563eb" />
          </TouchableOpacity>
        </View>

        {loadingDetails ? (
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 }}>
            <ActivityIndicator size="large" color="#2563eb" />
            <Text style={{ marginTop: 12, color: '#6b7280' }}>Cargando información...</Text>
          </View>
        ) : (
          <ScrollView showsVerticalScrollIndicator={false}>
            {/* User Profile Card */}
            <View style={styles.userProfileCard}>
              <View style={styles.userProfileTop}>
                <View style={styles.userProfileAvatarContainer}>
                  {userDetails.profile.picture ? (
                    <Image source={{ uri: userDetails.profile.picture }} style={styles.userProfileAvatar} />
                  ) : (
                    <View style={styles.userProfileAvatarPlaceholder}>
                      <Text style={styles.userProfileAvatarText}>{userDetails.profile.name?.charAt(0)?.toUpperCase()}</Text>
                    </View>
                  )}
                  {userDetails.profile.is_online && <View style={styles.userProfileOnline} />}
                </View>
                <View style={styles.userProfileInfo}>
                  <Text style={styles.userProfileName}>{userDetails.profile.name}</Text>
                  <Text style={styles.userProfileEmail}>{userDetails.profile.email}</Text>
                  <View style={styles.userProfileBadges}>
                    <View style={[styles.profileBadge, userDetails.kyc.verification_status === 'verified' ? styles.badgeGreen : styles.badgeYellow]}>
                      <Ionicons name={userDetails.kyc.verification_status === 'verified' ? 'checkmark-circle' : 'time'} size={12} color={userDetails.kyc.verification_status === 'verified' ? '#059669' : '#d97706'} />
                      <Text style={[styles.profileBadgeText, userDetails.kyc.verification_status === 'verified' ? { color: '#059669' } : { color: '#d97706' }]}>
                        {userDetails.kyc.verification_status === 'verified' ? 'Verificado' : 'Pendiente'}
                      </Text>
                    </View>
                    {userDetails.kyc.email_verified && (
                      <View style={[styles.profileBadge, styles.badgeBlue]}>
                        <Ionicons name="mail" size={12} color="#2563eb" />
                        <Text style={[styles.profileBadgeText, { color: '#2563eb' }]}>Email</Text>
                      </View>
                    )}
                  </View>
                </View>
              </View>
              <View style={styles.userProfileBalance}>
                <Text style={styles.userProfileBalanceLabel}>Saldo Actual</Text>
                <Text style={styles.userProfileBalanceValue}>{userDetails.profile.balance_ris?.toFixed(2)} RIS</Text>
              </View>
              
              {/* Delete User Button */}
              {userDetails.profile.role !== 'super_admin' && (
                <TouchableOpacity 
                  style={styles.deleteUserBtn}
                  onPress={() => deleteUser(userDetails.profile.user_id, userDetails.profile.name)}
                  disabled={deletingUser}
                >
                  {deletingUser ? (
                    <ActivityIndicator size="small" color="#dc2626" />
                  ) : (
                    <>
                      <Ionicons name="trash-outline" size={18} color="#dc2626" />
                      <Text style={styles.deleteUserBtnText}>Eliminar Usuario</Text>
                    </>
                  )}
                </TouchableOpacity>
              )}
            </View>

            {/* Stats Summary */}
            <View style={styles.userStatsGrid}>
              <View style={[styles.userStatBox, { backgroundColor: '#eff6ff' }]}>
                <Text style={[styles.userStatBoxValue, { color: '#2563eb' }]}>{userDetails.stats.total_recharges}</Text>
                <Text style={styles.userStatBoxLabel}>Recargas</Text>
              </View>
              <View style={[styles.userStatBox, { backgroundColor: '#fef3c7' }]}>
                <Text style={[styles.userStatBoxValue, { color: '#d97706' }]}>{userDetails.stats.total_withdrawals}</Text>
                <Text style={styles.userStatBoxLabel}>Envíos</Text>
              </View>
              <View style={[styles.userStatBox, { backgroundColor: '#f0fdf4' }]}>
                <Text style={[styles.userStatBoxValue, { color: '#059669' }]}>{userDetails.stats.total_recharged_ris?.toFixed(0)}</Text>
                <Text style={styles.userStatBoxLabel}>RIS Cargados</Text>
              </View>
              <View style={[styles.userStatBox, { backgroundColor: '#fef2f2' }]}>
                <Text style={[styles.userStatBoxValue, { color: '#dc2626' }]}>{userDetails.stats.total_ves_sent?.toFixed(0)}</Text>
                <Text style={styles.userStatBoxLabel}>VES Enviados</Text>
              </View>
            </View>

            {/* Detail Tabs */}
            <View style={styles.detailTabs}>
              {[
                { key: 'info', label: 'Info', icon: 'person' },
                { key: 'recharges', label: 'Recargas', icon: 'add-circle' },
                { key: 'withdrawals', label: 'Envíos', icon: 'send' },
                { key: 'beneficiaries', label: 'Beneficiarios', icon: 'people' },
                { key: 'kyc', label: 'KYC', icon: 'document' },
              ].map(tab => (
                <TouchableOpacity
                  key={tab.key}
                  style={[styles.detailTab, activeDetailTab === tab.key && styles.detailTabActive]}
                  onPress={() => setActiveDetailTab(tab.key as any)}
                >
                  <Ionicons name={tab.icon as any} size={16} color={activeDetailTab === tab.key ? '#2563eb' : '#6b7280'} />
                  <Text style={[styles.detailTabText, activeDetailTab === tab.key && styles.detailTabTextActive]}>{tab.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Tab Content */}
            {activeDetailTab === 'info' && (
              <View style={styles.detailSection}>
                <Text style={styles.detailSectionTitle}>Información del Perfil</Text>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>ID:</Text><Text style={styles.infoValue}>{userDetails.profile.user_id}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Nombre:</Text><Text style={styles.infoValue}>{userDetails.profile.full_name || userDetails.profile.name}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Teléfono:</Text><Text style={styles.infoValue}>{userDetails.profile.phone || 'No registrado'}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Registro:</Text><Text style={styles.infoValue}>{formatDate(userDetails.profile.created_at)}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Método:</Text><Text style={styles.infoValue}>{userDetails.profile.registration_method === 'email' ? 'Email/Contraseña' : 'Google'}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Último login:</Text><Text style={styles.infoValue}>{formatDate(userDetails.profile.last_login)}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Última actividad:</Text><Text style={styles.infoValue}>{formatLastSeen(userDetails.profile.last_seen)}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Contraseña:</Text><Text style={styles.infoValue}>{userDetails.security.password_set ? 'Configurada' : 'No configurada'}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Notificaciones:</Text><Text style={styles.infoValue}>{userDetails.security.fcm_token}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Políticas:</Text><Text style={styles.infoValue}>{userDetails.kyc.accepted_policies ? 'Aceptadas' : 'No aceptadas'}</Text></View>
              </View>
            )}

            {activeDetailTab === 'recharges' && (
              <View style={styles.detailSection}>
                <Text style={styles.detailSectionTitle}>Historial de Recargas ({userDetails.recharges.length})</Text>
                {userDetails.recharges.length === 0 ? (
                  <Text style={styles.noDataText}>Sin recargas registradas</Text>
                ) : (
                  userDetails.recharges.map((r: any, idx: number) => (
                    <View key={idx} style={styles.historyCard}>
                      <View style={styles.historyCardTop}>
                        <View>
                          <Text style={styles.historyAmount}>R$ {r.amount_brl?.toFixed(2)}</Text>
                          <Text style={styles.historySubtext}>→ {r.amount_ris?.toFixed(2)} RIS</Text>
                        </View>
                        <View style={[styles.historyStatus, r.status === 'completed' ? styles.statusCompleted : r.status === 'pending' ? styles.statusPending : styles.statusRejected]}>
                          <Text style={styles.historyStatusText}>{r.status === 'completed' ? 'Completada' : r.status === 'pending' ? 'Pendiente' : 'Rechazada'}</Text>
                        </View>
                      </View>
                      <Text style={styles.historyDate}>{formatDate(r.created_at)}</Text>
                      <Text style={styles.historyMeta}>ID: {r.transaction_id?.substring(0, 12)}... • {r.payment_method?.toUpperCase()}</Text>
                    </View>
                  ))
                )}
              </View>
            )}

            {activeDetailTab === 'withdrawals' && (
              <View style={styles.detailSection}>
                <Text style={styles.detailSectionTitle}>Historial de Envíos ({userDetails.withdrawals.length})</Text>
                {userDetails.withdrawals.length === 0 ? (
                  <Text style={styles.noDataText}>Sin envíos registrados</Text>
                ) : (
                  userDetails.withdrawals.map((w: any, idx: number) => (
                    <View key={idx} style={styles.historyCard}>
                      <View style={styles.historyCardTop}>
                        <View>
                          <Text style={styles.historyAmount}>{w.amount_ris?.toFixed(2)} RIS</Text>
                          <Text style={styles.historySubtext}>→ {w.amount_ves?.toFixed(2)} VES</Text>
                        </View>
                        <View style={[styles.historyStatus, w.status === 'completed' ? styles.statusCompleted : w.status === 'pending' ? styles.statusPending : styles.statusRejected]}>
                          <Text style={styles.historyStatusText}>{w.status === 'completed' ? 'Completado' : w.status === 'pending' ? 'Pendiente' : 'Rechazado'}</Text>
                        </View>
                      </View>
                      {w.beneficiary && (
                        <View style={styles.beneficiaryPreview}>
                          <Ionicons name="person" size={12} color="#6b7280" />
                          <Text style={styles.beneficiaryPreviewText}>{w.beneficiary.full_name} • {w.beneficiary.bank}</Text>
                        </View>
                      )}
                      <Text style={styles.historyDate}>{formatDate(w.created_at)}</Text>
                      {w.rejection_reason && <Text style={styles.rejectionText}>Motivo: {w.rejection_reason}</Text>}
                    </View>
                  ))
                )}
              </View>
            )}

            {activeDetailTab === 'beneficiaries' && (
              <View style={styles.detailSection}>
                <Text style={styles.detailSectionTitle}>Beneficiarios Guardados ({userDetails.beneficiaries.length})</Text>
                {userDetails.beneficiaries.length === 0 ? (
                  <Text style={styles.noDataText}>Sin beneficiarios registrados</Text>
                ) : (
                  userDetails.beneficiaries.map((b: any, idx: number) => (
                    <View key={idx} style={styles.beneficiaryCard}>
                      <View style={styles.beneficiaryCardHeader}>
                        <Ionicons name="person-circle" size={32} color="#2563eb" />
                        <View style={styles.beneficiaryCardInfo}>
                          <Text style={styles.beneficiaryCardName}>{b.full_name}</Text>
                          <Text style={styles.beneficiaryCardBank}>{b.bank_code} - {b.bank}</Text>
                        </View>
                      </View>
                      <View style={styles.beneficiaryCardDetails}>
                        <View style={styles.beneficiaryDetailRow}>
                          <Ionicons name="card" size={14} color="#6b7280" />
                          <Text style={styles.beneficiaryDetailText}>{b.account_number}</Text>
                        </View>
                        <View style={styles.beneficiaryDetailRow}>
                          <Ionicons name="id-card" size={14} color="#6b7280" />
                          <Text style={styles.beneficiaryDetailText}>{b.id_document}</Text>
                        </View>
                        <View style={styles.beneficiaryDetailRow}>
                          <Ionicons name="call" size={14} color="#6b7280" />
                          <Text style={styles.beneficiaryDetailText}>{b.phone_number}</Text>
                        </View>
                      </View>
                      <Text style={styles.beneficiaryCardDate}>Agregado: {formatShortDate(b.created_at)}</Text>
                    </View>
                  ))
                )}
              </View>
            )}

            {activeDetailTab === 'kyc' && (
              <View style={styles.detailSection}>
                <Text style={styles.detailSectionTitle}>Documentos KYC</Text>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Estado:</Text><Text style={[styles.infoValue, { fontWeight: '600', color: userDetails.kyc.verification_status === 'verified' ? '#059669' : '#d97706' }]}>{userDetails.kyc.verification_status?.toUpperCase()}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Documento:</Text><Text style={styles.infoValue}>{userDetails.kyc.document_number || 'No registrado'}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>CPF:</Text><Text style={styles.infoValue}>{userDetails.kyc.cpf_number || 'No registrado'}</Text></View>
                <View style={styles.infoRow}><Text style={styles.infoLabel}>Enviado:</Text><Text style={styles.infoValue}>{formatDate(userDetails.kyc.verification_submitted_at)}</Text></View>
                {userDetails.kyc.verified_at && <View style={styles.infoRow}><Text style={styles.infoLabel}>Verificado:</Text><Text style={styles.infoValue}>{formatDate(userDetails.kyc.verified_at)}</Text></View>}
                {userDetails.kyc.rejection_reason && <View style={styles.infoRow}><Text style={styles.infoLabel}>Motivo rechazo:</Text><Text style={[styles.infoValue, { color: '#dc2626' }]}>{userDetails.kyc.rejection_reason}</Text></View>}
                
                {userDetails.kyc.id_document_image && (
                  <>
                    <Text style={styles.kycDocTitle}>📄 Documento de Identidad</Text>
                    <Image source={{ uri: userDetails.kyc.id_document_image }} style={styles.kycDocImage} resizeMode="contain" />
                  </>
                )}
                
                {userDetails.kyc.cpf_image && (
                  <>
                    <Text style={styles.kycDocTitle}>📋 CPF</Text>
                    <Image source={{ uri: userDetails.kyc.cpf_image }} style={styles.kycDocImage} resizeMode="contain" />
                  </>
                )}
                
                {userDetails.kyc.selfie_image && (
                  <>
                    <Text style={styles.kycDocTitle}>🤳 Selfie</Text>
                    <Image source={{ uri: userDetails.kyc.selfie_image }} style={styles.kycSelfieSmall} resizeMode="contain" />
                  </>
                )}
              </View>
            )}

            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </View>
    );
  }

  // ============ DELETED USERS VIEW ============
  if (showDeletedUsers) {
    return (
      <View style={styles.tabContent}>
        <View style={styles.deletedUsersHeader}>
          <TouchableOpacity onPress={() => setShowDeletedUsers(false)} style={styles.userDetailBackBtn}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.deletedUsersTitle}>Usuarios Eliminados</Text>
          <TouchableOpacity onPress={loadDeletedUsers} style={styles.userDetailRefresh}>
            <Ionicons name="refresh" size={20} color="#2563eb" />
          </TouchableOpacity>
        </View>

        {loadingDeleted ? (
          <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />
        ) : deletedUsers.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="checkmark-circle" size={64} color="#10b981" />
            <Text style={styles.emptyTitle}>Sin usuarios eliminados</Text>
            <Text style={styles.emptyText}>No hay usuarios en la papelera</Text>
          </View>
        ) : (
          deletedUsers.map((u) => (
            <View key={u.user_id} style={styles.deletedUserCard}>
              <View style={styles.deletedUserInfo}>
                <View style={styles.deletedUserAvatar}>
                  <Text style={styles.deletedUserAvatarText}>{u.name?.charAt(0)?.toUpperCase() || '?'}</Text>
                </View>
                <View style={styles.deletedUserDetails}>
                  <Text style={styles.deletedUserName}>{u.name || 'Sin nombre'}</Text>
                  <Text style={styles.deletedUserEmail}>{u.email}</Text>
                  <Text style={styles.deletedUserDate}>
                    Eliminado: {u.deleted_at ? new Date(u.deleted_at).toLocaleDateString('es') : 'N/A'}
                  </Text>
                </View>
              </View>
              <TouchableOpacity 
                style={styles.restoreUserBtn}
                onPress={() => restoreUser(u.user_id, u.name)}
              >
                <Ionicons name="refresh" size={18} color="#059669" />
                <Text style={styles.restoreUserBtnText}>Restaurar</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </View>
    );
  }

  // ============ USERS LIST VIEW ============
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

      {/* Deleted Users Button */}
      <TouchableOpacity 
        style={styles.deletedUsersBtn}
        onPress={() => { setShowDeletedUsers(true); loadDeletedUsers(); }}
      >
        <Ionicons name="trash-outline" size={18} color="#dc2626" />
        <Text style={styles.deletedUsersBtnText}>Ver Usuarios Eliminados</Text>
        <Ionicons name="chevron-forward" size={18} color="#dc2626" />
      </TouchableOpacity>

      <Text style={styles.sectionTitle}>Lista de Usuarios</Text>
      <Text style={styles.sectionSubtitle}>Toca un usuario para ver toda su información</Text>
      
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
          <TouchableOpacity key={u.user_id} style={styles.userCard} onPress={() => openUserDetail(u)}>
            <View style={styles.userCardHeader}>
              <View style={styles.userAvatarContainer}>
                {u.picture ? (
                  <Image source={{ uri: u.picture }} style={styles.userAvatarImage} />
                ) : (
                  <View style={styles.userAvatar}>
                    <Text style={styles.userAvatarText}>{u.name?.charAt(0)?.toUpperCase() || '?'}</Text>
                  </View>
                )}
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
              <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
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
          </TouchableOpacity>
        ))
      )}
    </View>
  );
}

// KYC Verifications Tab - Review and approve user documents
function KYCVerificationsTab() {
  const [verifications, setVerifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [processing, setProcessing] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');

  useEffect(() => {
    loadVerifications();
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadVerifications, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadVerifications = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/verifications/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setVerifications(response.data);
    } catch (error) {
      console.error('Error loading verifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (approved: boolean) => {
    if (!selectedUser) return;
    if (!approved && !rejectionReason.trim()) {
      showAlert('Error', 'Ingresa el motivo del rechazo');
      return;
    }

    setProcessing(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/admin/verifications/decide`,
        {
          user_id: selectedUser.user_id,
          approved,
          rejection_reason: approved ? null : rejectionReason.trim()
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      showAlert('Éxito', approved ? 'Usuario verificado correctamente' : 'Usuario rechazado');
      setSelectedUser(null);
      setRejectionReason('');
      loadVerifications();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'Error al procesar');
    } finally {
      setProcessing(false);
    }
  };

  const formatDate = (date: string) => {
    if (!date) return 'N/A';
    return new Date(date).toLocaleString('es', { 
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' 
    });
  };

  // Document review modal
  if (selectedUser) {
    return (
      <View style={styles.tabContent}>
        <View style={styles.kycReviewHeader}>
          <TouchableOpacity onPress={() => setSelectedUser(null)} style={styles.kycBackBtn}>
            <Ionicons name="arrow-back" size={24} color="#0f172a" />
          </TouchableOpacity>
          <Text style={styles.kycReviewTitle}>Revisar Documentos</Text>
        </View>

        <ScrollView showsVerticalScrollIndicator={false}>
          {/* User Info */}
          <View style={styles.kycUserCard}>
            <View style={styles.kycUserInfo}>
              <Text style={styles.kycUserName}>{selectedUser.full_name || selectedUser.name}</Text>
              <Text style={styles.kycUserEmail}>{selectedUser.email}</Text>
              <Text style={styles.kycUserDate}>Enviado: {formatDate(selectedUser.verification_submitted_at)}</Text>
            </View>
          </View>

          {/* Document Details */}
          <View style={styles.kycDocSection}>
            <Text style={styles.kycDocLabel}>Número de Documento</Text>
            <Text style={styles.kycDocValue}>{selectedUser.document_number || 'N/A'}</Text>
          </View>

          <View style={styles.kycDocSection}>
            <Text style={styles.kycDocLabel}>CPF</Text>
            <Text style={styles.kycDocValue}>{selectedUser.cpf_number || 'N/A'}</Text>
          </View>

          {/* Document Images */}
          <Text style={styles.kycSectionTitle}>📄 Documento de Identidad</Text>
          {selectedUser.id_document_image ? (
            <Image source={{ uri: selectedUser.id_document_image }} style={styles.kycDocImage} resizeMode="contain" />
          ) : (
            <Text style={styles.kycNoImage}>No disponible</Text>
          )}

          <Text style={styles.kycSectionTitle}>📋 CPF</Text>
          {selectedUser.cpf_image ? (
            <Image source={{ uri: selectedUser.cpf_image }} style={styles.kycDocImage} resizeMode="contain" />
          ) : (
            <Text style={styles.kycNoImage}>No disponible</Text>
          )}

          <Text style={styles.kycSectionTitle}>🤳 Selfie (Foto de Perfil)</Text>
          {selectedUser.selfie_image ? (
            <Image source={{ uri: selectedUser.selfie_image }} style={styles.kycSelfieImage} resizeMode="contain" />
          ) : (
            <Text style={styles.kycNoImage}>No disponible</Text>
          )}

          {/* Rejection Reason Input */}
          <View style={styles.kycRejectSection}>
            <Text style={styles.kycRejectLabel}>Motivo de rechazo (si aplica):</Text>
            <TextInput
              style={styles.kycRejectInput}
              value={rejectionReason}
              onChangeText={setRejectionReason}
              placeholder="Ej: Documento ilegible, foto borrosa..."
              multiline
            />
          </View>

          {/* Action Buttons */}
          <View style={styles.kycActionButtons}>
            <TouchableOpacity
              style={styles.kycRejectBtn}
              onPress={() => handleDecision(false)}
              disabled={processing}
            >
              {processing ? (
                <ActivityIndicator color="#dc2626" size="small" />
              ) : (
                <>
                  <Ionicons name="close-circle" size={20} color="#dc2626" />
                  <Text style={styles.kycRejectBtnText}>Rechazar</Text>
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.kycApproveBtn}
              onPress={() => handleDecision(true)}
              disabled={processing}
            >
              {processing ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={20} color="#fff" />
                  <Text style={styles.kycApproveBtnText}>Aprobar</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    );
  }

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Verificaciones KYC Pendientes</Text>
      
      {loading ? (
        <ActivityIndicator size="large" color="#F5A623" style={{ marginTop: 40 }} />
      ) : verifications.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="document-text-outline" size={48} color="#9ca3af" />
          <Text style={styles.emptyStateText}>No hay verificaciones pendientes</Text>
          <Text style={styles.emptyStateSubtext}>Las nuevas solicitudes aparecerán aquí</Text>
        </View>
      ) : (
        verifications.map((v) => (
          <TouchableOpacity
            key={v.user_id}
            style={styles.kycCard}
            onPress={() => setSelectedUser(v)}
          >
            <View style={styles.kycCardHeader}>
              <View style={styles.kycAvatar}>
                {v.selfie_image ? (
                  <Image source={{ uri: v.selfie_image }} style={styles.kycAvatarImage} />
                ) : (
                  <Text style={styles.kycAvatarText}>{v.name?.charAt(0)?.toUpperCase() || '?'}</Text>
                )}
              </View>
              <View style={styles.kycCardInfo}>
                <Text style={styles.kycCardName}>{v.full_name || v.name}</Text>
                <Text style={styles.kycCardEmail}>{v.email}</Text>
                <Text style={styles.kycCardDate}>
                  {formatDate(v.verification_submitted_at || v.created_at)}
                </Text>
              </View>
              <View style={styles.kycPendingBadge}>
                <Text style={styles.kycPendingText}>Pendiente</Text>
              </View>
            </View>
            <View style={styles.kycCardFooter}>
              <View style={styles.kycDocIndicator}>
                <Ionicons name={v.id_document_image ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={v.id_document_image ? '#059669' : '#9ca3af'} />
                <Text style={styles.kycDocIndicatorText}>DNI</Text>
              </View>
              <View style={styles.kycDocIndicator}>
                <Ionicons name={v.cpf_image ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={v.cpf_image ? '#059669' : '#9ca3af'} />
                <Text style={styles.kycDocIndicatorText}>CPF</Text>
              </View>
              <View style={styles.kycDocIndicator}>
                <Ionicons name={v.selfie_image ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={v.selfie_image ? '#059669' : '#9ca3af'} />
                <Text style={styles.kycDocIndicatorText}>Selfie</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
            </View>
          </TouchableOpacity>
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
  const [risToVes, setRisToVes] = useState('92');
  const [vesToRis, setVesToRis] = useState('102');
  const [risToBrl, setRisToBrl] = useState('1');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCurrentRates();
  }, []);

  const loadCurrentRates = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      setRisToVes(response.data.ris_to_ves?.toString() || '92');
      setVesToRis(response.data.ves_to_ris?.toString() || '102');
      setRisToBrl(response.data.ris_to_brl?.toString() || '1');
    } catch (error) {
      console.error('Error loading rates:', error);
    } finally {
      setLoading(false);
    }
  };

  const saveRates = async () => {
    const risVes = parseFloat(risToVes);
    const vesRis = parseFloat(vesToRis);
    const risBrl = parseFloat(risToBrl);

    if (isNaN(risVes) || risVes <= 0 || isNaN(vesRis) || vesRis <= 0) {
      showAlert('Error', 'Ingresa tasas válidas');
      return;
    }

    setSaving(true);
    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/rate`,
        { 
          ris_to_ves: risVes,
          ves_to_ris: vesRis,
          ris_to_brl: risBrl || 1
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      showAlert('Éxito', 'Tasas actualizadas correctamente');
      onRateUpdated();
    } catch (error: any) {
      showAlert('Error', error.response?.data?.detail || 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <ActivityIndicator size="large" color="#2563eb" style={{ marginTop: 40 }} />;
  }

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Configuración de Tasas</Text>
      
      {/* Tasa RIS → VES (Enviar a Venezuela) */}
      <View style={styles.settingCard}>
        <View style={styles.settingHeader}>
          <Ionicons name="arrow-forward" size={24} color="#2563eb" />
          <Text style={styles.settingTitle}>RIS → VES</Text>
        </View>
        <Text style={styles.settingDesc}>Para enviar a Venezuela (1 RIS = X VES)</Text>
        <View style={styles.rateInputRow}>
          <TextInput
            style={styles.rateInput}
            value={risToVes}
            onChangeText={setRisToVes}
            keyboardType="numeric"
            placeholder="92"
          />
          <Text style={styles.rateUnit}>VES</Text>
        </View>
      </View>

      {/* Tasa VES → RIS (Recarga con Bolívares) */}
      <View style={styles.settingCard}>
        <View style={styles.settingHeader}>
          <Ionicons name="arrow-back" size={24} color="#F5A623" />
          <Text style={styles.settingTitle}>VES → RIS</Text>
        </View>
        <Text style={styles.settingDesc}>Para recargas con Bolívares (X VES = 1 RIS)</Text>
        <View style={styles.rateInputRow}>
          <TextInput
            style={styles.rateInput}
            value={vesToRis}
            onChangeText={setVesToRis}
            keyboardType="numeric"
            placeholder="102"
          />
          <Text style={styles.rateUnit}>VES</Text>
        </View>
      </View>

      {/* Tasa RIS → BRL (PIX) */}
      <View style={styles.settingCard}>
        <View style={styles.settingHeader}>
          <Ionicons name="qr-code" size={24} color="#059669" />
          <Text style={styles.settingTitle}>RIS → BRL</Text>
        </View>
        <Text style={styles.settingDesc}>Para recargas PIX (1 RIS = X BRL)</Text>
        <View style={styles.rateInputRow}>
          <TextInput
            style={styles.rateInput}
            value={risToBrl}
            onChangeText={setRisToBrl}
            keyboardType="numeric"
            placeholder="1"
          />
          <Text style={styles.rateUnit}>BRL</Text>
        </View>
      </View>

      <TouchableOpacity style={styles.saveButton} onPress={saveRates} disabled={saving}>
        {saving ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <>
            <Ionicons name="save" size={18} color="#fff" />
            <Text style={styles.saveButtonText}>Guardar Todas las Tasas</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, color: '#6b7280', fontSize: 14 },
  
  // Header - Professional Dark Theme
  header: { 
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    alignItems: 'center', 
    paddingHorizontal: 16, 
    paddingVertical: 16,
    backgroundColor: '#0f172a',
  },
  headerLeft: { width: 44 },
  backButton: { 
    width: 40, 
    height: 40, 
    borderRadius: 12, 
    backgroundColor: 'rgba(255,255,255,0.1)', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#fff' },
  roleBadge: { 
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(59,130,246,0.3)', 
    paddingHorizontal: 10, 
    paddingVertical: 4, 
    borderRadius: 20,
    marginTop: 4,
    gap: 4,
  },
  superBadge: { backgroundColor: 'rgba(245,158,11,0.3)' },
  roleBadgeText: { fontSize: 11, fontWeight: '600', color: '#fff' },
  headerRight: { width: 44, alignItems: 'flex-end' },
  refreshButton: { 
    width: 40, 
    height: 40, 
    borderRadius: 12, 
    backgroundColor: 'rgba(255,255,255,0.1)', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },

  // Tabs Navigation
  tabsWrapper: {
    backgroundColor: '#0f172a',
    paddingBottom: 12,
  },
  tabsContainer: {
    paddingHorizontal: 12,
    gap: 8,
  },
  tabItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 25,
    backgroundColor: 'rgba(255,255,255,0.08)',
    gap: 6,
  },
  tabItemActive: {
    backgroundColor: '#2563eb',
  },
  tabLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: '#94a3b8',
  },
  tabLabelActive: {
    color: '#fff',
    fontWeight: '600',
  },
  tabBadge: {
    backgroundColor: '#ef4444',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
    minWidth: 20,
    alignItems: 'center',
  },
  tabBadgeActive: {
    backgroundColor: 'rgba(255,255,255,0.3)',
  },
  tabBadgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
  },
  tabBadgeTextActive: {
    color: '#fff',
  },

  // Content
  content: { flex: 1, backgroundColor: '#f8fafc' },
  contentContainer: { paddingBottom: 20 },
  tabContent: { padding: 16 },
  
  // Desktop Styles
  headerDesktop: {
    paddingHorizontal: 40,
    paddingVertical: 20,
  },
  headerTitleDesktop: {
    fontSize: 24,
  },
  tabsWrapperDesktop: {
    paddingHorizontal: 24,
  },
  tabsContainerDesktop: {
    paddingHorizontal: 24,
    gap: 12,
    justifyContent: 'center',
  },
  tabItemDesktop: {
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  tabLabelDesktop: {
    fontSize: 15,
  },
  contentDesktop: {
    paddingHorizontal: 24,
  },
  contentContainerDesktop: {
    paddingHorizontal: 24,
    paddingTop: 24,
    maxWidth: '100%',
  },

  // Section Headers
  sectionTitle: { fontSize: 20, fontWeight: '700', color: '#1f2937', marginBottom: 16 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  countBadge: { backgroundColor: '#2563eb', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  countText: { color: '#fff', fontSize: 12, fontWeight: '600' },

  // Welcome Card
  welcomeCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },

  // Quick Access to Rates
  ratesQuickAccess: {
    backgroundColor: '#2563eb',
    borderRadius: 16,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
    shadowColor: '#2563eb',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  ratesQuickAccessLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  ratesQuickAccessIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  ratesQuickAccessTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
  ratesQuickAccessSubtitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 2,
  },
  welcomeContent: {},
  welcomeTitle: { fontSize: 20, fontWeight: '700', color: '#0f172a' },
  welcomeSubtitle: { fontSize: 14, color: '#64748b', marginTop: 4 },
  welcomeIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Pending Section
  pendingSection: { marginBottom: 24 },
  pendingSectionTitle: { fontSize: 16, fontWeight: '600', color: '#374151', marginBottom: 12 },
  pendingGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  pendingCard: {
    flex: 1,
    minWidth: '47%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    borderLeftWidth: 4,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  pendingCardIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pendingCardContent: {},
  pendingCardValue: { fontSize: 24, fontWeight: '700', color: '#0f172a' },
  pendingCardLabel: { fontSize: 12, color: '#64748b' },

  // Stats Section
  statsSection: { marginBottom: 24 },
  statsSectionTitle: { fontSize: 16, fontWeight: '600', color: '#374151', marginBottom: 12 },
  statsRow: { flexDirection: 'row', gap: 10 },
  statBox: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  statBoxIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  statBoxValue: { fontSize: 22, fontWeight: '700', color: '#0f172a' },
  statBoxLabel: { fontSize: 11, color: '#64748b', marginTop: 4 },

  // Volume Section
  volumeSection: { marginBottom: 20 },
  volumeSectionTitle: { fontSize: 16, fontWeight: '600', color: '#374151', marginBottom: 12 },
  volumeCards: { flexDirection: 'row', gap: 10 },
  volumeCardNew: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  volumeCardValue: { fontSize: 18, fontWeight: '700', color: '#0f172a', marginTop: 8 },
  volumeCardLabel: { fontSize: 10, color: '#64748b', marginTop: 4, textAlign: 'center' },

  // Quick Stats (legacy)
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
  responseContainer: { padding: 12, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e5e7eb' },
  imagePreviewContainer: { position: 'relative', marginBottom: 10, alignSelf: 'flex-start' },
  imagePreview: { width: 100, height: 100, borderRadius: 10 },
  removeImageBtn: { position: 'absolute', top: -8, right: -8, backgroundColor: '#fff', borderRadius: 12 },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  attachImageBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#f3f4f6', justifyContent: 'center', alignItems: 'center' },
  responseInput: { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, maxHeight: 100, fontSize: 14 },
  sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },
  sendButtonDisabled: { backgroundColor: '#9ca3af' },

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
  emptyStateSubtext: { fontSize: 12, color: '#9ca3af', marginTop: 4 },

  // KYC Tab Styles
  kycCard: { backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 8, elevation: 2 },
  kycCardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  kycAvatar: { width: 50, height: 50, borderRadius: 25, backgroundColor: '#F5A623', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' },
  kycAvatarImage: { width: 50, height: 50, borderRadius: 25 },
  kycAvatarText: { fontSize: 20, fontWeight: '700', color: '#fff' },
  kycCardInfo: { flex: 1, marginLeft: 12 },
  kycCardName: { fontSize: 16, fontWeight: '700', color: '#0f172a' },
  kycCardEmail: { fontSize: 13, color: '#64748b' },
  kycCardDate: { fontSize: 11, color: '#9ca3af', marginTop: 2 },
  kycPendingBadge: { backgroundColor: '#fef3c7', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  kycPendingText: { fontSize: 11, fontWeight: '600', color: '#d97706' },
  kycCardFooter: { flexDirection: 'row', alignItems: 'center', paddingTop: 12, borderTopWidth: 1, borderTopColor: '#f1f5f9' },
  kycDocIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 16 },
  kycDocIndicatorText: { fontSize: 11, color: '#6b7280' },
  
  // KYC Review Modal Styles
  kycReviewHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 20, gap: 12 },
  kycBackBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#f1f5f9', justifyContent: 'center', alignItems: 'center' },
  kycReviewTitle: { fontSize: 18, fontWeight: '700', color: '#0f172a' },
  kycUserCard: { backgroundColor: '#f8fafc', borderRadius: 14, padding: 16, marginBottom: 20 },
  kycUserInfo: { },
  kycUserName: { fontSize: 18, fontWeight: '700', color: '#0f172a' },
  kycUserEmail: { fontSize: 14, color: '#64748b', marginTop: 2 },
  kycUserDate: { fontSize: 12, color: '#9ca3af', marginTop: 4 },
  kycDocSection: { backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 12 },
  kycDocLabel: { fontSize: 12, color: '#64748b', marginBottom: 4 },
  kycDocValue: { fontSize: 16, fontWeight: '600', color: '#0f172a' },
  kycSectionTitle: { fontSize: 15, fontWeight: '700', color: '#0f172a', marginTop: 16, marginBottom: 10 },
  kycDocImage: { width: '100%', height: 200, borderRadius: 12, backgroundColor: '#f1f5f9' },
  kycSelfieImage: { width: 200, height: 200, borderRadius: 100, alignSelf: 'center', backgroundColor: '#f1f5f9' },
  kycNoImage: { fontSize: 14, color: '#9ca3af', fontStyle: 'italic', textAlign: 'center', padding: 20 },
  kycRejectSection: { marginTop: 20, marginBottom: 20 },
  kycRejectLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  kycRejectInput: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 10, padding: 12, minHeight: 80, textAlignVertical: 'top' },
  kycActionButtons: { flexDirection: 'row', gap: 12, marginBottom: 40 },
  kycRejectBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', borderWidth: 2, borderColor: '#fecaca', paddingVertical: 14, borderRadius: 12, gap: 8 },
  kycRejectBtnText: { fontSize: 15, fontWeight: '600', color: '#dc2626' },
  kycApproveBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#059669', paddingVertical: 14, borderRadius: 12, gap: 8 },
  kycApproveBtnText: { fontSize: 15, fontWeight: '700', color: '#fff' },

  // User Detail View Styles
  sectionSubtitle: { fontSize: 13, color: '#6b7280', marginTop: -12, marginBottom: 16 },
  userAvatarImage: { width: 40, height: 40, borderRadius: 20 },
  userDetailHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 16, gap: 12 },
  userDetailBackBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#f1f5f9', justifyContent: 'center', alignItems: 'center' },
  userDetailTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#0f172a' },
  userDetailRefresh: { padding: 8 },
  
  // User Profile Card
  userProfileCard: { backgroundColor: '#fff', borderRadius: 16, padding: 20, marginBottom: 16, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 10, elevation: 2 },
  userProfileTop: { flexDirection: 'row', alignItems: 'center', marginBottom: 16 },
  userProfileAvatarContainer: { position: 'relative' },
  userProfileAvatar: { width: 70, height: 70, borderRadius: 35 },
  userProfileAvatarPlaceholder: { width: 70, height: 70, borderRadius: 35, backgroundColor: '#2563eb', justifyContent: 'center', alignItems: 'center' },
  userProfileAvatarText: { fontSize: 28, fontWeight: '700', color: '#fff' },
  userProfileOnline: { position: 'absolute', bottom: 2, right: 2, width: 16, height: 16, borderRadius: 8, backgroundColor: '#10b981', borderWidth: 3, borderColor: '#fff' },
  userProfileInfo: { flex: 1, marginLeft: 16 },
  userProfileName: { fontSize: 20, fontWeight: '700', color: '#0f172a' },
  userProfileEmail: { fontSize: 14, color: '#64748b', marginTop: 2 },
  userProfileBadges: { flexDirection: 'row', gap: 8, marginTop: 8 },
  profileBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  badgeGreen: { backgroundColor: '#ecfdf5' },
  badgeYellow: { backgroundColor: '#fef3c7' },
  badgeBlue: { backgroundColor: '#eff6ff' },
  profileBadgeText: { fontSize: 11, fontWeight: '600' },
  userProfileBalance: { backgroundColor: '#f0fdf4', borderRadius: 12, padding: 16, alignItems: 'center' },
  userProfileBalanceLabel: { fontSize: 12, color: '#6b7280' },
  userProfileBalanceValue: { fontSize: 32, fontWeight: '700', color: '#059669', marginTop: 4 },
  
  // Stats Grid
  userStatsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 },
  userStatBox: { width: (SCREEN_WIDTH - 52) / 2, borderRadius: 12, padding: 14, alignItems: 'center' },
  userStatBoxValue: { fontSize: 24, fontWeight: '700' },
  userStatBoxLabel: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  
  // Detail Tabs
  detailTabs: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 12, padding: 4, marginBottom: 16 },
  detailTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 4, borderRadius: 8 },
  detailTabActive: { backgroundColor: '#eff6ff' },
  detailTabText: { fontSize: 11, color: '#6b7280', fontWeight: '500' },
  detailTabTextActive: { color: '#2563eb', fontWeight: '600' },
  
  // Detail Section
  detailSection: { backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 16 },
  detailSectionTitle: { fontSize: 16, fontWeight: '700', color: '#0f172a', marginBottom: 16 },
  infoRow: { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  infoLabel: { width: 120, fontSize: 13, color: '#64748b' },
  infoValue: { flex: 1, fontSize: 13, color: '#0f172a', fontWeight: '500' },
  noDataText: { fontSize: 14, color: '#9ca3af', textAlign: 'center', paddingVertical: 24 },
  
  // History Card
  historyCard: { backgroundColor: '#f8fafc', borderRadius: 10, padding: 14, marginBottom: 10 },
  historyCardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  historyAmount: { fontSize: 18, fontWeight: '700', color: '#0f172a' },
  historySubtext: { fontSize: 13, color: '#059669', marginTop: 2 },
  historyStatus: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusCompleted: { backgroundColor: '#ecfdf5' },
  statusPending: { backgroundColor: '#fef3c7' },
  statusRejected: { backgroundColor: '#fef2f2' },
  historyStatusText: { fontSize: 11, fontWeight: '600', color: '#0f172a' },
  historyDate: { fontSize: 12, color: '#64748b' },
  historyMeta: { fontSize: 11, color: '#9ca3af', marginTop: 4 },
  beneficiaryPreview: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  beneficiaryPreviewText: { fontSize: 12, color: '#6b7280' },
  rejectionText: { fontSize: 12, color: '#dc2626', marginTop: 4 },
  
  // Beneficiary Card
  beneficiaryCard: { backgroundColor: '#f8fafc', borderRadius: 12, padding: 14, marginBottom: 12 },
  beneficiaryCardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  beneficiaryCardInfo: { flex: 1, marginLeft: 10 },
  beneficiaryCardName: { fontSize: 15, fontWeight: '600', color: '#0f172a' },
  beneficiaryCardBank: { fontSize: 12, color: '#64748b', marginTop: 2 },
  beneficiaryCardDetails: { backgroundColor: '#fff', borderRadius: 8, padding: 10, marginBottom: 8 },
  beneficiaryDetailRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  beneficiaryDetailText: { fontSize: 13, color: '#374151' },
  beneficiaryCardDate: { fontSize: 11, color: '#9ca3af' },
  
  // KYC Document in Detail
  kycDocTitle: { fontSize: 14, fontWeight: '600', color: '#0f172a', marginTop: 16, marginBottom: 8 },
  kycSelfieSmall: { width: 150, height: 150, borderRadius: 75, alignSelf: 'center', backgroundColor: '#f1f5f9' },

  // VES Recharge Styles
  subTabsContainer: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 12, padding: 4, marginBottom: 16, gap: 4 },
  subTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 8, gap: 6 },
  subTabActive: { backgroundColor: '#fffbeb' },
  subTabText: { fontSize: 13, color: '#6b7280', fontWeight: '500' },
  subTabTextActive: { color: '#F5A623', fontWeight: '600' },
  emptyStateSmall: { alignItems: 'center', paddingVertical: 32 },
  emptyTextSmall: { fontSize: 13, color: '#9ca3af', marginTop: 8 },
  
  // VES Recharge Card
  vesRechargeCard: { backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  vesRechargeHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  vesRechargeUser: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  vesRechargeAvatar: { width: 40, height: 40, borderRadius: 20 },
  vesRechargeAvatarPlaceholder: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#F5A623', justifyContent: 'center', alignItems: 'center' },
  vesRechargeAvatarText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  vesRechargeName: { fontSize: 15, fontWeight: '600', color: '#0f172a' },
  vesRechargeDate: { fontSize: 11, color: '#6b7280', marginTop: 2 },
  vesRechargeAmounts: { alignItems: 'flex-end' },
  vesRechargeVES: { fontSize: 17, fontWeight: '700', color: '#0f172a' },
  vesRechargeRIS: { fontSize: 14, fontWeight: '600', color: '#059669', marginTop: 2 },
  vesRechargeFooter: { flexDirection: 'row', alignItems: 'center', paddingTop: 12, borderTopWidth: 1, borderTopColor: '#f3f4f6', gap: 12 },
  vesRechargeMethod: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  vesRechargeMethodText: { fontSize: 12, color: '#6b7280' },
  vesRechargeRef: { flex: 1 },
  vesRechargeRefText: { fontSize: 12, color: '#2563eb', fontWeight: '500' },
  
  // VES Detail View
  vesDetailHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 20 },
  vesBackBtn: { width: 44, height: 44, borderRadius: 12, backgroundColor: '#f1f5f9', justifyContent: 'center', alignItems: 'center' },
  vesDetailTitle: { fontSize: 18, fontWeight: '700', color: '#0f172a' },
  vesUserCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 16 },
  vesUserAvatar: { width: 50, height: 50, borderRadius: 25 },
  vesUserAvatarPlaceholder: { width: 50, height: 50, borderRadius: 25, backgroundColor: '#F5A623', justifyContent: 'center', alignItems: 'center' },
  vesUserAvatarText: { color: '#fff', fontSize: 20, fontWeight: '700' },
  vesUserInfo: { flex: 1, marginLeft: 14 },
  vesUserName: { fontSize: 17, fontWeight: '700', color: '#0f172a' },
  vesUserEmail: { fontSize: 13, color: '#64748b', marginTop: 2 },
  vesDate: { fontSize: 11, color: '#9ca3af', marginTop: 4 },
  
  vesAmountCard: { backgroundColor: '#f0fdf4', borderRadius: 14, padding: 20, marginBottom: 16 },
  vesAmountRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around' },
  vesAmountItem: { alignItems: 'center' },
  vesAmountLabel: { fontSize: 12, color: '#6b7280', marginBottom: 4 },
  vesAmountValue: { fontSize: 24, fontWeight: '700', color: '#0f172a' },
  
  vesDetailsCard: { backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 16 },
  vesDetailsTitle: { fontSize: 15, fontWeight: '700', color: '#0f172a', marginBottom: 12 },
  vesDetailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  vesDetailLabel: { fontSize: 13, color: '#64748b' },
  vesDetailValue: { fontSize: 13, color: '#0f172a', fontWeight: '500' },
  
  // Voucher Section
  voucherSectionTitle: { fontSize: 15, fontWeight: '700', color: '#0f172a', marginTop: 8 },
  voucherTapHint: { fontSize: 12, color: '#6b7280', marginBottom: 10 },
  voucherContainer: { position: 'relative', borderRadius: 14, overflow: 'hidden', marginBottom: 20 },
  voucherPreviewImage: { width: '100%', height: 250, backgroundColor: '#f1f5f9' },
  voucherExpandIcon: { position: 'absolute', bottom: 12, right: 12, width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center' },
  
  // Fullscreen Voucher Modal
  voucherFullscreenOverlay: { flex: 1, backgroundColor: '#000', justifyContent: 'center', alignItems: 'center' },
  voucherFullscreenClose: { position: 'absolute', top: 50, right: 20, zIndex: 10 },
  voucherFullscreenImage: { width: SCREEN_WIDTH, height: '70%' },
  voucherFullscreenInfo: { position: 'absolute', bottom: 50, alignItems: 'center' },
  voucherFullscreenAmount: { fontSize: 28, fontWeight: '700', color: '#fff' },
  voucherFullscreenRef: { fontSize: 16, color: 'rgba(255,255,255,0.8)', marginTop: 8 },
  
  // VES Action Buttons
  vesRejectSection: { marginBottom: 16 },
  vesRejectLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  vesRejectInput: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 12, padding: 14, minHeight: 80, textAlignVertical: 'top', fontSize: 14 },
  vesActionButtons: { flexDirection: 'row', gap: 12, marginBottom: 40 },
  vesRejectBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', borderWidth: 2, borderColor: '#fecaca', paddingVertical: 16, borderRadius: 14, gap: 8 },
  vesRejectBtnText: { fontSize: 15, fontWeight: '600', color: '#dc2626' },
  vesApproveBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#059669', paddingVertical: 16, borderRadius: 14, gap: 8 },
  vesApproveBtnText: { fontSize: 15, fontWeight: '700', color: '#fff' },

  // Delete User Button
  deleteUserBtn: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'center', 
    backgroundColor: '#fef2f2', 
    borderWidth: 1, 
    borderColor: '#fecaca', 
    paddingVertical: 12, 
    borderRadius: 10, 
    marginTop: 12,
    gap: 8 
  },
  deleteUserBtnText: { fontSize: 14, fontWeight: '600', color: '#dc2626' },

  // Deleted Users Button
  deletedUsersBtn: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'center', 
    backgroundColor: '#fef2f2', 
    borderWidth: 1, 
    borderColor: '#fecaca', 
    paddingVertical: 12, 
    borderRadius: 10, 
    marginBottom: 16,
    gap: 8 
  },
  deletedUsersBtnText: { fontSize: 14, fontWeight: '500', color: '#dc2626' },

  // Deleted Users View
  deletedUsersHeader: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    marginBottom: 20 
  },
  deletedUsersTitle: { 
    flex: 1, 
    fontSize: 18, 
    fontWeight: '700', 
    color: '#0f172a', 
    textAlign: 'center' 
  },
  deletedUserCard: { 
    backgroundColor: '#fff', 
    borderRadius: 12, 
    padding: 14, 
    marginBottom: 10, 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between' 
  },
  deletedUserInfo: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    flex: 1 
  },
  deletedUserAvatar: { 
    width: 44, 
    height: 44, 
    borderRadius: 22, 
    backgroundColor: '#fee2e2', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  deletedUserAvatarText: { 
    color: '#dc2626', 
    fontSize: 16, 
    fontWeight: '600' 
  },
  deletedUserDetails: { 
    marginLeft: 12, 
    flex: 1 
  },
  deletedUserName: { 
    fontSize: 15, 
    fontWeight: '600', 
    color: '#374151' 
  },
  deletedUserEmail: { 
    fontSize: 12, 
    color: '#6b7280', 
    marginTop: 2 
  },
  deletedUserDate: { 
    fontSize: 11, 
    color: '#9ca3af', 
    marginTop: 4 
  },
  restoreUserBtn: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    backgroundColor: '#ecfdf5', 
    paddingHorizontal: 12, 
    paddingVertical: 8, 
    borderRadius: 8, 
    gap: 6 
  },
  restoreUserBtnText: { 
    fontSize: 13, 
    fontWeight: '600', 
    color: '#059669' 
  },
});
