import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import api from '../utils/api';

export default function NotificationBell() {
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    loadUnreadCount();
    // Poll for new notifications every 30 seconds
    const interval = setInterval(loadUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadUnreadCount = async () => {
    try {
      const response = await api.get('/notifications/unread-count');
      // Backend returns unread_count, not count
      setUnreadCount(response.data.unread_count || response.data.count || 0);
    } catch (error) {
      console.error('Error loading notification count:', error);
    }
  };

  return (
    <button
      onClick={() => navigate('/notifications')}
      style={{
        position: 'relative',
        width: '44px',
        height: '44px',
        borderRadius: '12px',
        border: 'none',
        backgroundColor: '#f3f4f6',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s'
      }}
      data-testid="notification-bell"
      title="Notificaciones"
    >
      <Bell style={{ width: '22px', height: '22px', color: '#374151' }} />
      {unreadCount > 0 && (
        <span
          style={{
            position: 'absolute',
            top: '6px',
            right: '6px',
            minWidth: '18px',
            height: '18px',
            borderRadius: '9999px',
            backgroundColor: '#ef4444',
            color: '#ffffff',
            fontSize: '11px',
            fontWeight: '700',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 4px',
            border: '2px solid #ffffff'
          }}
          data-testid="notification-count"
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  );
}
