import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { Platform, View, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import WebWrapper from '../components/WebWrapper';

// Pantallas de autenticación donde NO se muestra la barra de tabs
const AUTH_SCREENS = ['login', 'register', 'verify-email', 'forgot-password', 'set-password', 'change-password', 'policies'];

function TabsLayout() {
  const insets = useSafeAreaInsets();
  const { user, loading } = useAuth();

  // Mostrar loading mientras se verifica la sesión
  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f8fafc' }}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  // Si no hay usuario, ocultar las tabs (pantallas de auth)
  const hideTabBar = !user;
  
  return (
    <WebWrapper showBranding={!user}>
      <Tabs
        screenOptions={{
          tabBarActiveTintColor: '#F5A623',
          tabBarInactiveTintColor: '#9ca3af',
          tabBarStyle: hideTabBar ? { display: 'none' } : {
            backgroundColor: '#ffffff',
            borderTopWidth: 1,
            borderTopColor: '#e5e7eb',
            paddingBottom: Platform.OS === 'ios' ? insets.bottom + 10 : 25,
            paddingTop: 10,
            height: Platform.OS === 'ios' ? 100 + insets.bottom : 90,
          },
          tabBarLabelStyle: {
            fontSize: 12,
            fontWeight: '500',
            marginBottom: Platform.OS === 'android' ? 15 : 5,
          },
          headerStyle: {
            backgroundColor: '#2563eb',
          },
          headerTintColor: '#fff',
          headerTitleStyle: {
            fontWeight: 'bold',
          },
        }}
      >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Inicio',
          headerShown: false,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'Historial',
          headerShown: false,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="list" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Perfil',
          headerShown: false,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person" size={size} color={color} />
          ),
        }}
      />
      {/* Hidden screens */}
      <Tabs.Screen name="send" options={{ href: null }} />
      <Tabs.Screen name="recharge" options={{ href: null }} />
      <Tabs.Screen name="verification" options={{ href: null }} />
      <Tabs.Screen name="admin" options={{ href: null }} />
      <Tabs.Screen name="policies" options={{ href: null }} />
      <Tabs.Screen name="notifications" options={{ href: null }} />
      <Tabs.Screen name="beneficiaries" options={{ href: null }} />
      <Tabs.Screen name="support" options={{ href: null }} />
      <Tabs.Screen name="admin-panel" options={{ href: null }} />
      <Tabs.Screen name="set-password" options={{ href: null, headerShown: false }} />
      <Tabs.Screen name="change-password" options={{ href: null, headerShown: false }} />
      <Tabs.Screen name="forgot-password" options={{ href: null, headerShown: false }} />
      <Tabs.Screen name="register" options={{ href: null, headerShown: false }} />
      <Tabs.Screen name="login" options={{ href: null, headerShown: false }} />
      <Tabs.Screen name="verify-email" options={{ href: null, headerShown: false }} />
    </Tabs>
  );
}

export default function TabLayout() {
  return (
    <AuthProvider>
      <TabsLayout />
    </AuthProvider>
  );
}