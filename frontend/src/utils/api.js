import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('session_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // UN 401 SOLO SACA AL LOGIN A QUIEN TENIA SESION.
    //
    //   Antes echaba a cualquiera, y el login con la clave mala contesta
    //   justamente 401 («Credenciales inválidas»): la página se recargaba
    //   en el acto y el aviso no llegaba a verse. Quien se equivocaba de
    //   clave veía la pantalla parpadear y nada más, sin saber qué pasó.
    //
    //   Sin sesión no hay nada que cerrar ni adónde volver: el error sigue
    //   su camino y la pantalla que hizo el pedido lo muestra.
    if (error.response?.status === 401) {
      const teniaSesion = localStorage.getItem('has_session');
      localStorage.removeItem('has_session');
      localStorage.removeItem('last_activity');
      if (teniaSesion) window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
