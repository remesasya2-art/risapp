import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * ErrorBoundary.jsx — Que un error de render no se lleve puesta la página.
 *
 * POR QUE EXISTE
 *   La app no tenía ninguno. En React, una excepción durante el render desmonta
 *   el árbol entero: el usuario no ve un error, ve una PÁGINA EN BLANCO. Pasó
 *   de verdad en el Libro Mayor —una sección leía un campo que la respuesta no
 *   traía— y desde afuera era indistinguible de «la app se rompió».
 *
 *   Una pantalla en blanco es el peor error posible: no dice qué pasó, no deja
 *   seguir trabajando, y no hay forma de reportarlo más que «se puso en blanco».
 *
 * QUE HACE
 *   Aísla el fallo a la sección que lo produjo. El resto de la pantalla —los
 *   botones, el menú, las otras vistas— sigue funcionando, y el que lo ve tiene
 *   un texto que puede copiar y pasar.
 *
 * QUE NO HACE
 *   No reintenta solo ni esconde el error. Un error que se traga en silencio es
 *   un error que nadie arregla.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Queda en la consola con el árbol de componentes: es lo único que permite
    // encontrar la línea exacta cuando alguien reporta «se puso en blanco».
    console.error('[ErrorBoundary]', this.props.donde || '', error, info?.componentStack);
  }

  componentDidUpdate(prevProps) {
    // Al cambiar de sección se limpia el error: si el problema era de esa vista,
    // las demás tienen que poder abrirse.
    if (this.state.error && prevProps.clave !== this.props.clave) {
      this.setState({ error: null });
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div style={{
        border: '1px solid #fecaca', backgroundColor: '#fef2f2',
        borderRadius: '12px', padding: '16px', color: '#7f1d1d',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          fontWeight: 700, fontSize: '14px', marginBottom: '6px',
        }}>
          <AlertTriangle size={16} />
          No se pudo dibujar esta sección
        </div>
        <p style={{ margin: '0 0 8px 0', fontSize: '13px', lineHeight: 1.6 }}>
          El resto de la pantalla sigue funcionando: probá otra sección. Si esto
          se repite, pasá el texto de abajo — dice exactamente qué falló.
        </p>
        <pre style={{
          margin: 0, padding: '10px', borderRadius: '8px',
          backgroundColor: '#fff', border: '1px solid #fecaca',
          fontSize: '11.5px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          fontFamily: 'ui-monospace, monospace',
        }}>
          {this.props.donde ? `${this.props.donde}: ` : ''}
          {String(error?.message || error)}
        </pre>
      </div>
    );
  }
}

export default ErrorBoundary;
