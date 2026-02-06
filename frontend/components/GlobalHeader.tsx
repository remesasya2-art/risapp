import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface GlobalHeaderProps {
  title?: string;
  showBack?: boolean;
  showNotifications?: boolean;
  rightComponent?: React.ReactNode;
  transparent?: boolean;
}

export default function GlobalHeader({ 
  title, 
  showBack = false, 
  showNotifications = true,
  rightComponent,
  transparent = false
}: GlobalHeaderProps) {
  const router = useRouter();
  const { user } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (user && showNotifications) {
      loadUnreadCount();
      const interval = setInterval(loadUnreadCount, 30000);
      return () => clearInterval(interval);
    }
  }, [user, showNotifications]);

  const loadUnreadCount = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (!token) return;
      const response = await axios.get(`${BACKEND_URL}/api/notifications/unread-count`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUnreadCount(response.data.count || 0);
    } catch (error) {
      // Silently fail
    }
  };

  if (!user) return null;

  return (
    <View style={[styles.header, transparent && styles.headerTransparent]}>
      <View style={styles.leftSection}>
        {showBack && (
          <TouchableOpacity 
            style={styles.backButton} 
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={24} color={transparent ? "#fff" : "#0f172a"} />
          </TouchableOpacity>
        )}
        {title && (
          <Text style={[styles.title, transparent && styles.titleTransparent]}>
            {title}
          </Text>
        )}
      </View>

      <View style={styles.rightSection}>
        {rightComponent}
        {showNotifications && (
          <TouchableOpacity 
            style={styles.notificationBtn}
            onPress={() => router.push('/notifications')}
          >
            <Ionicons 
              name="notifications-outline" 
              size={24} 
              color={transparent ? "#fff" : "#0f172a"} 
            />
            {unreadCount > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>
                  {unreadCount > 9 ? '9+' : unreadCount}
                </Text>
              </View>
            )}
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    backgroundColor: '#f8fafc',
  },
  headerTransparent: {
    backgroundColor: 'transparent',
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
  },
  leftSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  rightSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  titleTransparent: {
    color: '#fff',
  },
  notificationBtn: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: 6,
    right: 6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },
});
