import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ArrowLeft, Send, Bot, User, Clock, HelpCircle, Headphones } from 'lucide-react';
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
      const response = await api.post('/support/message', {
        message: newMessage.trim()
      }).catch(() => null);

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
    { text: '¿Cómo recargo mi saldo?', icon: '💳' },
    { text: '¿Cuánto tarda un envío?', icon: '⏱️' },
    { text: '¿Cómo verifico mi cuenta?', icon: '✅' },
    { text: '¿Cuáles son las tasas?', icon: '📊' }
  ];

  const handleQuickQuestion = (question) => {
    setNewMessage(question);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col" data-testid="support-page">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-lg mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate(-1)} 
              className="p-2 hover:bg-gray-100 rounded-xl transition-colors"
              data-testid="back-button"
            >
              <ArrowLeft className="w-5 h-5 text-gray-600" />
            </button>
            <div className="flex items-center gap-3 flex-1">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center shadow-md">
                <Headphones className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="font-bold text-gray-900 text-lg">Soporte RIS</h1>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                  <span className="text-xs text-green-600 font-medium">En línea</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto bg-gradient-to-b from-gray-50 to-white">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.type === 'bot' && (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center mr-3 flex-shrink-0 shadow-sm">
                  <Bot className="w-5 h-5 text-white" />
                </div>
              )}
              
              <div className={`max-w-[75%]`}>
                <div
                  className={`px-5 py-4 ${
                    msg.type === 'user'
                      ? 'bg-orange-500 text-white rounded-2xl rounded-br-md shadow-sm'
                      : 'bg-white text-gray-800 rounded-2xl rounded-bl-md shadow-sm border border-gray-100'
                  }`}
                >
                  <p className="text-sm leading-relaxed">{msg.text}</p>
                </div>
                <p className={`text-xs text-gray-400 mt-1.5 ${msg.type === 'user' ? 'text-right' : 'text-left'}`}>
                  {msg.time}
                </p>
              </div>
              
              {msg.type === 'user' && (
                <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center ml-3 flex-shrink-0">
                  <span className="text-gray-600 font-semibold text-sm">{user?.name?.charAt(0)?.toUpperCase() || 'U'}</span>
                </div>
              )}
            </div>
          ))}
          
          {loading && (
            <div className="flex justify-start">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center mr-3 shadow-sm">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div className="bg-white px-5 py-4 rounded-2xl rounded-bl-md shadow-sm border border-gray-100">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce"></div>
                  <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }}></div>
                  <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }}></div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick Questions */}
      {messages.length <= 2 && (
        <div className="bg-white border-t border-gray-100 px-4 py-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center gap-2 mb-3">
              <HelpCircle className="w-4 h-4 text-gray-400" />
              <p className="text-xs text-gray-500 font-medium">Preguntas frecuentes</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {quickQuestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleQuickQuestion(q.text)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-gray-100 hover:bg-orange-50 hover:text-orange-600 text-gray-700 text-sm rounded-full transition-all border border-transparent hover:border-orange-200"
                  data-testid={`quick-question-${i}`}
                >
                  <span>{q.icon}</span>
                  <span className="font-medium">{q.text}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <form onSubmit={handleSendMessage} className="max-w-3xl mx-auto">
          <div className="flex gap-3">
            <input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Escribe tu mensaje..."
              className="flex-1 px-5 py-4 rounded-2xl border border-gray-200 focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all text-gray-700"
              disabled={loading}
              data-testid="message-input"
            />
            <button
              type="submit"
              disabled={loading || !newMessage.trim()}
              className="px-5 py-4 bg-orange-500 hover:bg-orange-600 text-white rounded-2xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
              data-testid="send-message"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
