import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
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

  // Push notifications only work on physical devices
  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    return null;
  }

  // Check if we're on a supported platform
  if (Platform.OS === 'android') {
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
  }

  // Request permission
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission not granted');
    return null;
  }

  try {
    // Get the Expo push token (works with Expo Go)
    const expoPushToken = await Notifications.getExpoPushTokenAsync({
      projectId: Constants.expoConfig?.extra?.eas?.projectId,
    });
    token = expoPushToken.data;
    console.log('Expo Push Token:', token);
  } catch (error) {
    console.log('Error getting Expo push token:', error);
    
    // Try to get FCM token for production builds
    try {
      const fcmToken = await Notifications.getDevicePushTokenAsync();
      token = fcmToken.data;
      console.log('Device Push Token:', token);
    } catch (fcmError) {
      console.log('Error getting device push token:', fcmError);
    }
  }

  return token;
}

export async function sendPushTokenToServer(token: string): Promise<boolean> {
  try {
    const sessionToken = await AsyncStorage.getItem('session_token');
    if (!sessionToken) {
      console.log('No session token, cannot register FCM token');
      return false;
    }

    await axios.post(
      `${BACKEND_URL}/api/auth/register-fcm-token`,
      { fcm_token: token },
      { headers: { Authorization: `Bearer ${sessionToken}` } }
    );

    console.log('FCM token registered with server');
    return true;
  } catch (error) {
    console.error('Error sending push token to server:', error);
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
