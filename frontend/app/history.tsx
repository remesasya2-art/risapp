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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import { format } from 'date-fns';
import AsyncStorage from '@react-native-async-storage/async-storage';

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

  useEffect(() => {
    if (user) {
      loadTransactions();
    }
  }, [user, filter]);

  const loadTransactions = async () => {
    try {
      setLoading(true);
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
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="lock-closed" size={60} color="#6b7280" />
          <Text style={styles.emptyText}>Inicia sesión para ver tu historial</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const renderTransaction = ({ item }: { item: Transaction }) => {
    const isRecharge = item.type === 'recharge';
    const icon = isRecharge ? 'arrow-down-circle' : 'arrow-up-circle';
    const iconColor = isRecharge ? '#10b981' : '#f59e0b';
    const statusColor = item.status === 'completed' ? '#10b981' : 
                       item.status === 'pending' ? '#f59e0b' : '#ef4444';

    return (
      <View style={styles.transactionCard}>
        <View style={styles.transactionHeader}>
          <View style={styles.transactionIcon}>
            <Ionicons name={icon} size={24} color={iconColor} />
          </View>
          <View style={styles.transactionInfo}>
            <Text style={styles.transactionType}>
              {isRecharge ? 'Recarga' : 'Envío'}
            </Text>
            <Text style={styles.transactionDate}>
              {format(new Date(item.created_at), 'dd/MM/yyyy HH:mm')}
            </Text>
          </View>
          <View style={styles.transactionAmounts}>
            <Text style={[styles.transactionAmount, { color: iconColor }]}>
              {isRecharge ? '+' : '-'}{item.amount_input.toFixed(2)} {isRecharge ? 'REAIS' : 'RIS'}
            </Text>
            <Text style={styles.transactionOutput}>
              {item.amount_output.toFixed(2)} {isRecharge ? 'RIS' : 'VES'}
            </Text>
          </View>
        </View>
        
        <View style={styles.transactionFooter}>
          <View style={[styles.statusBadge, { backgroundColor: statusColor + '20' }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>
              {item.status === 'completed' ? 'Completado' : 
               item.status === 'pending' ? 'Pendiente' : 'Rechazado'}
            </Text>
          </View>
          {item.beneficiary_data && (
            <Text style={styles.beneficiaryText}>
              Para: {item.beneficiary_data.full_name}
            </Text>
          )}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.filterContainer}>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'all' && styles.filterButtonActive]}
          onPress={() => setFilter('all')}
        >
          <Text style={[styles.filterText, filter === 'all' && styles.filterTextActive]}>
            Todos
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'recharge' && styles.filterButtonActive]}
          onPress={() => setFilter('recharge')}
        >
          <Text style={[styles.filterText, filter === 'recharge' && styles.filterTextActive]}>
            Ingresos
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterButton, filter === 'withdrawal' && styles.filterButtonActive]}
          onPress={() => setFilter('withdrawal')}
        >
          <Text style={[styles.filterText, filter === 'withdrawal' && styles.filterTextActive]}>
            Egresos
          </Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#2563eb" />
        </View>
      ) : transactions.length === 0 ? (
        <View style={styles.centerContainer}>
          <Ionicons name="document-text-outline" size={60} color="#6b7280" />
          <Text style={styles.emptyText}>No hay transacciones</Text>
        </View>
      ) : (
        <FlatList
          data={transactions}
          renderItem={renderTransaction}
          keyExtractor={(item) => item.transaction_id}
          contentContainerStyle={styles.listContent}
        />
      )}
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
  emptyText: {
    fontSize: 16,
    color: '#6b7280',
    marginTop: 16,
    marginBottom: 24,
  },
  loginButton: {
    backgroundColor: '#2563eb',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  filterContainer: {
    flexDirection: 'row',
    padding: 16,
    gap: 8,
  },
  filterButton: {
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    alignItems: 'center',
  },
  filterButtonActive: {
    backgroundColor: '#2563eb',
    borderColor: '#2563eb',
  },
  filterText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#6b7280',
  },
  filterTextActive: {
    color: '#fff',
  },
  listContent: {
    padding: 16,
    gap: 12,
  },
  transactionCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  transactionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  transactionIcon: {
    marginRight: 12,
  },
  transactionInfo: {
    flex: 1,
  },
  transactionType: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  transactionDate: {
    fontSize: 12,
    color: '#6b7280',
  },
  transactionAmounts: {
    alignItems: 'flex-end',
  },
  transactionAmount: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  transactionOutput: {
    fontSize: 12,
    color: '#6b7280',
  },
  transactionFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
  beneficiaryText: {
    fontSize: 12,
    color: '#6b7280',
  },
});