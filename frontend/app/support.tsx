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
  status?: 'sending' | 'sent' | 'error';
}

const showAlert = (title: string, message: string) => {
  if (Platform.OS === 'web') {
    alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
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
  const scrollViewRef = useRef<ScrollView>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Load conversation when screen is focused
  useFocusEffect(
    useCallback(() => {
      if (user) {
        loadConversation();
        // Start polling for new messages every 5 seconds
        pollIntervalRef.current = setInterval(loadConversation, 5000);
      }
      
      return () => {
        // Clear polling when leaving screen
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }
      };
    }, [user])
  );

  const loadConversation = async () => {
    try {
      const token = await AsyncStorage.getItem('session_token');
      const response = await axios.get(`${BACKEND_URL}/api/support/conversation`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      const welcomeMessage: Message = {
        id: 'welcome',
        text: '¡Hola! 👋 Bienvenido al soporte de RIS.\n\nEscribe tu mensaje o adjunta una imagen y nuestro equipo te responderá lo antes posible.',
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
      
      setMessages([welcomeMessage, ...conversationMessages]);
      setLoading(false);
      
      // Scroll to bottom
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: false });
      }, 100);
      
    } catch (error) {
      console.error('Error loading conversation:', error);
      setLoading(false);
      setMessages([{
        id: 'welcome',
        text: '¡Hola! 👋 Bienvenido al soporte de RIS.\n\nEscribe tu mensaje o adjunta una imagen y nuestro equipo te responderá lo antes posible.',
        sender: 'system',
        timestamp: new Date(),
      }]);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadConversation();
    setRefreshing(false);
  };

  const pickImage = async () => {
    try {
      // Request permission
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
      // Request permission
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

    const newMessage: Message = {
      id: Date.now().toString(),
      text: messageText || (imageToSend ? '📷 Imagen' : ''),
      image: imageToSend || undefined,
      sender: 'user',
      timestamp: new Date(),
      status: 'sending',
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
        { headers: { Authorization: `Bearer ${token}` } }
      );

      // Update message status to sent
      setMessages(prev =>
        prev.map(m =>
          m.id === newMessage.id ? { ...m, status: 'sent' } : m
        )
      );

    } catch (error: any) {
      console.error('Error sending message:', error);
      
      // Update message status to error
      setMessages(prev =>
        prev.map(m =>
          m.id === newMessage.id ? { ...m, status: 'error' } : m
        )
      );

      showAlert('Error', error.response?.data?.detail || 'No se pudo enviar el mensaje. Intenta de nuevo.');
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
      return date.toLocaleDateString('es', { day: '2-digit', month: '2-digit', year: 'numeric' });
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Ayuda y Soporte</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.centerContainer}>
          <Ionicons name="chatbubbles-outline" size={60} color="#6b7280" />
          <Text style={styles.emptyText}>Inicia sesión para contactar soporte</Text>
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
          <TouchableOpacity onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#1f2937" />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={styles.headerTitle}>Ayuda y Soporte</Text>
            <View style={styles.onlineIndicator}>
              <View style={styles.onlineDot} />
              <Text style={styles.onlineText}>En línea</Text>
            </View>
          </View>
          <TouchableOpacity onPress={onRefresh}>
            <Ionicons name="refresh" size={24} color="#2563eb" />
          </TouchableOpacity>
        </View>

        {/* Info Banner */}
        <View style={styles.infoBanner}>
          <Ionicons name="information-circle" size={20} color="#2563eb" />
          <Text style={styles.infoBannerText}>
            Chat en vivo • Puedes adjuntar imágenes 📷
          </Text>
        </View>

        {/* Messages */}
        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color="#2563eb" />
            <Text style={styles.loadingText}>Cargando conversación...</Text>
          </View>
        ) : (
          <ScrollView
            ref={scrollViewRef}
            style={styles.messagesContainer}
            contentContainerStyle={styles.messagesContent}
            onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: false })}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
            }
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
                  <View
                    style={[
                      styles.messageBubble,
                      message.sender === 'user' ? styles.userBubble : 
                      message.sender === 'admin' ? styles.adminBubble : styles.systemBubble,
                    ]}
                  >
                    {message.sender === 'admin' && (
                      <View style={styles.adminLabel}>
                        <Ionicons name="headset" size={12} color="#10b981" />
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
                    
                    {message.text && message.text !== '📷 Imagen' && (
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
                        {message.sender === 'user' && message.status && (
                          <View style={styles.statusIcon}>
                            {message.status === 'sending' && (
                              <Ionicons name="time-outline" size={14} color="rgba(255,255,255,0.7)" />
                            )}
                            {message.status === 'sent' && (
                              <Ionicons name="checkmark-done" size={14} color="rgba(255,255,255,0.9)" />
                            )}
                            {message.status === 'error' && (
                              <Ionicons name="alert-circle" size={14} color="#fca5a5" />
                            )}
                          </View>
                        )}
                      </View>
                    )}
                  </View>
                </View>
              );
            })}
          </ScrollView>
        )}

        {/* Selected Image Preview */}
        {selectedImage && (
          <View style={styles.selectedImageContainer}>
            <Image source={{ uri: selectedImage }} style={styles.selectedImagePreview} />
            <TouchableOpacity style={styles.removeImageButton} onPress={removeSelectedImage}>
              <Ionicons name="close-circle" size={24} color="#ef4444" />
            </TouchableOpacity>
          </View>
        )}

        {/* Input Area */}
        <View style={styles.inputContainer}>
          <TouchableOpacity style={styles.attachButton} onPress={pickImage}>
            <Ionicons name="image-outline" size={24} color="#6b7280" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.attachButton} onPress={takePhoto}>
            <Ionicons name="camera-outline" size={24} color="#6b7280" />
          </TouchableOpacity>
          <TextInput
            style={styles.textInput}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Escribe tu mensaje..."
            placeholderTextColor="#9ca3af"
            multiline
            maxLength={500}
            editable={!sending}
          />
          <TouchableOpacity
            style={[styles.sendButton, ((!inputText.trim() && !selectedImage) || sending) && styles.sendButtonDisabled]}
            onPress={sendMessage}
            disabled={(!inputText.trim() && !selectedImage) || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Ionicons name="send" size={20} color="#fff" />
            )}
          </TouchableOpacity>
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
    backgroundColor: '#f3f4f6',
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  headerCenter: {
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
  },
  onlineIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  onlineDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#10b981',
    marginRight: 4,
  },
  onlineText: {
    fontSize: 12,
    color: '#10b981',
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
  loadingText: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 12,
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
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
  },
  infoBannerText: {
    flex: 1,
    fontSize: 13,
    color: '#2563eb',
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
    color: '#6b7280',
    backgroundColor: '#e5e7eb',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 10,
  },
  messageBubble: {
    maxWidth: '85%',
    padding: 12,
    borderRadius: 16,
    marginBottom: 8,
  },
  userBubble: {
    backgroundColor: '#2563eb',
    alignSelf: 'flex-end',
    borderBottomRightRadius: 4,
  },
  adminBubble: {
    backgroundColor: '#fff',
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: '#10b981',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  systemBubble: {
    backgroundColor: '#fff',
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
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
    color: '#10b981',
  },
  messageImage: {
    width: 200,
    height: 150,
    borderRadius: 8,
    marginBottom: 8,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
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
    color: 'rgba(255,255,255,0.7)',
  },
  otherMessageTime: {
    color: '#9ca3af',
  },
  statusIcon: {
    marginLeft: 2,
  },
  selectedImageContainer: {
    backgroundColor: '#fff',
    padding: 8,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    position: 'relative',
  },
  selectedImagePreview: {
    width: 80,
    height: 80,
    borderRadius: 8,
  },
  removeImageButton: {
    position: 'absolute',
    top: 0,
    left: 72,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 8,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    gap: 4,
  },
  attachButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textInput: {
    flex: 1,
    backgroundColor: '#f3f4f6',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 16,
    maxHeight: 100,
    color: '#1f2937',
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#93c5fd',
  },
  imagePreviewModal: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closePreviewButton: {
    position: 'absolute',
    top: 50,
    right: 20,
    zIndex: 10,
  },
  fullPreviewImage: {
    width: '100%',
    height: '80%',
  },
});
