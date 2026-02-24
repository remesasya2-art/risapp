import React, { useEffect, useState } from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { RateProvider } from '../contexts/RateContext';
import { Platform, View, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import WebWrapper from '../components/WebWrapper';
import * as Font from 'expo-font';

// Pantallas de autenticación donde NO se muestra la barra de tabs
const AUTH_SCREENS = ['login', 'register', 'verify-email', 'forgot-password', 'set-password', 'change-password', 'policies'];

function TabsLayout() {
  const insets = useSafeAreaInsets();
  const { user, loading } = useAuth();
  const [fontsLoaded, setFontsLoaded] = useState(false);

  useEffect(() => {
    async function loadFonts() {
      try {
        await Font.loadAsync(Ionicons.font);
        setFontsLoaded(true);
      } catch (e) {
        console.error('Error loading fonts:', e);
        setFontsLoaded(true); // Continue anyway
      }
    }
    loadFonts();
  }, []);

  // Mostrar loading mientras se verifica la sesión o cargan fuentes
  if (loading || !fontsLoaded) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f8fafc' }}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  // Ocultar tabs siempre - navegación por botones
  const hideTabBar = true;
  
  return (
    <WebWrapper showBranding={!user}>
      <Tabs
        screenOptions={{
          tabBarActiveTintColor: '#F5A623',
          tabBarInactiveTintColor: '#9ca3af',
          tabBarStyle: { display: 'none' },
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
      <Tabs.Screen name="recharge-ves" options={{ href: null }} />
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
    </WebWrapper>
  );
}

export default function TabLayout() {
  return (
    <AuthProvider>
      <RateProvider>
        <TabsLayout />
      </RateProvider>
    </AuthProvider>
  );
}