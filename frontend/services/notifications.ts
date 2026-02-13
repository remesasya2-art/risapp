import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform, Alert } from 'react-native';
import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// Configure notification behavior
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export async function registerForPushNotificationsAsync(): Promise<string | null> {
  let token: string | null = null;

  console.log('🔔 Iniciando registro de notificaciones push...');
  console.log('📱 Platform:', Platform.OS);
  console.log('📱 isDevice:', Device.isDevice);

  // En web, las push notifications no funcionan de la misma manera
  if (Platform.OS === 'web') {
    console.log('⚠️ Push notifications no están disponibles en web');
    return null;
  }

  // Push notifications only work on physical devices
  if (!Device.isDevice) {
    console.log('⚠️ Push notifications requieren un dispositivo físico');
    return null;
  }

  // Check if we're on a supported platform
  if (Platform.OS === 'android') {
    console.log('📱 Configurando canales de notificación para Android...');
    // Set notification channel for Android
    await Notifications.setNotificationChannelAsync('withdrawals', {
      name: 'Retiros',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#4CAF50',
    });

    await Notifications.setNotificationChannelAsync('default', {
      name: 'Default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#2563eb',
    });
    console.log('✅ Canales de notificación configurados');
  }

  // Request permission
  console.log('📱 Verificando permisos de notificación...');
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;
  console.log('📱 Estado actual de permisos:', existingStatus);

  if (existingStatus !== 'granted') {
    console.log('📱 Solicitando permisos de notificación...');
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
    console.log('📱 Nuevo estado de permisos:', status);
  }

  if (finalStatus !== 'granted') {
    console.log('❌ Permiso de notificaciones denegado');
    return null;
  }

  console.log('✅ Permisos de notificación concedidos');

  try {
    // Get the Expo push token (works with Expo Go)
    console.log('📱 Obteniendo Expo Push Token...');
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    console.log('📱 Project ID:', projectId);
    
    // Si no hay projectId, intentar obtener el token sin él
    let expoPushToken;
    if (projectId) {
      expoPushToken = await Notifications.getExpoPushTokenAsync({
        projectId: projectId,
      });
    } else {
      // Intentar sin projectId (puede funcionar en algunos casos con Expo Go)
      console.log('⚠️ No hay projectId configurado, intentando sin él...');
      expoPushToken = await Notifications.getExpoPushTokenAsync();
    }
    
    token = expoPushToken.data;
    console.log('✅ Expo Push Token obtenido:', token);
  } catch (error: any) {
    console.log('⚠️ Error obteniendo Expo push token:', error?.message || error);
    
    // Try to get device token for standalone/production builds
    try {
      console.log('📱 Intentando obtener token nativo del dispositivo...');
      const deviceToken = await Notifications.getDevicePushTokenAsync();
      token = deviceToken.data;
      console.log('✅ Device Push Token obtenido:', token);
    } catch (deviceError: any) {
      console.log('❌ Error obteniendo device push token:', deviceError?.message || deviceError);
      
      // Última alternativa: crear un token de experiencia Expo
      try {
        console.log('📱 Último intento: Token de experiencia...');
        const experienceToken = await Notifications.getExpoPushTokenAsync({
          experienceId: '@remesasya/ris-app'
        });
        token = experienceToken.data;
        console.log('✅ Experience Token obtenido:', token);
      } catch (expError: any) {
        console.log('❌ No se pudo obtener ningún token:', expError?.message || expError);
      }
    }
  }

  if (token) {
    // Guardar el token localmente para debug
    await AsyncStorage.setItem('push_token', token);
    console.log('✅ Token guardado localmente');
  }

  return token;
}

export async function sendPushTokenToServer(token: string): Promise<boolean> {
  try {
    console.log('📤 Enviando token al servidor...');
    const sessionToken = await AsyncStorage.getItem('session_token');
    if (!sessionToken) {
      console.log('❌ No hay session token, no se puede registrar FCM token');
      return false;
    }

    console.log('📤 Session token encontrado, enviando FCM token...');
    console.log('📤 Backend URL:', BACKEND_URL);
    
    const response = await axios.post(
      `${BACKEND_URL}/api/auth/register-fcm-token`,
      { fcm_token: token },
      { headers: { Authorization: `Bearer ${sessionToken}` } }
    );

    console.log('✅ FCM token registrado con el servidor:', response.data);
    return true;
  } catch (error: any) {
    console.error('❌ Error enviando push token al servidor:', error?.response?.data || error.message);
    return false;
  }
}

export function addNotificationReceivedListener(
  callback: (notification: Notifications.Notification) => void
) {
  return Notifications.addNotificationReceivedListener(callback);
}

export function addNotificationResponseReceivedListener(
  callback: (response: Notifications.NotificationResponse) => void
) {
  return Notifications.addNotificationResponseReceivedListener(callback);
}

export async function scheduleLocalNotification(
  title: string,
  body: string,
  data?: Record<string, unknown>
) {
  await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      data,
      sound: true,
    },
    trigger: null, // Immediately
  });
}
