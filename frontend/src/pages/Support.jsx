import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ArrowLeft, Send, Bot, User, HelpCircle, Headphones } from 'lucide-react';
import api from '../utils/api';
import toast from 'react-hot-toast';

export default function Support() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setMessages([
      {
        id: 1,
        type: 'bot',
        text: `¡Hola ${user?.name?.split(' ')[0] || 'Usuario'}! Soy el asistente virtual de RIS. ¿En qué puedo ayudarte hoy?`,
        time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
      }
    ]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
            ? '✅ Tu mensaje ha sido enviado al equipo de soporte. Te responderemos por WhatsApp o aquí en la app lo antes posible.'
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
      <div style={{ padding: '16px 24px', backgroundColor: 'rgba(255,255,255,0.9)', borderBottom: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button 
            onClick={() => navigate(-1)} 
            style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: '#f3f4f6', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            data-testid="back-button"
          >
            <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
          </button>
          <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 6px rgba(99, 102, 241, 0.3)' }}>
            <Headphones style={{ width: '24px', height: '24px', color: '#ffffff' }} />
          </div>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Soporte RIS</h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
              <div style={{ width: '8px', height: '8px', backgroundColor: '#22c55e', borderRadius: '50%' }} />
              <span style={{ fontSize: '12px', color: '#22c55e', fontWeight: '500' }}>En línea</span>
            </div>
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div style={{ flex: 1, overflow: 'auto', padding: '24px' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {messages.map((msg) => (
            <div key={msg.id} style={{ display: 'flex', justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start' }}>
              {msg.type === 'bot' && (
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '12px', flexShrink: 0 }}>
                  <Bot style={{ width: '20px', height: '20px', color: '#ffffff' }} />
                </div>
              )}
              <div style={{ maxWidth: '75%' }}>
                <div style={{
                  padding: '14px 18px',
                  borderRadius: msg.type === 'user' ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
                  backgroundColor: msg.type === 'user' ? '#6366f1' : '#ffffff',
                  color: msg.type === 'user' ? '#ffffff' : '#374151',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                  border: msg.type === 'bot' ? '1px solid #e5e7eb' : 'none'
                }}>
                  <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.5' }}>{msg.text}</p>
                </div>
                <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '6px', textAlign: msg.type === 'user' ? 'right' : 'left' }}>{msg.time}</p>
              </div>
              {msg.type === 'user' && (
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: '#e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: '12px', flexShrink: 0 }}>
                  <span style={{ color: '#6b7280', fontWeight: '600', fontSize: '14px' }}>{user?.name?.charAt(0)?.toUpperCase() || 'U'}</span>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '12px' }}>
                <Bot style={{ width: '20px', height: '20px', color: '#ffffff' }} />
              </div>
              <div style={{ padding: '16px 20px', backgroundColor: '#ffffff', borderRadius: '20px 20px 20px 4px', border: '1px solid #e5e7eb' }}>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <div style={{ width: '8px', height: '8px', backgroundColor: '#d1d5db', borderRadius: '50%', animation: 'bounce 1s infinite' }} />
                  <div style={{ width: '8px', height: '8px', backgroundColor: '#d1d5db', borderRadius: '50%', animation: 'bounce 1s infinite 0.15s' }} />
                  <div style={{ width: '8px', height: '8px', backgroundColor: '#d1d5db', borderRadius: '50%', animation: 'bounce 1s infinite 0.3s' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick Questions */}
      {messages.length <= 2 && (
        <div style={{ padding: '16px 24px', backgroundColor: 'rgba(255,255,255,0.9)', borderTop: '1px solid #e5e7eb' }}>
          <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <HelpCircle style={{ width: '16px', height: '16px', color: '#9ca3af' }} />
              <p style={{ fontSize: '12px', color: '#6b7280', fontWeight: '500', margin: 0 }}>Preguntas frecuentes</p>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {quickQuestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => setNewMessage(q.text)}
                  style={{
                    padding: '10px 16px',
                    backgroundColor: '#f3f4f6',
                    border: 'none',
                    borderRadius: '9999px',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: '500',
                    color: '#374151',
                    transition: 'all 0.2s'
                  }}
                  data-testid={`quick-question-${i}`}
                >
                  {q.text}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div style={{ padding: '16px 24px', backgroundColor: 'rgba(255,255,255,0.95)', borderTop: '1px solid #e5e7eb' }}>
        <form onSubmit={handleSendMessage} style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', gap: '12px' }}>
          <input
            type="text"
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder="Escribe tu mensaje..."
            disabled={loading}
            style={{
              flex: 1,
              padding: '14px 20px',
              borderRadius: '16px',
              border: '1px solid #e5e7eb',
              fontSize: '14px',
              outline: 'none',
              backgroundColor: '#ffffff'
            }}
            data-testid="message-input"
          />
          <button
            type="submit"
            disabled={loading || !newMessage.trim()}
            style={{
              padding: '14px 20px',
              backgroundColor: '#6366f1',
              color: '#ffffff',
              borderRadius: '16px',
              border: 'none',
              cursor: 'pointer',
              opacity: loading || !newMessage.trim() ? 0.5 : 1
            }}
            data-testid="send-message"
          >
            <Send style={{ width: '20px', height: '20px' }} />
          </button>
        </form>
      </div>

      <style>{`@keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }`}</style>
    </div>
  );
}
