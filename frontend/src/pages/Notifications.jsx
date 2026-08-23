import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCheck, X, ExternalLink } from 'lucide-react';
import api from '../utils/api';
import { fmt } from '../utils/format';

export default function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedNotification, setSelectedNotification] = useState(null);

  useEffect(() => {
    loadNotifications();
  }, []);

  const loadNotifications = async () => {
    try {
      const response = await api.get('/notifications');
      // Handle both { notifications: [...] } and direct array response
      const data = response.data;
      setNotifications(Array.isArray(data) ? data : (data.notifications || []));
    } catch (error) {
      console.error('Error loading notifications:', error);
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  const openNotification = async (notification) => {
    setSelectedNotification(notification);
    
    // Mark as read when opening
    if (!notification.read) {
      try {
        await api.post(`/notifications/${notification.notification_id}/read`);
        setNotifications(notifications.map(n => 
          n.notification_id === notification.notification_id ? { ...n, read: true } : n
        ));
      } catch (error) {
        console.error('Error marking notification as read:', error);
      }
    }
  };

  const closeNotification = () => {
    setSelectedNotification(null);
  };

  const markAllAsRead = async () => {
    try {
      await api.post('/notifications/mark-all-read');
      setNotifications(notifications.map(n => ({ ...n, read: true })));
    } catch (error) {
      console.error('Error marking all as read:', error);
    }
  };

  const formatTime = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Ahora';
    if (minutes < 60) return `Hace ${minutes} min`;
    if (hours < 24) return `Hace ${hours}h`;
    if (days < 7) return `Hace ${days}d`;
    return date.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
  };

  const formatFullDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-ES', { 
      weekday: 'long',
      day: '2-digit', 
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'transaction': return '💰';
      case 'recharge': return '💳';
      case 'withdrawal': return '📤';
      case 'kyc': return '✅';
      case 'password_reset': return '🔐';
      case 'support': return '💬';
      case 'rate_change': return '📊';
      default: return '🔔';
    }
  };

  const getNotificationAction = (notification) => {
    switch (notification.type) {
      case 'transaction':
      case 'recharge':
      case 'withdrawal':
        return { label: 'Ver historial', path: '/history' };
      case 'kyc':
        return { label: 'Ver perfil', path: '/profile' };
      case 'support':
        return { label: 'Ir a soporte', path: '/support' };
      default:
        return null;
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;

  const pageStyle = {
    minHeight: '100vh',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    border: '1px solid #e5e7eb'
  };

  return (
    <div style={pageStyle} data-testid="notifications-page">
      <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button 
              onClick={() => navigate('/')} 
              style={{ 
                width: '40px', height: '40px', borderRadius: '12px', border: 'none', 
                backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', 
                display: 'flex', alignItems: 'center', justifyContent: 'center' 
              }}
              data-testid="back-button"
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Notificaciones</h1>
              {unreadCount > 0 && (
                <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{unreadCount} sin leer</p>
              )}
            </div>
          </div>
          {unreadCount > 0 && (
            <button
              onClick={markAllAsRead}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 16px',
                backgroundColor: '#dbeafe', color: '#2563eb', border: 'none',
                borderRadius: '12px', fontSize: '14px', fontWeight: '500', cursor: 'pointer'
              }}
              data-testid="mark-all-read"
            >
              <CheckCheck style={{ width: '16px', height: '16px' }} />
              Marcar todas
            </button>
          )}
        </div>

        {/* Content */}
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px' }}>
            <div style={{ 
              width: '32px', height: '32px', borderRadius: '50%', 
              border: '3px solid #e5e7eb', borderTopColor: '#6366f1',
              animation: 'spin 1s linear infinite'
            }} />
          </div>
        ) : notifications.length === 0 ? (
          <div style={{ ...cardStyle, padding: '48px', textAlign: 'center' }}>
            <div style={{ 
              width: '64px', height: '64px', borderRadius: '50%', 
              backgroundColor: '#f3f4f6', margin: '0 auto 16px',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Bell style={{ width: '32px', height: '32px', color: '#9ca3af' }} />
            </div>
            <p style={{ color: '#6b7280', fontSize: '16px', margin: 0 }}>No tienes notificaciones</p>
          </div>
        ) : (
          <div style={{ ...cardStyle, overflow: 'hidden' }}>
            {notifications.map((notification, index) => (
              <div
                key={notification.notification_id}
                onClick={() => openNotification(notification)}
                style={{
                  padding: '16px 20px',
                  cursor: 'pointer',
                  backgroundColor: notification.read ? '#ffffff' : '#eff6ff',
                  borderBottom: index < notifications.length - 1 ? '1px solid #e5e7eb' : 'none',
                  transition: 'background-color 0.2s'
                }}
                data-testid={`notification-${notification.notification_id}`}
              >
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: '24px' }}>{getNotificationIcon(notification.type)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                      <p style={{ 
                        fontWeight: notification.read ? '500' : '600', 
                        color: notification.read ? '#6b7280' : '#111827',
                        margin: 0, fontSize: '15px'
                      }}>
                        {notification.title}
                      </p>
                      <span style={{ fontSize: '12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
                        {formatTime(notification.created_at)}
                      </span>
                    </div>
                    <p style={{ 
                      fontSize: '14px', color: notification.read ? '#9ca3af' : '#6b7280',
                      margin: '4px 0 0 0', lineHeight: '1.4',
                      overflow: 'hidden', textOverflow: 'ellipsis', 
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
                    }}>
                      {notification.message}
                    </p>
                  </div>
                  {!notification.read && (
                    <div style={{ 
                      width: '8px', height: '8px', borderRadius: '50%', 
                      backgroundColor: '#6366f1', flexShrink: 0, marginTop: '6px'
                    }} />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Notification Detail Modal */}
      {selectedNotification && (
        <div 
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', padding: '20px',
            zIndex: 1000
          }}
          onClick={closeNotification}
          data-testid="notification-modal-overlay"
        >
          <div 
            style={{
              backgroundColor: '#ffffff', borderRadius: '20px', width: '100%',
              maxWidth: '480px', maxHeight: '80vh', overflow: 'hidden',
              boxShadow: '0 20px 50px rgba(0,0,0,0.2)'
            }}
            onClick={(e) => e.stopPropagation()}
            data-testid="notification-modal"
          >
            {/* Modal Header */}
            <div style={{ 
              padding: '20px', borderBottom: '1px solid #e5e7eb',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ fontSize: '32px' }}>{getNotificationIcon(selectedNotification.type)}</div>
                <div>
                  <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111827', margin: 0 }}>
                    {selectedNotification.title}
                  </h3>
                  <p style={{ fontSize: '12px', color: '#9ca3af', margin: '4px 0 0 0' }}>
                    {formatFullDate(selectedNotification.created_at)}
                  </p>
                </div>
              </div>
              <button
                onClick={closeNotification}
                style={{
                  width: '36px', height: '36px', borderRadius: '50%',
                  border: 'none', backgroundColor: '#f3f4f6', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}
                data-testid="close-notification-modal"
              >
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: '20px', overflowY: 'auto', maxHeight: 'calc(80vh - 160px)' }}>
              <p style={{ fontSize: '15px', color: '#374151', lineHeight: '1.6', margin: 0, whiteSpace: 'pre-wrap' }}>
                {selectedNotification.message}
              </p>
              
              {selectedNotification.data && Object.keys(selectedNotification.data).length > 0 && (
                <div style={{ marginTop: '16px', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '12px' }}>
                  <p style={{ fontSize: '12px', fontWeight: '600', color: '#6b7280', margin: '0 0 8px 0' }}>Detalles:</p>
                  {selectedNotification.data.amount && (
                    <p style={{ fontSize: '14px', color: '#111827', margin: '4px 0' }}>
                      Monto: <strong>RI$ {fmt(parseFloat(selectedNotification.data.amount))}</strong>
                    </p>
                  )}
                  {selectedNotification.data.transaction_id && (
                    <p style={{ fontSize: '14px', color: '#111827', margin: '4px 0' }}>
                      ID: <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{selectedNotification.data.transaction_id}</span>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer with Action */}
            {getNotificationAction(selectedNotification) && (
              <div style={{ padding: '16px 20px', borderTop: '1px solid #e5e7eb' }}>
                <button
                  onClick={() => {
                    closeNotification();
                    navigate(getNotificationAction(selectedNotification).path);
                  }}
                  style={{
                    width: '100%', padding: '14px', backgroundColor: '#6366f1',
                    color: '#ffffff', border: 'none', borderRadius: '12px',
                    fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                  }}
                  data-testid="notification-action-btn"
                >
                  <ExternalLink style={{ width: '18px', height: '18px' }} />
                  {getNotificationAction(selectedNotification).label}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
