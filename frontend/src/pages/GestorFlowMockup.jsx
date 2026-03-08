import React, { useState } from 'react';
import { ArrowLeft, Calculator, QrCode, Copy, Clock, CheckCircle, CreditCard, Building2, User, Phone, FileText, ChevronRight, AlertCircle, Loader2 } from 'lucide-react';

// Mockup de todas las pantallas del flujo Gestor
export default function GestorFlowMockup() {
  const [currentStep, setCurrentStep] = useState(1);

  const steps = [
    { num: 1, title: 'Calculadora' },
    { num: 2, title: 'QR PIX' },
    { num: 3, title: 'Pago Exitoso' },
    { num: 4, title: 'Tipo Pago' },
    { num: 5, title: 'Beneficiario' },
    { num: 6, title: 'Confirmar' },
    { num: 7, title: 'Pendientes' },
  ];

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f3f4f6', padding: '20px' }}>
      {/* Step Navigator */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
        {steps.map((step) => (
          <button
            key={step.num}
            onClick={() => setCurrentStep(step.num)}
            style={{
              padding: '8px 16px',
              borderRadius: '20px',
              border: 'none',
              cursor: 'pointer',
              backgroundColor: currentStep === step.num ? '#7c3aed' : '#e5e7eb',
              color: currentStep === step.num ? 'white' : '#374151',
              fontWeight: '600',
              fontSize: '12px'
            }}
          >
            {step.num}. {step.title}
          </button>
        ))}
      </div>

      {/* Phone Frame */}
      <div style={{ 
        maxWidth: '400px', 
        margin: '0 auto', 
        backgroundColor: '#1f2937', 
        borderRadius: '40px', 
        padding: '12px',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)'
      }}>
        <div style={{ 
          backgroundColor: 'white', 
          borderRadius: '32px', 
          overflow: 'hidden',
          minHeight: '700px'
        }}>
          
          {/* PASO 1: Calculadora */}
          {currentStep === 1 && (
            <div style={{ padding: '0' }}>
              {/* Header */}
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <ArrowLeft style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Nuevo Envío</span>
                </div>
                <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>Ingresa el monto a enviar</p>
              </div>

              <div style={{ padding: '24px' }}>
                {/* Toggle RIS/VES */}
                <div style={{ 
                  display: 'flex', 
                  backgroundColor: '#f3f4f6', 
                  borderRadius: '12px', 
                  padding: '4px',
                  marginBottom: '24px'
                }}>
                  <button style={{ 
                    flex: 1, 
                    padding: '12px', 
                    borderRadius: '10px', 
                    border: 'none',
                    backgroundColor: '#7c3aed',
                    color: 'white',
                    fontWeight: '600'
                  }}>
                    RIS (Reales)
                  </button>
                  <button style={{ 
                    flex: 1, 
                    padding: '12px', 
                    borderRadius: '10px', 
                    border: 'none',
                    backgroundColor: 'transparent',
                    color: '#6b7280',
                    fontWeight: '600'
                  }}>
                    VES (Bolívares)
                  </button>
                </div>

                {/* Input Principal */}
                <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                  <div style={{ 
                    fontSize: '48px', 
                    fontWeight: '700', 
                    color: '#111827',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px'
                  }}>
                    <span style={{ color: '#7c3aed' }}>R$</span>
                    <span>150.00</span>
                  </div>
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    gap: '8px',
                    marginTop: '8px'
                  }}>
                    <Calculator style={{ width: '16px', height: '16px', color: '#9ca3af' }} />
                    <span style={{ color: '#6b7280', fontSize: '14px' }}>= 13,800.00 VES</span>
                  </div>
                  <p style={{ color: '#9ca3af', fontSize: '12px', marginTop: '8px' }}>
                    Tasa: 1 RIS = 92.00 VES
                  </p>
                </div>

                {/* Teclado numérico */}
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(3, 1fr)', 
                  gap: '12px',
                  marginBottom: '24px'
                }}>
                  {['1','2','3','4','5','6','7','8','9','.','0','⌫'].map((key) => (
                    <button key={key} style={{
                      padding: '20px',
                      fontSize: '24px',
                      fontWeight: '600',
                      borderRadius: '16px',
                      border: 'none',
                      backgroundColor: '#f3f4f6',
                      color: '#374151',
                      cursor: 'pointer'
                    }}>
                      {key}
                    </button>
                  ))}
                </div>

                {/* Botón Continuar */}
                <button style={{
                  width: '100%',
                  padding: '18px',
                  borderRadius: '16px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                  color: 'white',
                  fontSize: '16px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}>
                  Continuar
                  <ChevronRight style={{ width: '20px', height: '20px' }} />
                </button>
              </div>
            </div>
          )}

          {/* PASO 2: QR PIX */}
          {currentStep === 2 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <ArrowLeft style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Pago PIX</span>
                </div>
                <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>El tercero debe escanear el QR o copiar el código</p>
              </div>

              <div style={{ padding: '24px', textAlign: 'center' }}>
                {/* Timer */}
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: '#fef3c7',
                  color: '#d97706',
                  padding: '12px 20px',
                  borderRadius: '12px',
                  marginBottom: '24px'
                }}>
                  <Clock style={{ width: '20px', height: '20px' }} />
                  <span style={{ fontWeight: '600' }}>Expira en: 06:42</span>
                </div>

                {/* Monto */}
                <div style={{ marginBottom: '24px' }}>
                  <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 4px 0' }}>Monto a pagar</p>
                  <p style={{ fontSize: '32px', fontWeight: '700', color: '#111827', margin: 0 }}>
                    R$ 150.00
                  </p>
                </div>

                {/* QR Code */}
                <div style={{
                  backgroundColor: 'white',
                  padding: '20px',
                  borderRadius: '20px',
                  border: '2px solid #e5e7eb',
                  display: 'inline-block',
                  marginBottom: '24px'
                }}>
                  <div style={{
                    width: '200px',
                    height: '200px',
                    backgroundColor: '#f3f4f6',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <QrCode style={{ width: '150px', height: '150px', color: '#374151' }} />
                  </div>
                </div>

                {/* Código PIX */}
                <div style={{
                  backgroundColor: '#f3f4f6',
                  borderRadius: '12px',
                  padding: '16px',
                  marginBottom: '24px'
                }}>
                  <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 8px 0' }}>Código PIX Copia y Pega</p>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    backgroundColor: 'white',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid #e5e7eb'
                  }}>
                    <code style={{ 
                      flex: 1, 
                      fontSize: '11px', 
                      color: '#374151',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      00020126580014br.gov.bcb.pix...
                    </code>
                    <button style={{
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: '#7c3aed',
                      color: 'white',
                      fontWeight: '600',
                      fontSize: '12px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <Copy style={{ width: '14px', height: '14px' }} />
                      Copiar
                    </button>
                  </div>
                </div>

                {/* Status */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  color: '#6b7280'
                }}>
                  <Loader2 style={{ width: '20px', height: '20px', animation: 'spin 1s linear infinite' }} />
                  <span>Esperando pago...</span>
                </div>
              </div>
            </div>
          )}

          {/* PASO 3: Pago Exitoso */}
          {currentStep === 3 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <CheckCircle style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Pago Recibido</span>
                </div>
              </div>

              <div style={{ padding: '24px', textAlign: 'center' }}>
                {/* Success Icon */}
                <div style={{
                  width: '120px',
                  height: '120px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 24px'
                }}>
                  <CheckCircle style={{ width: '60px', height: '60px', color: '#16a34a' }} />
                </div>

                <h2 style={{ fontSize: '24px', fontWeight: '700', color: '#16a34a', margin: '0 0 8px 0' }}>
                  ¡Pago Realizado con Éxito!
                </h2>
                <p style={{ color: '#6b7280', margin: '0 0 32px 0' }}>
                  El pago PIX ha sido confirmado
                </p>

                {/* Saldo añadido */}
                <div style={{
                  backgroundColor: '#f0fdf4',
                  borderRadius: '16px',
                  padding: '20px',
                  marginBottom: '24px',
                  border: '2px solid #bbf7d0'
                }}>
                  <p style={{ color: '#16a34a', fontSize: '14px', margin: '0 0 8px 0', fontWeight: '600' }}>
                    Añadido a Saldo Terceros
                  </p>
                  <p style={{ fontSize: '36px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                    +R$ 150.00
                  </p>
                </div>

                {/* Nuevo saldo */}
                <div style={{
                  backgroundColor: '#f3f4f6',
                  borderRadius: '12px',
                  padding: '16px',
                  marginBottom: '32px'
                }}>
                  <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 4px 0' }}>
                    Saldo Terceros Disponible
                  </p>
                  <p style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>
                    R$ 650.00
                  </p>
                </div>

                <button style={{
                  width: '100%',
                  padding: '18px',
                  borderRadius: '16px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
                  color: 'white',
                  fontSize: '16px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}>
                  Continuar con el Envío
                  <ChevronRight style={{ width: '20px', height: '20px' }} />
                </button>
              </div>
            </div>
          )}

          {/* PASO 4: Tipo de Pago */}
          {currentStep === 4 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <ArrowLeft style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Tipo de Pago</span>
                </div>
                <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>¿Cómo desea recibir el beneficiario?</p>
              </div>

              <div style={{ padding: '24px' }}>
                {/* Monto a enviar */}
                <div style={{
                  backgroundColor: '#f3f4f6',
                  borderRadius: '12px',
                  padding: '16px',
                  marginBottom: '24px',
                  textAlign: 'center'
                }}>
                  <p style={{ color: '#6b7280', fontSize: '12px', margin: '0 0 4px 0' }}>Monto a enviar</p>
                  <p style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>
                    13,800.00 VES
                  </p>
                </div>

                {/* Opciones */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Pago Móvil */}
                  <button style={{
                    padding: '20px',
                    borderRadius: '16px',
                    border: '3px solid #7c3aed',
                    backgroundColor: '#faf5ff',
                    cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px'
                  }}>
                    <div style={{
                      width: '56px',
                      height: '56px',
                      borderRadius: '14px',
                      backgroundColor: '#7c3aed',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      <Phone style={{ width: '28px', height: '28px', color: 'white' }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>
                        Pago Móvil
                      </p>
                      <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
                        Teléfono, banco y cédula
                      </p>
                    </div>
                    <div style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      border: '2px solid #7c3aed',
                      backgroundColor: '#7c3aed',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      <CheckCircle style={{ width: '16px', height: '16px', color: 'white' }} />
                    </div>
                  </button>

                  {/* Transferencia */}
                  <button style={{
                    padding: '20px',
                    borderRadius: '16px',
                    border: '2px solid #e5e7eb',
                    backgroundColor: 'white',
                    cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px'
                  }}>
                    <div style={{
                      width: '56px',
                      height: '56px',
                      borderRadius: '14px',
                      backgroundColor: '#f3f4f6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      <Building2 style={{ width: '28px', height: '28px', color: '#6b7280' }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>
                        Transferencia
                      </p>
                      <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
                        Cuenta bancaria (20 dígitos)
                      </p>
                    </div>
                    <div style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      border: '2px solid #d1d5db'
                    }} />
                  </button>
                </div>

                <button style={{
                  width: '100%',
                  padding: '18px',
                  borderRadius: '16px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                  color: 'white',
                  fontSize: '16px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  marginTop: '32px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}>
                  Continuar
                  <ChevronRight style={{ width: '20px', height: '20px' }} />
                </button>
              </div>
            </div>
          )}

          {/* PASO 5: Datos Beneficiario */}
          {currentStep === 5 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <ArrowLeft style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Datos del Beneficiario</span>
                </div>
                <div style={{ 
                  display: 'inline-flex', 
                  alignItems: 'center', 
                  gap: '6px',
                  backgroundColor: 'rgba(255,255,255,0.2)',
                  padding: '6px 12px',
                  borderRadius: '20px',
                  fontSize: '12px'
                }}>
                  <Phone style={{ width: '14px', height: '14px' }} />
                  Pago Móvil
                </div>
              </div>

              <div style={{ padding: '24px' }}>
                {/* Beneficiarios guardados */}
                <div style={{
                  backgroundColor: '#f0fdf4',
                  borderRadius: '12px',
                  padding: '14px',
                  marginBottom: '20px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  border: '1px solid #bbf7d0'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <User style={{ width: '18px', height: '18px', color: '#16a34a' }} />
                    <span style={{ fontSize: '14px', color: '#16a34a', fontWeight: '600' }}>
                      3 beneficiarios guardados
                    </span>
                  </div>
                  <ChevronRight style={{ width: '18px', height: '18px', color: '#16a34a' }} />
                </div>

                {/* Formulario */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                      Nombre Completo
                    </label>
                    <input 
                      type="text"
                      placeholder="Juan Pérez"
                      value="María García"
                      style={{
                        width: '100%',
                        padding: '14px',
                        borderRadius: '12px',
                        border: '2px solid #e5e7eb',
                        fontSize: '15px',
                        boxSizing: 'border-box'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                      Cédula
                    </label>
                    <input 
                      type="text"
                      placeholder="V-12345678"
                      value="V-25789456"
                      style={{
                        width: '100%',
                        padding: '14px',
                        borderRadius: '12px',
                        border: '2px solid #e5e7eb',
                        fontSize: '15px',
                        boxSizing: 'border-box'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                      Banco
                    </label>
                    <select style={{
                      width: '100%',
                      padding: '14px',
                      borderRadius: '12px',
                      border: '2px solid #e5e7eb',
                      fontSize: '15px',
                      backgroundColor: 'white',
                      boxSizing: 'border-box'
                    }}>
                      <option>0102 - Banco de Venezuela</option>
                    </select>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '6px' }}>
                      Teléfono
                    </label>
                    <input 
                      type="text"
                      placeholder="04141234567"
                      value="04141234567"
                      style={{
                        width: '100%',
                        padding: '14px',
                        borderRadius: '12px',
                        border: '2px solid #e5e7eb',
                        fontSize: '15px',
                        boxSizing: 'border-box'
                      }}
                    />
                  </div>

                  {/* Guardar checkbox */}
                  <label style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '14px',
                    backgroundColor: '#f3f4f6',
                    borderRadius: '12px',
                    cursor: 'pointer'
                  }}>
                    <input type="checkbox" style={{ width: '20px', height: '20px' }} />
                    <span style={{ fontSize: '14px', color: '#374151' }}>
                      Guardar para futuros envíos
                    </span>
                  </label>
                </div>

                <button style={{
                  width: '100%',
                  padding: '18px',
                  borderRadius: '16px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                  color: 'white',
                  fontSize: '16px',
                  fontWeight: '700',
                  cursor: 'pointer',
                  marginTop: '24px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}>
                  Continuar
                  <ChevronRight style={{ width: '20px', height: '20px' }} />
                </button>
              </div>
            </div>
          )}

          {/* PASO 6: Confirmación */}
          {currentStep === 6 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <ArrowLeft style={{ width: '24px', height: '24px' }} />
                  <span style={{ fontSize: '18px', fontWeight: '600' }}>Confirmar Envío</span>
                </div>
                <p style={{ fontSize: '14px', opacity: 0.9, margin: 0 }}>Verifica los datos antes de confirmar</p>
              </div>

              <div style={{ padding: '24px' }}>
                {/* Monto */}
                <div style={{
                  background: 'linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%)',
                  borderRadius: '16px',
                  padding: '20px',
                  textAlign: 'center',
                  marginBottom: '20px',
                  border: '2px solid #e9d5ff'
                }}>
                  <p style={{ color: '#7c3aed', fontSize: '14px', margin: '0 0 4px 0', fontWeight: '600' }}>
                    Monto a Enviar
                  </p>
                  <p style={{ fontSize: '32px', fontWeight: '700', color: '#7c3aed', margin: 0 }}>
                    13,800.00 VES
                  </p>
                  <p style={{ color: '#9ca3af', fontSize: '12px', margin: '4px 0 0 0' }}>
                    R$ 150.00 × 92.00
                  </p>
                </div>

                {/* Datos */}
                <div style={{
                  backgroundColor: '#f9fafb',
                  borderRadius: '16px',
                  padding: '16px',
                  marginBottom: '20px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                    <Phone style={{ width: '18px', height: '18px', color: '#7c3aed' }} />
                    <span style={{ fontSize: '14px', fontWeight: '600', color: '#7c3aed' }}>Pago Móvil</span>
                  </div>

                  {[
                    { label: 'Beneficiario', value: 'María García' },
                    { label: 'Cédula', value: 'V-25789456' },
                    { label: 'Banco', value: '0102 - Banco de Venezuela' },
                    { label: 'Teléfono', value: '04141234567' },
                  ].map((item, i) => (
                    <div key={i} style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '12px 0',
                      borderBottom: i < 3 ? '1px solid #e5e7eb' : 'none'
                    }}>
                      <span style={{ color: '#6b7280', fontSize: '14px' }}>{item.label}</span>
                      <span style={{ color: '#111827', fontSize: '14px', fontWeight: '600' }}>{item.value}</span>
                    </div>
                  ))}
                </div>

                {/* Saldo */}
                <div style={{
                  backgroundColor: '#f0fdf4',
                  borderRadius: '12px',
                  padding: '14px',
                  marginBottom: '24px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <span style={{ color: '#16a34a', fontSize: '14px' }}>Se descontará de Saldo Terceros</span>
                  <span style={{ color: '#16a34a', fontSize: '16px', fontWeight: '700' }}>R$ 150.00</span>
                </div>

                {/* Botones */}
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button style={{
                    flex: 1,
                    padding: '16px',
                    borderRadius: '14px',
                    border: '2px solid #e5e7eb',
                    backgroundColor: 'white',
                    color: '#374151',
                    fontSize: '15px',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}>
                    ← Editar
                  </button>
                  <button style={{
                    flex: 2,
                    padding: '16px',
                    borderRadius: '14px',
                    border: 'none',
                    background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
                    color: 'white',
                    fontSize: '15px',
                    fontWeight: '700',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px'
                  }}>
                    <CheckCircle style={{ width: '20px', height: '20px' }} />
                    Confirmar
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* PASO 7: Pagos Pendientes */}
          {currentStep === 7 && (
            <div style={{ padding: '0' }}>
              <div style={{ 
                background: 'linear-gradient(135deg, #7c3aed 0%, #6366f1 100%)',
                padding: '20px',
                color: 'white'
              }}>
                <span style={{ fontSize: '18px', fontWeight: '600' }}>Mis Pagos Pendientes</span>
                <p style={{ fontSize: '14px', opacity: 0.9, margin: '8px 0 0 0' }}>
                  Transacciones en proceso
                </p>
              </div>

              <div style={{ padding: '16px' }}>
                {/* Pending item 1 */}
                <div style={{
                  backgroundColor: 'white',
                  borderRadius: '16px',
                  padding: '16px',
                  marginBottom: '12px',
                  border: '2px solid #fef3c7',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                    <div>
                      <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        María García
                      </p>
                      <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                        Pago Móvil • 0102
                      </p>
                    </div>
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: '20px',
                      backgroundColor: '#fef3c7',
                      color: '#d97706',
                      fontSize: '11px',
                      fontWeight: '600'
                    }}>
                      ⏳ Pendiente
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
                      13,800.00 VES
                    </span>
                    <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                      Hace 5 min
                    </span>
                  </div>
                </div>

                {/* Pending item 2 */}
                <div style={{
                  backgroundColor: 'white',
                  borderRadius: '16px',
                  padding: '16px',
                  marginBottom: '12px',
                  border: '2px solid #fef3c7',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                    <div>
                      <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        Carlos Rodríguez
                      </p>
                      <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                        Transferencia • Banesco
                      </p>
                    </div>
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: '20px',
                      backgroundColor: '#dbeafe',
                      color: '#2563eb',
                      fontSize: '11px',
                      fontWeight: '600'
                    }}>
                      🔄 Procesando
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
                      25,000.00 VES
                    </span>
                    <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                      Hace 15 min
                    </span>
                  </div>
                </div>

                {/* Completed item */}
                <div style={{
                  backgroundColor: 'white',
                  borderRadius: '16px',
                  padding: '16px',
                  border: '2px solid #dcfce7',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                    <div>
                      <p style={{ fontSize: '16px', fontWeight: '700', color: '#111827', margin: 0 }}>
                        Ana Martínez
                      </p>
                      <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>
                        Pago Móvil • 0134
                      </p>
                    </div>
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: '20px',
                      backgroundColor: '#dcfce7',
                      color: '#16a34a',
                      fontSize: '11px',
                      fontWeight: '600'
                    }}>
                      ✅ Completado
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '20px', fontWeight: '700', color: '#111827' }}>
                      8,500.00 VES
                    </span>
                    <span style={{ fontSize: '12px', color: '#9ca3af' }}>
                      Hace 1 hora
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
