import { useState, useEffect, useRef } from 'react';
import { MessageSquare, Send, X, ChevronDown } from 'lucide-react';
import api from '../utils/api';
import { abrirArchivo, rutaDeArchivo } from '../utils/urlDeArchivo';
import toast from 'react-hot-toast';

export default function SupportChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [conv, setConv] = useState(null);
  const [ratingStars, setRatingStars] = useState(0);
  const [ratingComment, setRatingComment] = useState('');
  const [ratingDone, setRatingDone] = useState(false);
  const [submittingRating, setSubmittingRating] = useState(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadMessages = async () => {
    try {
      const response = await api.get('/support/history');
      setMessages(response.data || []);
      // Count unread admin messages
      const unread = (response.data || []).filter(m => m.sender === 'admin' && !m.read).length;
      setUnreadCount(unread);
    } catch (error) {
      console.error('Error loading messages:', error);
    }
  };

  const loadConversation = async () => {
    try {
      const res = await api.get('/support/conversation');
      setConv(res.data || null);
    } catch (error) { /* silencioso */ }
  };

  useEffect(() => {
    loadMessages();
    loadConversation();
    // Poll for new messages every 10 seconds
    const interval = setInterval(() => { loadMessages(); loadConversation(); }, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      setUnreadCount(0);
    }
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!newMessage.trim() || sending) return;
    
    setSending(true);
    try {
      await api.post('/support/send', { message: newMessage.trim() });
      setNewMessage('');
      await loadMessages();
      toast.success('Mensaje enviado');
    } catch (error) {
      toast.error('Error al enviar mensaje');
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const submitRating = async () => {
    if (ratingStars < 1 || submittingRating) return;
    setSubmittingRating(true);
    try {
      await api.post('/support/rate', { stars: ratingStars, comment: ratingComment.trim() || null });
      setRatingDone(true);
      toast.success('¡Gracias por tu calificación!');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'No se pudo enviar la calificación');
    } finally {
      setSubmittingRating(false);
    }
  };

  return (
    <>
      {/* Floating Chat Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          backgroundColor: '#6366f1',
          color: 'white',
          border: 'none',
          boxShadow: '0 4px 20px rgba(99, 102, 241, 0.4)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          transition: 'transform 0.2s, box-shadow 0.2s'
        }}
        data-testid="support-chat-button"
      >
        {isOpen ? (
          <ChevronDown style={{ width: '28px', height: '28px' }} />
        ) : (
          <>
            <MessageSquare style={{ width: '28px', height: '28px' }} />
            {unreadCount > 0 && (
              <span style={{
                position: 'absolute',
                top: '-4px',
                right: '-4px',
                backgroundColor: '#ef4444',
                color: 'white',
                borderRadius: '50%',
                width: '22px',
                height: '22px',
                fontSize: '12px',
                fontWeight: '700',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                {unreadCount}
              </span>
            )}
          </>
        )}
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div style={{
          position: 'fixed',
          bottom: '100px',
          right: '24px',
          width: '360px',
          maxWidth: 'calc(100vw - 48px)',
          height: '480px',
          maxHeight: 'calc(100vh - 140px)',
          backgroundColor: 'white',
          borderRadius: '20px',
          boxShadow: '0 10px 40px rgba(0, 0, 0, 0.15)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          zIndex: 1000
        }} data-testid="support-chat-window">
          {/* Header */}
          <div style={{
            padding: '16px 20px',
            backgroundColor: '#6366f1',
            color: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: 'rgba(255,255,255,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <MessageSquare style={{ width: '20px', height: '20px' }} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Soporte RIS</h3>
                <p style={{ margin: 0, fontSize: '12px', opacity: 0.8 }}>Estamos aquí para ayudarte</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', padding: '4px' }}
            >
              <X style={{ width: '20px', height: '20px' }} />
            </button>
          </div>

          {/* Messages */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            backgroundColor: '#f9fafb'
          }}>
            {messages.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#9ca3af', padding: '40px 20px' }}>
                <MessageSquare style={{ width: '48px', height: '48px', margin: '0 auto 12px', opacity: 0.5 }} />
                <p style={{ fontSize: '14px' }}>¡Hola! ¿En qué podemos ayudarte?</p>
                <p style={{ fontSize: '12px' }}>Escribe tu mensaje y te responderemos pronto.</p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.message_id}
                  style={{
                    alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '80%'
                  }}
                >
                  <div style={{
                    padding: '12px 16px',
                    borderRadius: msg.sender === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                    backgroundColor: msg.sender === 'user' ? '#6366f1' : 'white',
                    color: msg.sender === 'user' ? 'white' : '#1f2937',
                    boxShadow: msg.sender === 'admin' ? '0 2px 8px rgba(0,0,0,0.08)' : 'none'
                  }}>
                    {msg.sender === 'admin' && (
                      <p style={{ fontSize: '11px', color: '#6366f1', fontWeight: '600', margin: '0 0 4px 0' }}>
                        {msg.admin_name || 'Soporte'}
                      </p>
                    )}
                    {msg.message && (
                      <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>
                        {msg.message}
                      </p>
                    )}
                    {msg.image && (
                      <img src={rutaDeArchivo(msg.image)} alt="adjunto" onClick={() => abrirArchivo(msg.image)} style={{ marginTop: msg.message ? '8px' : 0, maxWidth: '200px', maxHeight: '200px', borderRadius: '10px', display: 'block', cursor: 'pointer' }} />
                    )}
                  </div>
                  <p style={{
                    fontSize: '10px',
                    color: '#9ca3af',
                    margin: '4px 8px 0',
                    textAlign: msg.sender === 'user' ? 'right' : 'left'
                  }}>
                    {new Date(msg.created_at).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

                    {conv?.status === 'closed' && (conv?.rated || ratingDone) && (
            <div style={{ padding: '12px 16px', borderTop: '1px solid #e5e7eb', backgroundColor: '#f0fdf4', textAlign: 'center', fontSize: '13px', color: '#15803d', fontWeight: 600 }}>
              ✓ ¡Gracias por tu calificación!
            </div>
          )}
          {conv?.status === 'closed' && !conv?.rated && !ratingDone && (
            <div style={{ padding: '14px 16px', borderTop: '1px solid #e5e7eb', backgroundColor: '#fafafa' }}>
              <p style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 600, color: '#1f2937', textAlign: 'center' }}>
                ¿Cómo fue tu atención{conv?.assigned_to_name ? ` con ${conv.assigned_to_name}` : ''}?
              </p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '6px', marginBottom: '10px' }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} onClick={() => setRatingStars(n)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '28px', lineHeight: 1, color: n <= ratingStars ? '#f59e0b' : '#d1d5db' }}>★</button>
                ))}
              </div>
              <textarea value={ratingComment} onChange={(e) => setRatingComment(e.target.value)} placeholder="Comentario (opcional)" rows={2} style={{ width: '100%', padding: '8px 10px', borderRadius: '10px', border: '1px solid #e5e7eb', fontSize: '13px', resize: 'none', outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit', marginBottom: '8px' }} />
              <button onClick={submitRating} disabled={ratingStars < 1 || submittingRating} style={{ width: '100%', padding: '10px', borderRadius: '10px', border: 'none', backgroundColor: ratingStars >= 1 ? '#6366f1' : '#e5e7eb', color: '#fff', fontSize: '14px', fontWeight: 600, cursor: ratingStars >= 1 ? 'pointer' : 'default' }}>
                Enviar calificación
              </button>
            </div>
          )}
          {/* Input */}
          <div style={{
            padding: '12px 16px',
            borderTop: '1px solid #e5e7eb',
            backgroundColor: 'white',
            display: 'flex',
            gap: '8px',
            alignItems: 'flex-end'
          }}>
            <textarea
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Escribe tu mensaje..."
              rows={1}
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '24px',
                border: '1px solid #e5e7eb',
                fontSize: '14px',
                resize: 'none',
                outline: 'none',
                maxHeight: '100px',
                fontFamily: 'inherit'
              }}
              data-testid="support-chat-input"
            />
            <button
              onClick={handleSend}
              disabled={!newMessage.trim() || sending}
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                backgroundColor: newMessage.trim() ? '#6366f1' : '#e5e7eb',
                border: 'none',
                color: 'white',
                cursor: newMessage.trim() ? 'pointer' : 'default',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background-color 0.2s'
              }}
              data-testid="support-chat-send"
            >
              <Send style={{ width: '18px', height: '18px' }} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
