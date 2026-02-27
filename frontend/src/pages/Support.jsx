import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ArrowLeft, Send, Bot, User, Clock } from 'lucide-react';
import api from '../utils/api';
import toast from 'react-hot-toast';

export default function Support() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [tickets, setTickets] = useState([]);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadTickets();
    // Add initial bot message
    setMessages([
      {
        id: 1,
        type: 'bot',
        text: `¡Hola ${user?.name?.split(' ')[0] || 'Usuario'}! 👋 Bienvenido al soporte de RIS. ¿En qué puedo ayudarte hoy?`,
        time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
      }
    ]);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadTickets = async () => {
    try {
      const response = await api.get('/support/tickets').catch(() => ({ data: [] }));
      setTickets(response.data || []);
    } catch (error) {
      console.error('Error loading tickets:', error);
    }
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
    setNewMessage('');
    setLoading(true);

    try {
      // Send to backend
      const response = await api.post('/support/message', {
        message: newMessage.trim()
      }).catch(() => null);

      // Add bot response
      setTimeout(() => {
        const botResponse = {
          id: Date.now() + 1,
          type: 'bot',
          text: response?.data?.reply || 'Tu mensaje ha sido recibido. Un agente de soporte te responderá pronto. También puedes revisar nuestras preguntas frecuentes mientras esperas.',
          time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
        };
        setMessages(prev => [...prev, botResponse]);
        setLoading(false);
      }, 1000);
    } catch (error) {
      toast.error('Error al enviar mensaje');
      setLoading(false);
    }
  };

  const quickQuestions = [
    '¿Cómo recargo mi saldo?',
    '¿Cuánto tarda un envío?',
    '¿Cómo verifico mi cuenta?',
    '¿Cuáles son las tasas?'
  ];

  const handleQuickQuestion = (question) => {
    setNewMessage(question);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-gray-100 rounded-lg">
              <ArrowLeft className="w-5 h-5 text-gray-600" />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
                <Bot className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <h1 className="font-bold text-gray-900">Soporte RIS</h1>
                <p className="text-xs text-green-600 flex items-center gap-1">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  En línea
                </p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[80%] ${msg.type === 'user' ? 'order-1' : 'order-2'}`}>
                <div
                  className={`px-4 py-3 rounded-2xl ${
                    msg.type === 'user'
                      ? 'bg-orange-500 text-white rounded-br-md'
                      : 'bg-white text-gray-800 rounded-bl-md shadow-sm border border-gray-100'
                  }`}
                >
                  <p className="text-sm">{msg.text}</p>
                </div>
                <p className={`text-xs text-gray-400 mt-1 ${msg.type === 'user' ? 'text-right' : 'text-left'}`}>
                  {msg.time}
                </p>
              </div>
              {msg.type === 'bot' && (
                <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center mr-2 flex-shrink-0 order-1">
                  <Bot className="w-4 h-4 text-orange-600" />
                </div>
              )}
            </div>
          ))}
          
          {loading && (
            <div className="flex justify-start">
              <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center mr-2">
                <Bot className="w-4 h-4 text-orange-600" />
              </div>
              <div className="bg-white px-4 py-3 rounded-2xl rounded-bl-md shadow-sm border border-gray-100">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick Questions */}
      {messages.length <= 2 && (
        <div className="bg-white border-t border-gray-200 px-4 py-3">
          <p className="text-xs text-gray-500 mb-2">Preguntas frecuentes:</p>
          <div className="flex flex-wrap gap-2">
            {quickQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => handleQuickQuestion(q)}
                className="px-3 py-1.5 bg-gray-100 hover:bg-orange-50 hover:text-orange-600 text-gray-700 text-sm rounded-full transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <form onSubmit={handleSendMessage} className="max-w-2xl mx-auto">
          <div className="flex gap-2">
            <input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Escribe tu mensaje..."
              className="flex-1 px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-orange-500 focus:border-transparent"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !newMessage.trim()}
              className="px-4 py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
