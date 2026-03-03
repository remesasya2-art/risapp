/**
 * Push Notification Service
 * Handles web push notification subscription and management
 */
import api from './api';

// Convert base64 to Uint8Array (needed for VAPID key)
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Detect if running on iOS
function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

// Detect if running as PWA (installed)
function isPWA() {
  return window.matchMedia('(display-mode: standalone)').matches || 
         window.navigator.standalone === true;
}

class PushNotificationService {
  constructor() {
    this.registration = null;
    this.subscription = null;
    this.publicKey = null;
  }

  // Check if push notifications are supported
  isSupported() {
    // Basic check
    const hasServiceWorker = 'serviceWorker' in navigator;
    const hasPushManager = 'PushManager' in window;
    const hasNotification = 'Notification' in window;
    
    // iOS Safari doesn't support web push unless it's a PWA on iOS 16.4+
    if (isIOS() && !isPWA()) {
      console.log('iOS detected - Push requires PWA installation');
      return false;
    }
    
    return hasServiceWorker && hasPushManager && hasNotification;
  }

  // Get detailed support info
  getSupportInfo() {
    return {
      serviceWorker: 'serviceWorker' in navigator,
      pushManager: 'PushManager' in window,
      notification: 'Notification' in window,
      isIOS: isIOS(),
      isPWA: isPWA(),
      permission: 'Notification' in window ? Notification.permission : 'unsupported'
    };
  }

  // Check current permission status
  getPermissionStatus() {
    if (!this.isSupported()) return 'unsupported';
    return Notification.permission;
  }

  // Initialize service worker
  async init() {
    if (!this.isSupported()) {
      console.log('Push notifications not supported on this device');
      return false;
    }

    try {
      // Register service worker with update check
      this.registration = await navigator.serviceWorker.register('/sw.js', {
        updateViaCache: 'none'
      });
      console.log('Service Worker registered:', this.registration);

      // Check for updates
      this.registration.update();

      // Wait for it to be ready
      await navigator.serviceWorker.ready;

      // Get VAPID public key from server
      const response = await api.get('/push/web/vapid-public-key');
      this.publicKey = response.data.publicKey;

      // Check existing subscription
      this.subscription = await this.registration.pushManager.getSubscription();
      
      return true;
    } catch (error) {
      console.error('Failed to initialize push service:', error);
      return false;
    }
  }

  // Request notification permission
  async requestPermission() {
    if (!this.isSupported()) return 'unsupported';
    
    try {
      const permission = await Notification.requestPermission();
      return permission;
    } catch (error) {
      console.error('Permission request failed:', error);
      return 'denied';
    }
  }

  // Subscribe to push notifications
  async subscribe() {
    if (!this.registration || !this.publicKey) {
      const initialized = await this.init();
      if (!initialized) {
        throw new Error('No se pudo inicializar el servicio de notificaciones');
      }
    }

    if (!this.publicKey) {
      throw new Error('No se pudo obtener la clave del servidor');
    }

    try {
      // Request permission if not granted
      const permission = await this.requestPermission();
      if (permission !== 'granted') {
        throw new Error('Permiso de notificaciones denegado. Por favor, habilita las notificaciones en la configuración de tu navegador.');
      }

      // Subscribe to push manager
      this.subscription = await this.registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(this.publicKey)
      });

      // Send subscription to server
      const subscriptionData = this.subscription.toJSON();
      await api.post('/push/web/subscribe', {
        endpoint: subscriptionData.endpoint,
        keys: subscriptionData.keys
      });

      console.log('Push subscription successful');
      return true;
    } catch (error) {
      console.error('Push subscription failed:', error);
      throw error;
    }
  }

  // Unsubscribe from push notifications
  async unsubscribe() {
    try {
      if (this.subscription) {
        await this.subscription.unsubscribe();
        this.subscription = null;
      }

      await api.post('/push/web/unsubscribe');
      console.log('Push unsubscription successful');
      return true;
    } catch (error) {
      console.error('Push unsubscription failed:', error);
      throw error;
    }
  }

  // Check if currently subscribed
  async isSubscribed() {
    if (!this.registration) {
      await this.init();
    }
    
    this.subscription = await this.registration?.pushManager?.getSubscription();
    return !!this.subscription;
  }

  // Get subscription status from server
  async getStatus() {
    try {
      const response = await api.get('/push/web/status');
      return response.data;
    } catch (error) {
      console.error('Failed to get push status:', error);
      return { enabled: false, subscribed: false };
    }
  }

  // Send test notification
  async sendTestNotification() {
    try {
      const response = await api.post('/push/web/test');
      return response.data;
    } catch (error) {
      console.error('Failed to send test notification:', error);
      throw error;
    }
  }
}

// Singleton instance
const pushService = new PushNotificationService();
export default pushService;
