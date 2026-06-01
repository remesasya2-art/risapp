import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../utils/api';

export default function DriveCallback() {
  const [status, setStatus] = useState('Conectando Google Drive...');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const code = searchParams.get('code');
    if (code) {
      api.post('/oauth/drive/exchange-code', { code })
        .then(res => {
          setStatus('Google Drive conectado exitosamente!');
          setTimeout(() => navigate('/admin?drive_connected=true'), 1500);
        })
        .catch(err => {
          setStatus('Error al conectar: ' + (err.response?.data?.detail || err.message));
          setTimeout(() => navigate('/admin?drive_error=true'), 3000);
        });
    } else {
      setStatus('No se recibió código de autorización');
      setTimeout(() => navigate('/admin'), 2000);
    }
  }, []);

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', backgroundColor: '#f9fafb' }}>
      <div style={{ textAlign: 'center', padding: '40px', backgroundColor: 'white', borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
        <div style={{ width: '48px', height: '48px', border: '4px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 16px' }} />
        <p style={{ fontSize: '16px', color: '#374151', fontWeight: '500' }}>{status}</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
