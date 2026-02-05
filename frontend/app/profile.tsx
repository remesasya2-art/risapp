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
          <View style={styles.emptyIconContainer}>
            <Ionicons name="person" size={48} color="#94a3b8" />
          </View>
          <Text style={styles.emptyTitle}>Acceso Restringido</Text>
          <Text style={styles.emptyText}>Inicia sesión para ver tu perfil</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Ionicons name="log-in" size={20} color="#fff" />
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Verification status config
  const verificationConfig = {
    verified: { color: '#059669', bg: '#ecfdf5', label: 'Verificado', icon: 'shield-checkmark' },
    pending: { color: '#d97706', bg: '#fef3c7', label: 'En Revisión', icon: 'time' },
    rejected: { color: '#dc2626', bg: '#fef2f2', label: 'Rechazado', icon: 'alert-circle' },
    none: { color: '#64748b', bg: '#f1f5f9', label: 'Sin Verificar', icon: 'shield-outline' },
  };

  const verStatus = verificationConfig[user.verification_status as keyof typeof verificationConfig] || verificationConfig.none;

  const MenuItem = ({ 
    icon, 
    label, 
    onPress, 
    color = '#0f172a', 
    badge, 
    badgeColor,
    showArrow = true,
    highlight = false 
  }: {
    icon: string;
    label: string;
    onPress: () => void;
    color?: string;
    badge?: string;
    badgeColor?: string;
    showArrow?: boolean;
    highlight?: boolean;
  }) => (
    <TouchableOpacity 
      style={[styles.menuItem, highlight && styles.menuItemHighlight]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={[styles.menuIconContainer, { backgroundColor: color + '15' }]}>
        <Ionicons name={icon as any} size={20} color={color} />
      </View>
      <Text style={styles.menuLabel}>{label}</Text>
      {badge && (
        <View style={[styles.menuBadge, { backgroundColor: badgeColor || '#0f172a' }]}>
          <Text style={styles.menuBadgeText}>{badge}</Text>
        </View>
      )}
      {showArrow && <Ionicons name="chevron-forward" size={18} color="#cbd5e1" />}
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView 
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Perfil</Text>
        </View>

        {/* Profile Card */}
        <View style={styles.profileCard}>
          <View style={styles.profileHeader}>
            <View style={styles.avatarWrapper}>
              {user.picture ? (
                <Image source={{ uri: user.picture }} style={styles.avatar} />
              ) : (
                <View style={styles.avatarPlaceholder}>
                  <Text style={styles.avatarText}>
                    {user.name?.charAt(0).toUpperCase() || 'U'}
                  </Text>
                </View>
              )}
              {user.verification_status === 'verified' && (
                <View style={styles.verifiedBadgeAvatar}>
                  <Ionicons name="checkmark-circle" size={20} color="#fff" />
                </View>
              )}
            </View>
            <View style={styles.profileInfo}>
              <Text style={styles.userName}>{user.name}</Text>
              <Text style={styles.userEmail}>{user.email}</Text>
              {user.picture && (
                <View style={styles.photoLockedBadge}>
                  <Ionicons name="lock-closed" size={10} color="#64748b" />
                  <Text style={styles.photoLockedText}>Foto verificada</Text>
                </View>
              )}
            </View>
          </View>
          
          {/* Verification Status */}
          <View style={styles.verificationContainer}>
            <View style={[styles.verificationBadge, { backgroundColor: verStatus.bg }]}>
              <Ionicons name={verStatus.icon as any} size={16} color={verStatus.color} />
              <Text style={[styles.verificationText, { color: verStatus.color }]}>
                {verStatus.label}
              </Text>
            </View>
            {user.verification_status !== 'verified' && user.verification_status !== 'pending' && (
              <TouchableOpacity 
                style={styles.verifyButton}
                onPress={() => router.push('/verification')}
              >
                <Text style={styles.verifyButtonText}>Verificar ahora</Text>
                <Ionicons name="arrow-forward" size={14} color="#F5A623" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Quick Stats */}
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{user.balance_ris?.toFixed(0) || '0'}</Text>
            <Text style={styles.statLabel}>RIS</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>
              {user.password_set ? '✓' : '✗'}
            </Text>
            <Text style={styles.statLabel}>Contraseña</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>
              {user.role === 'super_admin' ? 'Super' : user.role === 'admin' ? 'Admin' : 'User'}
            </Text>
            <Text style={styles.statLabel}>Rol</Text>
          </View>
        </View>

        {/* Admin Section */}
        {(user.role === 'admin' || user.role === 'super_admin') && (
          <View style={styles.menuSection}>
            <Text style={styles.sectionTitle}>Administración</Text>
            <View style={styles.menuCard}>
              <MenuItem
                icon="shield"
                label="Panel de Administración"
                color="#8b5cf6"
                badge={user.role === 'super_admin' ? 'Super' : 'Admin'}
                badgeColor="#8b5cf6"
                onPress={() => router.push('/admin-panel')}
              />
            </View>
          </View>
        )}

        {/* Security Section */}
        <View style={styles.menuSection}>
          <Text style={styles.sectionTitle}>Seguridad</Text>
          <View style={styles.menuCard}>
            {!user.password_set ? (
              <MenuItem
                icon="lock-closed"
                label="Configurar Contraseña"
                color="#dc2626"
                badge="Requerido"
                badgeColor="#dc2626"
                highlight={true}
                onPress={() => router.push('/set-password')}
              />
            ) : (
              <MenuItem
                icon="key"
                label="Cambiar Contraseña"
                color="#059669"
                onPress={() => router.push('/change-password')}
              />
            )}
            <MenuItem
              icon="finger-print"
              label="Verificación de Identidad"
              color="#F5A623"
              badge={verStatus.label}
              badgeColor={verStatus.color}
              onPress={() => router.push('/verification')}
            />
          </View>
        </View>

        {/* Personal Info Section - LOCKED if verified */}
        {user.verification_status === 'verified' && (
          <View style={styles.menuSection}>
            <View style={styles.lockedSectionHeader}>
              <Text style={styles.sectionTitle}>Información Personal</Text>
              <View style={styles.lockedBadge}>
                <Ionicons name="lock-closed" size={12} color="#059669" />
                <Text style={styles.lockedBadgeText}>Bloqueado</Text>
              </View>
            </View>
            <View style={styles.lockedInfoCard}>
              <View style={styles.lockedInfoNote}>
                <Ionicons name="information-circle" size={18} color="#64748b" />
                <Text style={styles.lockedInfoNoteText}>
                  Tu información personal está verificada y no puede ser modificada.
                </Text>
              </View>
              
              <View style={styles.lockedInfoRow}>
                <Ionicons name="person" size={18} color="#F5A623" />
                <View style={styles.lockedInfoContent}>
                  <Text style={styles.lockedInfoLabel}>Nombre</Text>
                  <Text style={styles.lockedInfoValue}>{user.name}</Text>
                </View>
              </View>
              
              <View style={styles.lockedInfoRow}>
                <Ionicons name="mail" size={18} color="#F5A623" />
                <View style={styles.lockedInfoContent}>
                  <Text style={styles.lockedInfoLabel}>Email</Text>
                  <Text style={styles.lockedInfoValue}>{user.email}</Text>
                </View>
              </View>
              
              <View style={[styles.lockedInfoRow, { borderBottomWidth: 0 }]}>
                <Ionicons name="shield-checkmark" size={18} color="#059669" />
                <View style={styles.lockedInfoContent}>
                  <Text style={styles.lockedInfoLabel}>Estado</Text>
                  <Text style={[styles.lockedInfoValue, { color: '#059669' }]}>Cuenta Verificada</Text>
                </View>
              </View>
            </View>
          </View>
        )}

        {/* Account Section */}
        <View style={styles.menuSection}>
          <Text style={styles.sectionTitle}>Cuenta</Text>
          <View style={styles.menuCard}>
            <MenuItem
              icon="people"
              label="Beneficiarios Guardados"
              color="#2563eb"
              onPress={() => router.push('/beneficiaries')}
            />
            <MenuItem
              icon="notifications"
              label="Notificaciones"
              color="#0ea5e9"
              onPress={() => router.push('/notifications')}
            />
            <MenuItem
              icon="document-text"
              label="Políticas y Términos"
              color="#64748b"
              onPress={() => router.push('/policies')}
            />
          </View>
        </View>

        {/* Support Section */}
        <View style={styles.menuSection}>
          <Text style={styles.sectionTitle}>Ayuda</Text>
          <View style={styles.menuCard}>
            <MenuItem
              icon="chatbubbles"
              label="Chat de Soporte"
              color="#10b981"
              onPress={() => router.push('/support')}
            />
            <MenuItem
              icon="help-circle"
              label="Preguntas Frecuentes"
              color="#6366f1"
              onPress={() => Alert.alert('FAQ', 'Próximamente')}
            />
          </View>
        </View>

        {/* Logout Button */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={20} color="#dc2626" />
          <Text style={styles.logoutButtonText}>Cerrar Sesión</Text>
        </TouchableOpacity>

        {/* App Version */}
        <Text style={styles.versionText}>RIS App v1.0.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
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
    marginBottom: 24,
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
  scrollContent: {
    paddingBottom: 40,
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
  profileCard: {
    backgroundColor: '#fff',
    marginHorizontal: 20,
    borderRadius: 20,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
    marginBottom: 16,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarWrapper: {
    position: 'relative',
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
  },
  avatarPlaceholder: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#F5A623',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
  },
  verifiedBadgeAvatar: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#059669',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#fff',
  },
  profileInfo: {
    flex: 1,
    marginLeft: 16,
  },
  userName: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0f172a',
  },
  userEmail: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 2,
  },
  photoLockedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 6,
  },
  photoLockedText: {
    fontSize: 11,
    color: '#64748b',
  },
  verificationContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
  },
  verificationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    gap: 6,
  },
  verificationText: {
    fontSize: 13,
    fontWeight: '600',
  },
  verifyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  verifyButtonText: {
    fontSize: 13,
    color: '#F5A623',
    fontWeight: '600',
  },
  statsRow: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    marginHorizontal: 20,
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  statLabel: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 4,
  },
  statDivider: {
    width: 1,
    backgroundColor: '#e2e8f0',
  },
  menuSection: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginLeft: 20,
    marginBottom: 12,
  },
  menuCard: {
    backgroundColor: '#fff',
    marginHorizontal: 20,
    borderRadius: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  menuItemHighlight: {
    backgroundColor: '#fef2f2',
  },
  menuIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  menuLabel: {
    flex: 1,
    fontSize: 15,
    color: '#0f172a',
    marginLeft: 14,
    fontWeight: '500',
  },
  menuBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    marginRight: 8,
  },
  menuBadgeText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#fff',
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 20,
    paddingVertical: 16,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#fecaca',
    backgroundColor: '#fff',
    gap: 10,
    marginTop: 8,
  },
  logoutButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#dc2626',
  },
  versionText: {
    fontSize: 12,
    color: '#94a3b8',
    textAlign: 'center',
    marginTop: 24,
  },
});
