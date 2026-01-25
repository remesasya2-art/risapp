import React, { useState, useRef, useEffect } from 'react';
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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'system';
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
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: '¡Hola! 👋 Bienvenido al soporte de RIS.\n\nEscribe tu mensaje y nuestro equipo te responderá por WhatsApp lo antes posible.',
      sender: 'system',
      timestamp: new Date(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    // Load chat history from AsyncStorage
    loadChatHistory();
  }, []);

  const loadChatHistory = async () => {
    try {
      const history = await AsyncStorage.getItem('support_chat_history');
      if (history) {
        const parsed = JSON.parse(history);
        // Convert timestamps back to Date objects
        const messagesWithDates = parsed.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp),
        }));
        setMessages([
          {
            id: '1',
            text: '¡Hola! 👋 Bienvenido al soporte de RIS.\n\nEscribe tu mensaje y nuestro equipo te responderá por WhatsApp lo antes posible.',
            sender: 'system',
            timestamp: new Date(),
          },
          ...messagesWithDates,
        ]);
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  };

  const saveChatHistory = async (newMessages: Message[]) => {
    try {
      // Only save user messages
      const userMessages = newMessages.filter(m => m.sender === 'user');
      await AsyncStorage.setItem('support_chat_history', JSON.stringify(userMessages.slice(-20))); // Keep last 20 messages
    } catch (error) {
      console.error('Error saving chat history:', error);
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim()) return;
    
    if (!user) {
      showAlert('Inicia sesión', 'Debes iniciar sesión para enviar mensajes de soporte.');
      return;
    }

    const messageText = inputText.trim();
    setInputText('');

    const newMessage: Message = {
      id: Date.now().toString(),
      text: messageText,
      sender: 'user',
      timestamp: new Date(),
      status: 'sending',
    };

    setMessages(prev => [...prev, newMessage]);
    setSending(true);

    try {
      const token = await AsyncStorage.getItem('session_token');
      await axios.post(
        `${BACKEND_URL}/api/support/send`,
        { message: messageText },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      // Update message status to sent
      setMessages(prev =>
        prev.map(m =>
          m.id === newMessage.id ? { ...m, status: 'sent' } : m
        )
      );

      // Add confirmation message
      const confirmMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: '✅ Mensaje enviado. Nuestro equipo te contactará por WhatsApp pronto.',
        sender: 'system',
        timestamp: new Date(),
      };
      
      setMessages(prev => {
        const updated = [...prev, confirmMessage];
        saveChatHistory(updated);
        return updated;
      });

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

    // Scroll to bottom
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
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
          <View style={{ width: 24 }} />
        </View>

        {/* Info Banner */}
        <View style={styles.infoBanner}>
          <Ionicons name="information-circle" size={20} color="#2563eb" />
          <Text style={styles.infoBannerText}>
            Los mensajes serán enviados a nuestro equipo vía WhatsApp
          </Text>
        </View>

        {/* Messages */}
        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
          onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.map((message) => (
            <View
              key={message.id}
              style={[
                styles.messageBubble,
                message.sender === 'user' ? styles.userBubble : styles.systemBubble,
              ]}
            >
              <Text
                style={[
                  styles.messageText,
                  message.sender === 'user' ? styles.userMessageText : styles.systemMessageText,
                ]}
              >
                {message.text}
              </Text>
              <View style={styles.messageFooter}>
                <Text
                  style={[
                    styles.messageTime,
                    message.sender === 'user' ? styles.userMessageTime : styles.systemMessageTime,
                  ]}
                >
                  {formatTime(message.timestamp)}
                </Text>
                {message.sender === 'user' && message.status && (
                  <View style={styles.statusIcon}>
                    {message.status === 'sending' && (
                      <Ionicons name="time-outline" size={14} color="#fff" />
                    )}
                    {message.status === 'sent' && (
                      <Ionicons name="checkmark-done" size={14} color="#fff" />
                    )}
                    {message.status === 'error' && (
                      <Ionicons name="alert-circle" size={14} color="#fca5a5" />
                    )}
                  </View>
                )}
              </View>
            </View>
          ))}
        </ScrollView>

        {/* Input Area */}
        <View style={styles.inputContainer}>
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
            style={[styles.sendButton, (!inputText.trim() || sending) && styles.sendButtonDisabled]}
            onPress={sendMessage}
            disabled={!inputText.trim() || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Ionicons name="send" size={20} color="#fff" />
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
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
  },
  messageBubble: {
    maxWidth: '80%',
    padding: 12,
    borderRadius: 16,
    marginBottom: 12,
  },
  userBubble: {
    backgroundColor: '#2563eb',
    alignSelf: 'flex-end',
    borderBottomRightRadius: 4,
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
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  userMessageText: {
    color: '#fff',
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
  systemMessageTime: {
    color: '#9ca3af',
  },
  statusIcon: {
    marginLeft: 2,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 12,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    gap: 8,
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
});
