import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Image,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

export default function ProfileScreen() {
  const { user, login, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    if (Platform.OS === 'web') {
      if (confirm('¿Estás seguro que deseas cerrar sesión?')) {
        logout();
      }
    } else {
      Alert.alert(
        'Cerrar sesión',
        '¿Estás seguro que deseas cerrar sesión?',
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Cerrar sesión', style: 'destructive', onPress: logout },
        ]
      );
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContainer}>
          <Ionicons name="person-circle-outline" size={80} color="#6b7280" />
          <Text style={styles.emptyText}>Inicia sesión para ver tu perfil</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Profile Header */}
        <View style={styles.profileHeader}>
          {user.picture ? (
            <Image source={{ uri: user.picture }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarPlaceholder}>
              <Ionicons name="person" size={40} color="#fff" />
            </View>
          )}
          <Text style={styles.userName}>{user.name}</Text>
          <Text style={styles.userEmail}>{user.email}</Text>
        </View>

        {/* Menu Items */}
        <View style={styles.menuContainer}>
          {/* Only show verification option if not yet submitted */}
          {user.verification_status !== 'pending' && user.verification_status !== 'verified' && (
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => router.push('/verification')}
            >
              <Ionicons name="shield-checkmark" size={24} color="#f59e0b" />
              <Text style={styles.menuText}>Completar Verificación</Text>
              <Ionicons name="chevron-forward" size={20} color="#6b7280" />
            </TouchableOpacity>
          )}

          {user.email.includes('admin') && (
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => router.push('/admin')}
            >
              <Ionicons name="shield-checkmark" size={24} color="#2563eb" />
              <Text style={styles.menuText}>Panel de Administración</Text>
              <Ionicons name="chevron-forward" size={20} color="#6b7280" />
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => router.push('/beneficiaries')}
          >
            <Ionicons name="people" size={24} color="#2563eb" />
            <Text style={styles.menuText}>Beneficiarios guardados</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => Alert.alert('Info', 'Funcionalidad próximamente')}
          >
            <Ionicons name="settings" size={24} color="#2563eb" />
            <Text style={styles.menuText}>Configuración</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => Alert.alert('Info', 'Funcionalidad próximamente')}
          >
            <Ionicons name="help-circle" size={24} color="#2563eb" />
            <Text style={styles.menuText}>Ayuda y soporte</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>
        </View>

        {/* Logout Button */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out" size={20} color="#ef4444" />
          <Text style={styles.logoutButtonText}>Cerrar sesión</Text>
        </TouchableOpacity>
      </ScrollView>
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
  scrollContent: {
    padding: 16,
  },
  profileHeader: {
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    marginBottom: 16,
  },
  avatarPlaceholder: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  userName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 4,
  },
  userEmail: {
    fontSize: 14,
    color: '#6b7280',
  },
  menuContainer: {
    backgroundColor: '#fff',
    borderRadius: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  menuText: {
    flex: 1,
    fontSize: 16,
    color: '#1f2937',
    marginLeft: 12,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ef4444',
    gap: 8,
  },
  logoutButtonText: {
    color: '#ef4444',
    fontSize: 16,
    fontWeight: '600',
  },
});