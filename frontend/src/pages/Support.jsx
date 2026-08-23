import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ArrowLeft, Send, Bot, User, HelpCircle, Headphones, RefreshCw } from 'lucide-react';
import api from '../utils/api';
import toast from 'react-hot-toast';

export default function Support() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadConversation();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadConversation = async () => {
    setRefreshing(true);
    try {
      const response = await api.get('/support/conversation');
      const conversation = response.data || [];
      
      // Format messages
      const formattedMessages = conversation.map(msg => ({
        id: msg.id,
        type: msg.sender === 'user' ? 'user' : 'admin',
        text: msg.text,
        time: msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) : ''
      }));

      // Add welcome message if no messages
      if (formattedMessages.length === 0) {
        setMessages([{
          id: 'welcome',
          type: 'bot',
          text: `¡Hola ${user?.name?.split(' ')[0] || 'Usuario'}! Soy el asistente de soporte de RIS. ¿En qué puedo ayudarte hoy?`,
          time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
        }]);
      } else {
        // Add welcome message at the beginning
        setMessages([
          {
            id: 'welcome',
            type: 'bot',
            text: `¡Hola ${user?.name?.split(' ')[0] || 'Usuario'}! Aquí está tu historial de soporte.`,
            time: ''
          },
          ...formattedMessages
        ]);
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
      setMessages([{
        id: 'welcome',
        type: 'bot',
        text: `¡Hola ${user?.name?.split(' ')[0] || 'Usuario'}! Soy el asistente de soporte de RIS. ¿En qué puedo ayudarte hoy?`,
        time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
      }]);
    } finally {
      setRefreshing(false);
    }
  };

  const handleRefresh = async () => {
    await loadConversation();
    toast.success('Chat actualizado');
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;

    const userMsg = {
      id: Date.now(),
      type: 'user',
      text: newMessage.trim(),
      time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    const messageToSend = newMessage.trim();
    setNewMessage('');
    setLoading(true);

    try {
      const response = await api.post('/support/send', { message: messageToSend });
      setTimeout(() => {
        const botResponse = {
          id: Date.now() + 1,
          type: 'bot',
          text: response?.data?.status === 'success' 
            ? '✅ Tu mensaje ha sido enviado al equipo de soporte. Te responderemos aquí en la app. Usa el botón 🔄 para ver nuevas respuestas.'
            : 'Tu mensaje ha sido recibido. Un agente de soporte te responderá pronto.',
          time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
        };
        setMessages(prev => [...prev, botResponse]);
        setLoading(false);
      }, 1000);
    } catch (error) {
      console.error('Support error:', error);
      const errorMsg = {
        id: Date.now() + 1,
        type: 'bot',
        text: '❌ No se pudo enviar el mensaje. Por favor intenta de nuevo.',
        time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
      };
      setMessages(prev => [...prev, errorMsg]);
      toast.error('Error al enviar mensaje');
      setLoading(false);
    }
  };

  const quickQuestions = [
    { text: '¿Cómo recargo mi saldo?' },
    { text: '¿Cuánto tarda un envío?' },
    { text: '¿Cómo verifico mi cuenta?' },
    { text: '¿Cuáles son las tasas?' }
  ];

  const pageStyle = {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  return (
    <div style={pageStyle} data-testid="support-page">
      {/* Header */}
      <div style={{ 
        padding: '16px 24px', 
        backgroundColor: 'rgba(255,255,255,0.9)',
        borderBottom: '1px solid #e5e7eb',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button 
            onClick={() => navigate(-1)} 
            style={{ 
              width: '36px', height: '36px', borderRadius: '10px', border: 'none', 
              backgroundColor: '#f3f4f6', cursor: 'pointer', 
              display: 'flex', alignItems: 'center', justifyContent: 'center' 
            }}
          >
            <ArrowLeft style={{ width: '18px', height: '18px', color: '#374151' }} />
          </button>
          <div style={{ 
            width: '40px', height: '40px', borderRadius: '50%', 
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Headphones style={{ width: '20px', height: '20px', color: '#ffffff' }} />
          </div>
          <div>
            <h1 style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>Soporte RIS</h1>
            <p style={{ fontSize: '12px', color: '#16a34a', margin: 0, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#16a34a' }}></span>
              En línea
            </p>
          </div>
        </div>
        
        {/* Refresh Button */}
        <button 
          onClick={handleRefresh}
          disabled={refreshing}
          style={{ 
            width: '44px', height: '44px', borderRadius: '12px', border: 'none', 
            backgroundColor: '#dbeafe', cursor: 'pointer', 
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s'
          }}
          data-testid="refresh-chat-btn"
          title="Actualizar chat"
        >
          <RefreshCw style={{ 
            width: '20px', height: '20px', color: '#2563eb',
            animation: refreshing ? 'spin 1s linear infinite' : 'none'
          }} />
        </button>
      </div>

      {/* Messages Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
        {messages.map((msg) => (
          <div 
            key={msg.id} 
            style={{ 
              display: 'flex', 
              justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: '16px'
            }}
          >
            {msg.type !== 'user' && (
              <div style={{ 
                width: '32px', height: '32px', borderRadius: '50%', marginRight: '8px',
                background: msg.type === 'admin' ? 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)' : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
              }}>
                {msg.type === 'admin' ? (
                  <Headphones style={{ width: '16px', height: '16px', color: '#ffffff' }} />
                ) : (
                  <Bot style={{ width: '16px', height: '16px', color: '#ffffff' }} />
                )}
              </div>
            )}
            <div style={{ 
              maxWidth: '75%', 
              padding: '12px 16px', 
              borderRadius: msg.type === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
              backgroundColor: msg.type === 'user' ? '#6366f1' : msg.type === 'admin' ? '#dcfce7' : '#ffffff',
              color: msg.type === 'user' ? '#ffffff' : '#111827',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              border: msg.type === 'admin' ? '1px solid #bbf7d0' : 'none'
            }}>
              {msg.type === 'admin' && (
                <p style={{ fontSize: '11px', color: '#16a34a', margin: '0 0 4px 0', fontWeight: '600' }}>
                  📱 Respuesta del Soporte
                </p>
              )}
              <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.5' }}>{msg.text}</p>
              {msg.time && (
                <p style={{ 
                  margin: '6px 0 0 0', fontSize: '11px', 
                  color: msg.type === 'user' ? 'rgba(255,255,255,0.7)' : '#9ca3af',
                  textAlign: 'right'
                }}>
                  {msg.time}
                </p>
              )}
            </div>
            {msg.type === 'user' && (
              <div style={{ 
                width: '32px', height: '32px', borderRadius: '50%', marginLeft: '8px',
                backgroundColor: '#e5e7eb',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
              }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#374151' }}>
                  {user?.name?.charAt(0) || 'U'}
                </span>
              </div>
            )}
          </div>
        ))}
        
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '16px' }}>
            <div style={{ 
              width: '32px', height: '32px', borderRadius: '50%', marginRight: '8px',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Bot style={{ width: '16px', height: '16px', color: '#ffffff' }} />
            </div>
            <div style={{ 
              padding: '12px 16px', borderRadius: '18px 18px 18px 4px',
              backgroundColor: '#ffffff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
            }}>
              <div style={{ display: 'flex', gap: '4px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1', animation: 'bounce 1s infinite' }}></div>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1', animation: 'bounce 1s infinite 0.2s' }}></div>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1', animation: 'bounce 1s infinite 0.4s' }}></div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Questions */}
      <div style={{ padding: '12px 24px', backgroundColor: 'rgba(255,255,255,0.5)' }}>
        <p style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <HelpCircle style={{ width: '14px', height: '14px' }} />
          Preguntas frecuentes
        </p>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {quickQuestions.map((q, i) => (
            <button 
              key={i}
              onClick={() => setNewMessage(q.text)}
              style={{ 
                padding: '8px 14px', borderRadius: '20px', border: 'none',
                backgroundColor: '#ffffff', color: '#374151', fontSize: '13px',
                cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
              }}
            >
              {q.text}
            </button>
          ))}
        </div>
      </div>

      {/* Input Area */}
      <form 
        onSubmit={handleSendMessage}
        style={{ 
          padding: '16px 24px', 
          backgroundColor: '#ffffff',
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          gap: '12px'
        }}
      >
        <input 
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Escribe tu mensaje..."
          style={{ 
            flex: 1, padding: '14px 18px', borderRadius: '24px',
            border: '1px solid #e5e7eb', fontSize: '14px', outline: 'none'
          }}
          data-testid="support-input"
        />
        <button 
          type="submit"
          disabled={!newMessage.trim() || loading}
          style={{ 
            width: '50px', height: '50px', borderRadius: '50%',
            backgroundColor: newMessage.trim() ? '#6366f1' : '#e5e7eb',
            border: 'none', cursor: newMessage.trim() ? 'pointer' : 'default',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s'
          }}
          data-testid="send-support-btn"
        >
          <Send style={{ width: '20px', height: '20px', color: newMessage.trim() ? '#ffffff' : '#9ca3af' }} />
        </button>
      </form>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes bounce { 
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
      `}</style>
    </div>
  );
}
