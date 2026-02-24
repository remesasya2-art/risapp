import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Platform,
  KeyboardAvoidingView,
  Alert,
  RefreshControl,
  Image,
  Modal,
  Animated,
  Vibration,
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

interface Message {
  id: string;
  text: string;
  image?: string;
  sender: 'user' | 'admin' | 'system';
  timestamp: Date;
  status?: 'sending' | 'sent' | 'error' | 'read';
  retryCount?: number;
}

interface QuickReply {
  id: string;
  text: string;
  icon: string;
}

const QUICK_REPLIES: QuickReply[] = [
  { id: '1', text: 'Tengo un problema con mi recarga', icon: 'card-outline' },
  { id: '2', text: 'No recibí mis RIS', icon: 'alert-circle-outline' },
  { id: '3', text: 'Necesito verificar mi cuenta', icon: 'shield-checkmark-outline' },
  { id: '4', text: 'Pregunta sobre tasas de cambio', icon: 'trending-up-outline' },
];

const showAlert = (title: string, message: string, buttons?: any[]) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
    if (buttons && buttons[0]?.onPress) buttons[0].onPress();
  } else {
    Alert.alert(title, message, buttons);
  }
};

export default function SupportScreen() {
  const router = useRouter();
  const { user, login } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'reconnecting' | 'offline'>('connected');
  const [showQuickReplies, setShowQuickReplies] = useState(true);
  const [retryQueue, setRetryQueue] = useState<string[]>([]);
  
  const scrollViewRef = useRef<ScrollView>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const lastMessageCount = useRef(0);

  // Animate entrance
  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, []);

  // Load conversation when screen is focused
  useFocusEffect(
    useCallback(() => {
      if (user) {
        loadConversation();
        // Start polling for new messages every 4 seconds
        pollIntervalRef.current = setInterval(() => {
          loadConversation(true);
        }, 4000);
      }
      
      return () => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }
        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }
      };
    }, [user])
  );

  // Process retry queue
  useEffect(() => {
    if (retryQueue.length > 0 && connectionStatus === 'connected') {
      const messageId = retryQueue[0];
      const messageToRetry = messages.find(m => m.id === messageId && m.status === 'error');
      
      if (messageToRetry) {
        retryMessage(messageToRetry);
      }
    }
  }, [retryQueue, connectionStatus]);

  const loadConversation = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/support/conversation`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 10000,
      });
      
      setConnectionStatus('connected');
      
      const welcomeMessage: Message = {
        id: 'welcome',
        text: '¡Hola! Bienvenido al soporte de RIS.\n\nNuestro equipo está listo para ayudarte. Puedes escribir tu consulta o usar las opciones rápidas.',
        sender: 'system',
        timestamp: new Date(0),
      };
      
      // Convert API response to Message format
      const conversationMessages: Message[] = response.data.map((msg: any) => ({
        id: msg.id,
        text: msg.text,
        image: msg.image,
        sender: msg.sender === 'admin' ? 'admin' : 'user',
        timestamp: new Date(msg.timestamp),
        status: 'sent',
      }));
      
      // Preserve local messages that are still sending
      const localSendingMessages = messages.filter(m => m.status === 'sending' || m.status === 'error');
      
      const allMessages = [welcomeMessage, ...conversationMessages, ...localSendingMessages];
      
      // Check for new messages and notify
      if (silent && conversationMessages.length > lastMessageCount.current) {
        const newAdminMessages = conversationMessages.filter(
          m => m.sender === 'admin' && 
          !messages.find(existing => existing.id === m.id)
        );
        
        if (newAdminMessages.length > 0) {
          // Vibrate on new message (mobile only)
          if (Platform.OS !== 'web') {
            Vibration.vibrate(100);
          }
        }
      }
      
      lastMessageCount.current = conversationMessages.length;
      setMessages(allMessages);
      setShowQuickReplies(conversationMessages.length === 0);
      
      if (!silent) {
        setLoading(false);
        setTimeout(() => {
          scrollViewRef.current?.scrollToEnd({ animated: false });
        }, 100);
      }
      
    } catch (error: any) {
      console.error('Error loading conversation:', error);
      
      if (error.code === 'ECONNABORTED' || !error.response) {
        setConnectionStatus('reconnecting');
      }
      
      if (!silent) {
        setLoading(false);
        setMessages([{
          id: 'welcome',
          text: '¡Hola! Bienvenido al soporte de RIS.\n\nNuestro equipo está listo para ayudarte.',
          sender: 'system',
          timestamp: new Date(),
        }]);
      }
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadConversation();
    setRefreshing(false);
  };

  const pickImage = async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        showAlert('Permiso requerido', 'Necesitamos acceso a tu galería para adjuntar imágenes.');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        quality: 0.7,
        base64: true,
      });

      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        const base64Image = `data:image/jpeg;base64,${asset.base64}`;
        setSelectedImage(base64Image);
      }
    } catch (error) {
      console.error('Error picking image:', error);
      showAlert('Error', 'No se pudo seleccionar la imagen');
    }
  };

  const takePhoto = async () => {
    try {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        showAlert('Permiso requerido', 'Necesitamos acceso a tu cámara para tomar fotos.');
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: true,
        quality: 0.7,
        base64: true,
      });

      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        const base64Image = `data:image/jpeg;base64,${asset.base64}`;
        setSelectedImage(base64Image);
      }
    } catch (error) {
      console.error('Error taking photo:', error);
      showAlert('Error', 'No se pudo tomar la foto');
    }
  };

  const removeSelectedImage = () => {
    setSelectedImage(null);
  };

  const selectQuickReply = (reply: QuickReply) => {
    setInputText(reply.text);
    setShowQuickReplies(false);
  };

  const retryMessage = async (message: Message) => {
    // Remove from retry queue
    setRetryQueue(prev => prev.filter(id => id !== message.id));
    
    // Update status to sending
    setMessages(prev =>
      prev.map(m =>
        m.id === message.id ? { ...m, status: 'sending', retryCount: (m.retryCount || 0) + 1 } : m
      )
    );

    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/support/send`,
        { 
          message: message.text,
          image: message.image 
        },
        { 
          headers: { Authorization: `Bearer ${token}` },
          timeout: 15000,
        }
      );

      setMessages(prev =>
        prev.map(m =>
          m.id === message.id ? { ...m, status: 'sent' } : m
        )
      );
      
      setConnectionStatus('connected');
      
    } catch (error) {
      console.error('Retry failed:', error);
      
      const retryCount = (message.retryCount || 0) + 1;
      
      if (retryCount < 3) {
        // Schedule another retry
        setMessages(prev =>
          prev.map(m =>
            m.id === message.id ? { ...m, status: 'error', retryCount } : m
          )
        );
        
        retryTimeoutRef.current = setTimeout(() => {
          setRetryQueue(prev => [...prev, message.id]);
        }, 5000 * retryCount);
      } else {
        // Give up after 3 retries
        setMessages(prev =>
          prev.map(m =>
            m.id === message.id ? { ...m, status: 'error', retryCount } : m
          )
        );
      }
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim() && !selectedImage) return;
    
    if (!user) {
      showAlert('Inicia sesión', 'Debes iniciar sesión para enviar mensajes de soporte.');
      return;
    }

    const messageText = inputText.trim();
    const imageToSend = selectedImage;
    
    setInputText('');
    setSelectedImage(null);
    setShowQuickReplies(false);

    const newMessage: Message = {
      id: `local_${Date.now()}`,
      text: messageText || '',
      image: imageToSend || undefined,
      sender: 'user',
      timestamp: new Date(),
      status: 'sending',
      retryCount: 0,
    };

    setMessages(prev => [...prev, newMessage]);
    setSending(true);

    // Scroll to bottom
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);

    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/support/send`,
        { 
          message: messageText,
          image: imageToSend 
        },
        { 
          headers: { Authorization: `Bearer ${token}` },
          timeout: 15000,
        }
      );

      // Update message status to sent
      setMessages(prev =>
        prev.map(m =>
          m.id === newMessage.id ? { ...m, status: 'sent' } : m
        )
      );
      
      setConnectionStatus('connected');

    } catch (error: any) {
      console.error('Error sending message:', error);
      
      // Check if it's a network error
      if (error.code === 'ECONNABORTED' || !error.response) {
        setConnectionStatus('reconnecting');
      }
      
      // Update message status to error
      setMessages(prev =>
        prev.map(m =>
          m.id === newMessage.id ? { ...m, status: 'error' } : m
        )
      );

      // Add to retry queue
      retryTimeoutRef.current = setTimeout(() => {
        setRetryQueue(prev => [...prev, newMessage.id]);
      }, 3000);

    } finally {
      setSending(false);
    }
  };

  const formatTime = (date: Date) => {
    if (date.getTime() === 0) return '';
    return date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (date: Date) => {
    if (date.getTime() === 0) return '';
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (date.toDateString() === today.toDateString()) {
      return 'Hoy';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Ayer';
    } else {
      return date.toLocaleDateString('es', { day: '2-digit', month: 'short' });
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'sending':
        return <ActivityIndicator size={12} color="rgba(255,255,255,0.7)" />;
      case 'sent':
        return <Ionicons name="checkmark" size={14} color="rgba(255,255,255,0.8)" />;
      case 'read':
        return <Ionicons name="checkmark-done" size={14} color="#60a5fa" />;
      case 'error':
        return <Ionicons name="alert-circle" size={14} color="#fca5a5" />;
      default:
        return null;
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Ayuda y Soporte</Text>
          <View style={{ width: 44 }} />
        </View>
        <View style={styles.centerContainer}>
          <View style={styles.emptyIconContainer}>
            <Ionicons name="chatbubbles" size={48} color="#F5A623" />
          </View>
          <Text style={styles.emptyTitle}>Centro de Ayuda</Text>
          <Text style={styles.emptyText}>Inicia sesión para contactar con nuestro equipo de soporte</Text>
          <TouchableOpacity style={styles.loginButton} onPress={login}>
            <Text style={styles.loginButtonText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={styles.headerTitle}>Soporte RIS</Text>
            <View style={styles.statusContainer}>
              <View style={[
                styles.statusDot,
                connectionStatus === 'connected' && styles.statusDotOnline,
                connectionStatus === 'reconnecting' && styles.statusDotReconnecting,
                connectionStatus === 'offline' && styles.statusDotOffline,
              ]} />
              <Text style={[
                styles.statusText,
                connectionStatus === 'connected' && styles.statusTextOnline,
                connectionStatus === 'reconnecting' && styles.statusTextReconnecting,
              ]}>
                {connectionStatus === 'connected' && 'En línea'}
                {connectionStatus === 'reconnecting' && 'Reconectando...'}
                {connectionStatus === 'offline' && 'Sin conexión'}
              </Text>
            </View>
          </View>
          <TouchableOpacity onPress={onRefresh} style={styles.headerButton}>
            <Ionicons name="refresh" size={22} color="#F5A623" />
          </TouchableOpacity>
        </View>

        {/* Connection Warning */}
        {connectionStatus !== 'connected' && (
          <Animated.View style={[styles.connectionWarning, { opacity: fadeAnim }]}>
            <Ionicons name="cloud-offline-outline" size={16} color="#92400e" />
            <Text style={styles.connectionWarningText}>
              {connectionStatus === 'reconnecting' 
                ? 'Reconectando... Los mensajes se enviarán cuando vuelva la conexión'
                : 'Sin conexión a internet'}
            </Text>
          </Animated.View>
        )}

        {/* Messages */}
        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color="#F5A623" />
            <Text style={styles.loadingText}>Cargando conversación...</Text>
          </View>
        ) : (
          <ScrollView
            ref={scrollViewRef}
            style={styles.messagesContainer}
            contentContainerStyle={styles.messagesContent}
            onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: false })}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={['#F5A623']} />
            }
            keyboardShouldPersistTaps="handled"
          >
            {messages.map((message, index) => {
              const showDate = index === 0 || 
                (index > 0 && formatDate(message.timestamp) !== formatDate(messages[index - 1].timestamp) && message.timestamp.getTime() !== 0);
              
              return (
                <View key={message.id}>
                  {showDate && message.timestamp.getTime() !== 0 && (
                    <View style={styles.dateSeparator}>
                      <Text style={styles.dateSeparatorText}>{formatDate(message.timestamp)}</Text>
                    </View>
                  )}
                  
                  <TouchableOpacity
                    activeOpacity={message.status === 'error' ? 0.7 : 1}
                    onPress={() => {
                      if (message.status === 'error') {
                        showAlert(
                          'Mensaje no enviado',
                          '¿Deseas reintentar enviar este mensaje?',
                          [
                            { text: 'Cancelar', style: 'cancel' },
                            { text: 'Reintentar', onPress: () => retryMessage(message) }
                          ]
                        );
                      }
                    }}
                  >
                    <View
                      style={[
                        styles.messageBubble,
                        message.sender === 'user' ? styles.userBubble : 
                        message.sender === 'admin' ? styles.adminBubble : styles.systemBubble,
                        message.status === 'error' && styles.errorBubble,
                      ]}
                    >
                      {message.sender === 'admin' && (
                        <View style={styles.adminLabel}>
                          <Ionicons name="headset" size={12} color="#F5A623" />
                          <Text style={styles.adminLabelText}>Soporte RIS</Text>
                        </View>
                      )}
                      
                      {/* Image if present */}
                      {message.image && (
                        <TouchableOpacity onPress={() => setPreviewImage(message.image || null)}>
                          <Image 
                            source={{ uri: message.image }} 
                            style={styles.messageImage}
                            resizeMode="cover"
                          />
                        </TouchableOpacity>
                      )}
                      
                      {message.text && (
                        <Text
                          style={[
                            styles.messageText,
                            message.sender === 'user' ? styles.userMessageText : 
                            message.sender === 'admin' ? styles.adminMessageText : styles.systemMessageText,
                          ]}
                        >
                          {message.text}
                        </Text>
                      )}
                      
                      {message.timestamp.getTime() !== 0 && (
                        <View style={styles.messageFooter}>
                          <Text
                            style={[
                              styles.messageTime,
                              message.sender === 'user' ? styles.userMessageTime : styles.otherMessageTime,
                            ]}
                          >
                            {formatTime(message.timestamp)}
                          </Text>
                          {message.sender === 'user' && (
                            <View style={styles.statusIcon}>
                              {getStatusIcon(message.status)}
                            </View>
                          )}
                        </View>
                      )}
                      
                      {message.status === 'error' && (
                        <View style={styles.retryHint}>
                          <Ionicons name="refresh" size={12} color="#fca5a5" />
                          <Text style={styles.retryHintText}>Toca para reintentar</Text>
                        </View>
                      )}
                    </View>
                  </TouchableOpacity>
                </View>
              );
            })}
            
            {/* Quick Replies */}
            {showQuickReplies && messages.length <= 1 && (
              <View style={styles.quickRepliesSection}>
                <Text style={styles.quickRepliesTitle}>Preguntas frecuentes</Text>
                <View style={styles.quickRepliesContainer}>
                  {QUICK_REPLIES.map((reply) => (
                    <TouchableOpacity
                      key={reply.id}
                      style={styles.quickReplyButton}
                      onPress={() => selectQuickReply(reply)}
                    >
                      <Ionicons name={reply.icon as any} size={18} color="#F5A623" />
                      <Text style={styles.quickReplyText}>{reply.text}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            )}
          </ScrollView>
        )}

        {/* Selected Image Preview */}
        {selectedImage && (
          <View style={styles.selectedImageContainer}>
            <Image source={{ uri: selectedImage }} style={styles.selectedImagePreview} />
            <TouchableOpacity style={styles.removeImageButton} onPress={removeSelectedImage}>
              <View style={styles.removeImageButtonInner}>
                <Ionicons name="close" size={16} color="#fff" />
              </View>
            </TouchableOpacity>
          </View>
        )}

        {/* Input Area */}
        <View style={styles.inputContainer}>
          <View style={styles.inputRow}>
            <TouchableOpacity style={styles.attachButton} onPress={pickImage}>
              <Ionicons name="image-outline" size={22} color="#64748b" />
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachButton} onPress={takePhoto}>
              <Ionicons name="camera-outline" size={22} color="#64748b" />
            </TouchableOpacity>
            <View style={styles.textInputContainer}>
              <TextInput
                style={styles.textInput}
                value={inputText}
                onChangeText={setInputText}
                placeholder="Escribe tu mensaje..."
                placeholderTextColor="#94a3b8"
                multiline
                maxLength={500}
                editable={!sending}
              />
            </View>
            <TouchableOpacity
              style={[
                styles.sendButton, 
                ((!inputText.trim() && !selectedImage) || sending) && styles.sendButtonDisabled
              ]}
              onPress={sendMessage}
              disabled={(!inputText.trim() && !selectedImage) || sending}
            >
              {sending ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Ionicons name="send" size={18} color="#fff" />
              )}
            </TouchableOpacity>
          </View>
          <Text style={styles.inputHint}>
            Respuesta típica en menos de 5 minutos
          </Text>
        </View>
      </KeyboardAvoidingView>

      {/* Image Preview Modal */}
      <Modal
        visible={!!previewImage}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setPreviewImage(null)}
      >
        <View style={styles.imagePreviewModal}>
          <TouchableOpacity 
            style={styles.closePreviewButton} 
            onPress={() => setPreviewImage(null)}
          >
            <Ionicons name="close" size={32} color="#fff" />
          </TouchableOpacity>
          {previewImage && (
            <Image 
              source={{ uri: previewImage }} 
              style={styles.fullPreviewImage}
              resizeMode="contain"
            />
          )}
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 8,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  headerButton: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerCenter: {
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#0f172a',
  },
  statusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusDotOnline: {
    backgroundColor: '#22c55e',
  },
  statusDotReconnecting: {
    backgroundColor: '#f59e0b',
  },
  statusDotOffline: {
    backgroundColor: '#ef4444',
  },
  statusText: {
    fontSize: 12,
  },
  statusTextOnline: {
    color: '#22c55e',
  },
  statusTextReconnecting: {
    color: '#f59e0b',
  },
  connectionWarning: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef3c7',
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
  },
  connectionWarningText: {
    flex: 1,
    fontSize: 13,
    color: '#92400e',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  emptyIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#fef3c7',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 15,
    color: '#64748b',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 22,
  },
  loadingText: {
    fontSize: 14,
    color: '#64748b',
    marginTop: 12,
  },
  loginButton: {
    backgroundColor: '#F5A623',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 12,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  messagesContainer: {
    flex: 1,
  },
  messagesContent: {
    padding: 16,
    paddingBottom: 8,
  },
  dateSeparator: {
    alignItems: 'center',
    marginVertical: 16,
  },
  dateSeparatorText: {
    fontSize: 12,
    color: '#64748b',
    backgroundColor: '#e2e8f0',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 10,
    fontWeight: '500',
  },
  messageBubble: {
    maxWidth: '85%',
    padding: 12,
    borderRadius: 18,
    marginBottom: 8,
  },
  userBubble: {
    backgroundColor: '#0f172a',
    alignSelf: 'flex-end',
    borderBottomRightRadius: 4,
  },
  adminBubble: {
    backgroundColor: '#fff',
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: '#F5A623',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  systemBubble: {
    backgroundColor: '#fff',
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  errorBubble: {
    backgroundColor: '#1e293b',
    opacity: 0.8,
  },
  adminLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: 6,
  },
  adminLabelText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#F5A623',
  },
  messageImage: {
    width: 200,
    height: 150,
    borderRadius: 12,
    marginBottom: 8,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 21,
  },
  userMessageText: {
    color: '#fff',
  },
  adminMessageText: {
    color: '#1f2937',
  },
  systemMessageText: {
    color: '#1f2937',
  },
  messageFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginTop: 4,
    gap: 4,
  },
  messageTime: {
    fontSize: 11,
  },
  userMessageTime: {
    color: 'rgba(255,255,255,0.6)',
  },
  otherMessageTime: {
    color: '#94a3b8',
  },
  statusIcon: {
    marginLeft: 2,
  },
  retryHint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 6,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.1)',
  },
  retryHintText: {
    fontSize: 11,
    color: '#fca5a5',
  },
  quickRepliesSection: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  quickRepliesTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748b',
    marginBottom: 12,
    textAlign: 'center',
  },
  quickRepliesContainer: {
    gap: 8,
  },
  quickReplyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    gap: 12,
  },
  quickReplyText: {
    flex: 1,
    fontSize: 14,
    color: '#374151',
  },
  selectedImageContainer: {
    backgroundColor: '#fff',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    position: 'relative',
  },
  selectedImagePreview: {
    width: 72,
    height: 72,
    borderRadius: 10,
  },
  removeImageButton: {
    position: 'absolute',
    top: 4,
    left: 72,
  },
  removeImageButtonInner: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
  },
  inputContainer: {
    backgroundColor: '#fff',
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 6,
  },
  attachButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textInputContainer: {
    flex: 1,
    backgroundColor: '#f1f5f9',
    borderRadius: 20,
    paddingHorizontal: 16,
    minHeight: 40,
    maxHeight: 100,
    justifyContent: 'center',
  },
  textInput: {
    fontSize: 15,
    color: '#0f172a',
    paddingVertical: 10,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#F5A623',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#cbd5e1',
  },
  inputHint: {
    fontSize: 11,
    color: '#94a3b8',
    textAlign: 'center',
    marginTop: 6,
  },
  imagePreviewModal: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.95)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closePreviewButton: {
    position: 'absolute',
    top: 50,
    right: 20,
    zIndex: 10,
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullPreviewImage: {
    width: '100%',
    height: '80%',
  },
});
