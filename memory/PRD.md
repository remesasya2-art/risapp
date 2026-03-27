# RIS App - Product Requirements Document

## Overview
**Nombre:** RIS - Billetera Digital para Remesas
**Descripción:** Aplicación web de billetera digital para transferencias de dinero entre Brasil y Venezuela
**Idioma:** Español
**Dominio:** www.risappbr.com

## User Personas
- **Usuarios en Brasil:** Trabajadores brasileños o venezolanos en Brasil que envían dinero a Venezuela
- **Beneficiarios en Venezuela:** Familiares que reciben remesas
- **Socios (Referidores):** Usuarios que refieren nuevos clientes y ganan comisiones
- **Socios Gestores:** Agentes que procesan remesas de terceros
- **Administradores:** Personal de RIS que procesa transacciones y verifica usuarios

## Core Requirements

### Autenticación
- [x] Login con email/contraseña
- [x] Login con Google OAuth
- [x] Registro de nuevos usuarios con verificación por email (Resend)
- [x] Campo opcional de código de referido en registro
- [x] Sistema de roles (user, socio, socio_gestor, admin, super_admin)
- [x] Recuperación de contraseña via email
- [x] **Reseteo de contraseña por Admin** - SuperAdmin puede restablecer contraseña de usuarios
  - Genera contraseña temporal de 8 caracteres
  - Envía email con contraseña temporal
  - Usuario forzado a cambiar contraseña en siguiente login
  - Página /force-change-password para establecer nueva contraseña

### Dashboard
- [x] Balance total en RI$ (formato: RI$ 100.00)
- [x] Tasa de cambio actual (RIS/VES)
- [x] Resumen de ingresos/gastos (30 días)
- [x] Acceso rápido a Recargar y Enviar
- [x] Transacciones recientes

### Recargas
- [x] PIX (Brasil) - Pago instantáneo
- [x] Bolívares (Venezuela) - Transferencia bancaria con voucher
- [x] Generación de QR Code PIX
- [x] Subida de comprobante para VES
- [ ] Recarga con Bitcoin/Lightning (Blink) - Pendiente

### Envío de Remesas
- [x] Wizard de 3 pasos (monto → beneficiario → confirmación)
- [x] Gestión de beneficiarios guardados
- [x] Cálculo automático de conversión RIS → VES
- [x] Lista de bancos venezolanos
- [x] **Sistema FIFO de Retiros via WhatsApp** - Cola ordenada, un retiro activo a la vez
- [x] **Panel Web para procesar retiros** - Admin puede aprobar con comprobante directamente
- [x] Estadísticas de cola en tiempo real (pendientes, activo en WhatsApp, en cola)

### Historial
- [x] Lista de transacciones con filtros
- [x] Estados: Completado, Pendiente, Rechazado
- [x] Detalles de cada transacción

### Perfil
- [x] Información del usuario
- [x] Estado de verificación KYC
- [x] Cambio de contraseña
- [x] Notificaciones Push (activar/desactivar)
- [x] Acceso a Panel de Socio (si es socio)
- [x] Acceso a Panel Gestor (si es socio_gestor)
- [x] Cerrar sesión

### Sistema de Notificaciones
- [x] Notificaciones in-app con modal de detalle
- [x] Web Push Notifications (sonido, vibración)
- [x] Notificación por email al completar retiro VES
- [x] Marcar como leído al abrir notificación

### Sistema de Socios (Referidos)
- [x] Registro con código de referido opcional
- [x] URL con código pre-llenado: /register?ref=CODIGO
- [x] Panel de Socio con:
  - Link de referido compartible
  - Estadísticas (referidos, ganancias)
  - Lista de referidos
  - Historial de ganancias
- [x] Bonificación:
  - 5 RI$ cuando referido acumula 100 RI$ en recargas
  - 1% de cada recarga posterior del referido

### Sistema de Socios Gestores
- [x] Panel de Gestor con:
  - Saldo personal disponible
  - **Saldo de Terceros (balance_ris_terceros)** - Separado del saldo personal
  - Estadísticas de transacciones
  - Gestión de beneficiarios
  - Historial de transacciones
- [x] Agregar beneficiarios con dos tipos de pago:
  - **Pago Móvil**: Nombre, cédula, banco (código), teléfono
  - **Transferencia**: Nombre, cédula, banco, número de cuenta (20 dígitos)
- [x] **Recargar saldo de terceros** - Transferir desde saldo personal
- [x] Procesar transacciones de terceros (debita de balance_ris_terceros)
- [x] Flujo de transacción de 4 pasos: Monto → Tipo de Pago → Datos del Cliente → Confirmación
- [x] Comisión configurable por SuperAdmin
- [x] **NUEVO: Flujo PIX para Terceros (Implementado 2026-03-08)**
  - Calculadora RIS/VES con toggle y teclado numérico
  - Integración con Mercado Pago para generar QR PIX reales
  - Timer de 7 minutos para expiración del código
  - Polling automático para detectar pago
  - Botón de simular pago (para testing)
  - Actualización automática de balance_ris_terceros al confirmar pago
  - Historial de pagos PIX

### Panel de Administración
- [x] Gestión de usuarios (búsqueda, historial)
- [x] Aprobar/Rechazar recargas VES
- [x] Aprobar/Rechazar retiros
- [x] Configuración de tasas de cambio
- [x] Asignar rol de Socio a usuarios
- [x] Asignar rol de Socio Gestor a usuarios
- [x] **Tab "Socios"** con sub-tabs:
  - Socios Referidos: Lista con código, referidos, ganancias totales, ganancias del mes
  - Socios Gestores: Lista con código, transacciones, volumen total, saldo terceros
- [x] Configurar comisión de gestores
- [x] **Resetear contraseña de usuario** - Genera contraseña temporal de un solo uso
- [x] **Herramienta de limpieza** - Eliminar transacciones pendientes atascadas

## Technical Stack
- **Frontend:** React + Vite + Tailwind CSS
- **Backend:** FastAPI + Python
- **Database:** MongoDB
- **Email:** Resend
- **WhatsApp:** Twilio
- **Push:** WebPush (pywebpush)
- **Pagos:** Mercado Pago (PIX)
- **Hosting Backend:** Railway
- **Hosting Frontend:** Cloudflare Pages
- **DNS:** Cloudflare

## API Endpoints

### Auth
- POST /api/auth/register
- POST /api/auth/verify-code
- POST /api/auth/login
- POST /api/auth/login-password
- POST /api/auth/forgot-password
- POST /api/auth/set-new-password - Establecer nueva contraseña después de reset
- GET /api/auth/me

### Partner (Socio)
- GET /api/partner/dashboard
- GET /api/partner/referral-link

### Gestor (Socio Gestor)
- GET /api/gestor/dashboard - Incluye balance_ris y balance_ris_terceros
- GET /api/gestor/beneficiaries - Lista beneficiarios con payment_type
- POST /api/gestor/beneficiaries - Crear beneficiario (Pago Móvil o Transferencia)
- POST /api/gestor/process-transaction - Procesa transacción de terceros
- POST /api/gestor/recharge-terceros - Transferir de saldo personal a terceros
- GET /api/gestor/transactions - Lista transacciones del gestor

### Admin
- POST /api/admin/assign-partner
- DELETE /api/admin/remove-partner/{user_id}
- GET /api/admin/partners
- GET /api/admin/partners/{partner_id}/referrals
- POST /api/admin/assign-gestor
- DELETE /api/admin/remove-gestor/{user_id}
- GET /api/admin/gestors
- GET /api/admin/gestor-commission
- POST /api/admin/gestor-commission
- POST /api/admin/reset-password - Resetear contraseña de usuario (SuperAdmin)
- POST /api/admin/change-role - Cambiar rol de usuario (SuperAdmin)

## Database Collections
- users
- transactions
- beneficiaries
- notifications
- pending_registrations
- referral_earnings
- gestor_beneficiaries
- gestor_transactions
- app_settings

## Deployment
- **Backend:** Railway (risapp-production.up.railway.app)
- **Frontend:** Cloudflare Pages (risapp-brasil.pages.dev)
- **Custom Domain:** www.risappbr.com / risappbr.com

## Environment Variables (Railway)
- MONGO_URL
- DB_NAME
- RESEND_API_KEY
- SENDER_EMAIL
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_WHATSAPP_FROM
- TWILIO_WHATSAPP_TO
- MERCADOPAGO_ACCESS_TOKEN
- VAPID_PUBLIC_KEY
- VAPID_PRIVATE_KEY
- VAPID_SUBJECT

## Test Results

### Sistema de Referidos "Socio" - E2E Test (2026-03-07) ✅ PASSED
- **Flujo probado:**
  1. Admin asigna rol "socio" → genera código de referido
  2. Usuario se registra con código de referido
  3. Usuario referido hace recargas
  4. Sistema paga bono milestone (5 RI$) al alcanzar 100 RI$
  5. Sistema paga comisión 1% en recargas posteriores
  6. Ganancias se registran en `referral_earnings`
- **Resultado:** 12 RI$ ganados correctamente (5 milestone + 2 + 5 comisiones)

## Changelog

### 2026-03-07 - Rediseño Flujo "Enviar Dinero"
- **Nuevo flujo de 4 pasos:**
  1. Monto a enviar
  2. Tipo de pago (Pago Móvil o Transferencia)
  3. Seleccionar/Agregar beneficiario
  4. Confirmar envío
- **Pago Móvil:** Cédula, Banco, Teléfono (11 dígitos, solo números)
- **Transferencia:** Cédula, Banco, Cuenta (20 dígitos, solo números)
- **Buscador de bancos:** Con lupa, filtrar por código (ej: 0134) o nombre
- **33 bancos venezolanos** con sus códigos actualizados
- **Backend:** Modelo Beneficiary actualizado con `payment_type`, campos opcionales según tipo

### 2026-03-07 - Descarga de Comprobantes
- **Mejora:** Botón "Descargar todas" para bajar todas las imágenes de una transacción
- **Mejora:** Botón de descarga individual en cada imagen (esquina superior derecha)
- **Formato:** Archivos se descargan como `comprobante_{ID}_{num}.png`

### 2026-03-07 - Vista Multi-Imagen para Usuarios
- **Mejora:** Usuarios pueden ver todas las imágenes de comprobantes en su historial
- **UI:** Botón "Ver X comprobantes" con ícono de ojo en transacciones completadas
- **Modal:** Muestra grid de imágenes con numeración, click para ver tamaño completo
- **Backend:** Endpoint `/transactions` ya incluye `proof_images` array

### 2026-03-08 - Migración Completa de Endpoints
- **routes/auth.py (409 líneas):** Login, registro, verificación email, password reset
- **routes/admin.py (439 líneas):** Usuarios, retiros, socios, gestores, tasas, KYC
- **routes/transactions.py (230 líneas):** Beneficiarios, retiros, historial
- **routes/gestor.py (323 líneas):** Dashboard, beneficiarios, transacciones terceros
- **routes/partner.py (102 líneas):** Dashboard socios, referral links
- **routes/basic.py (83 líneas):** Health, rate, queue stats
- **routes/dependencies.py (89 líneas):** Auth functions (get_current_user, etc.)
- **Total:** 1700 líneas organizadas en 7 archivos modulares
- **Testing:** Todos los endpoints verificados (health, auth, admin, gestor, transactions)

### 2026-03-08 - Migración Completa de Endpoints a Módulos
- **routes/basic.py:** Endpoints health, rate, queue-stats (3 endpoints)
- **routes/gestor.py:** Dashboard, beneficiarios, transacciones, recarga (6 endpoints)
- **routes/partner.py:** Dashboard, referral-link (2 endpoints)
- **routes/dependencies.py:** Funciones de autenticación (get_current_user, get_admin_user, etc.)
- **Documentación:** Cada módulo es independiente y auto-contenido
- **Estado:** server.py original sigue activo, módulos funcionando en paralelo
- **Total migrado:** ~11 endpoints a módulos separados

### 2026-03-07 - Refactorización Modular del Backend
- **Nueva estructura:** Creada arquitectura modular para mejor mantenibilidad
- **config.py:** Configuración centralizada de variables de entorno
- **database.py:** Conexión MongoDB e índices en módulo separado
- **models/:** Modelos Pydantic (user.py, transaction.py, requests.py)
- **services/:** Lógica de negocio (whatsapp.py, email.py, push_notifications.py, notifications.py, referrals.py)
- **utils/:** Utilidades (security.py, helpers.py)
- **Estado:** server.py original sigue funcionando, módulos listos para migración gradual

### 2026-03-07 - Sistema Socio Gestor E2E Completo
- **Completado:** Sistema de balance separado (personal y terceros)
- **Completado:** Flujo de transacción de 4 pasos (Monto → Tipo → Cliente → Confirmación)
- **Completado:** Integración con cola FIFO de WhatsApp para transacciones de gestor
- **Completado:** Formato de mensaje WhatsApp distingue gestor (👤 Cliente / 🏢 Gestor)
- **Completado:** Tab "Socios" en Admin Panel con sub-tabs para Referidos y Gestores
- **Completado:** Menú dinámico según rol del usuario
- **Backend:** Nuevo endpoint `/gestor/recharge-terceros` para transferir saldo
- **Backend:** Endpoints admin incluyen `is_gestor_transaction`, `client_name`, `payment_type`
- **Tests:** 9/9 tests E2E pasados en `/app/backend/tests/test_gestor_whatsapp_integration.py`

### 2026-03-07 - Multi-Imagen Admin Panel
- **Mejora:** Admin Panel ahora muestra columna "Imágenes" con indicador visual (📷 X)
- **Mejora:** Modal de procesamiento permite subir múltiples imágenes
- **Mejora:** Modal de "Ver Comprobantes" muestra todas las imágenes en grid
- **Backend:** Endpoint `/admin/withdrawals/process` soporta array `proof_images`
- **Backend:** Endpoints `/admin/withdrawals/all` y `/pending` incluyen `display_id`, `pending_images`, `proof_images`

### 2026-03-07 - Fix Multi-Imagen WhatsApp
- **Bug corregido:** Solo la primera imagen se asignaba a la transacción activa
- **Causa raíz:** Patrón read-modify-write causaba race conditions entre webhooks
- **Solución:** Cambio a operación atómica `$push` con `$each` de MongoDB
- **Tests:** 12/12 tests pasados en `/app/backend/tests/test_whatsapp_image_accumulation.py`

### 2026-03-05 - Sistema FIFO WhatsApp
- Sistema FIFO para retiros WhatsApp con Total Bs pendientes implementado
- Panel de admin con estadísticas de cola en tiempo real

### 2026-03-08 - Nuevo Flujo PIX Socio Gestor
- **IMPLEMENTADO:** Flujo completo para pagos de terceros via PIX
- **Mercado Pago:** Integración real que genera QR PIX con código copia-pega
- **Frontend:** Dashboard de gestor totalmente rediseñado con:
  - Calculadora RIS/VES con toggle y teclado numérico
  - Pantalla de QR PIX con timer de 7 minutos
  - Polling automático para detectar confirmación de pago
  - Botón de simulación de pago para testing
  - Selección de tipo de pago (Pago Móvil vs Transferencia)
  - Selector de beneficiarios
  - Pantalla de confirmación de transacción
- **Backend:** Nuevos endpoints en `/api/gestor/pix/`:
  - `POST /create` - Genera QR PIX real
  - `GET /status/{id}` - Verifica estado del pago
  - `POST /simulate-payment/{id}` - Simula pago para testing
  - `GET /history` - Historial de pagos PIX
  - `POST /cancel/{id}` - Cancela pago pendiente
- **Webhook:** Endpoint `/api/webhook/mercadopago` para recibir confirmaciones
- **Tests:** 17/18 backend tests pasados, 100% frontend tests pasados
- **Balance Terceros:** Se actualiza automáticamente al confirmar pago PIX

### 2026-03-08 - Correcciones y Mejoras Gestor
- **Bug Fix:** Corregido el avance automático de pantalla tras confirmación de pago PIX
  - Implementado `useRef` para prevenir procesamiento doble
  - Polling aumentado a cada 2 segundos para respuesta más rápida
- **Nueva Funcionalidad:** Botón "Enviar desde Saldo Terceros"
  - Permite envío directo sin pasar por recarga PIX
  - Útil cuando el gestor ya tiene saldo disponible
  - Valida que el monto no exceda el saldo disponible
- **Historial de Operaciones con Tabs:**
  - Tab "Todos": Muestra PIX recibidos y envíos mezclados, ordenados por fecha
  - Tab "PIX Recibidos": Solo pagos PIX con estado (Confirmado/Pendiente/Expirado)
  - Tab "Envíos": Solo transacciones de envío con tipo de pago e icono
- **UI Simplificada:** Panel Gestor muestra solo Saldo Terceros (no saldo personal)

### 2026-03-17 - Limpieza de server.py
- **Refactorización completada:** server.py reducido de 6027 a 578 líneas (90% reducción)
- **Estructura modular:** Los endpoints principales están ahora en `/routes/`:
  - `auth.py` - Autenticación (login, registro, etc.)
  - `admin.py` - Panel de administración
  - `gestor.py` - Panel del gestor
  - `gestor_pix.py` - Pagos PIX de Mercado Pago
  - `partner.py` - Panel de socios
  - `transactions.py` - Transacciones y beneficiarios
  - `basic.py` - Endpoints básicos (health, rate, etc.)
- **Legacy router:** Endpoints no migrados (notificaciones, soporte, web push) siguen en server.py
- **Corrección de colecciones:** Unificado uso de `db.user_sessions` en todos los módulos
- **Backup:** server_old.py conservado como referencia

### 2026-03-18 - Integración Stripe Completada
- **Backend:** Nuevo módulo `/routes/stripe_payments.py`:
  - `GET /payments/stripe/packages` - Lista paquetes de recarga con bonus
  - `POST /payments/stripe/checkout` - Crea sesión de Stripe Checkout
  - `GET /payments/stripe/status/{session_id}` - Verifica estado del pago
  - `GET /payments/stripe/history` - Historial de pagos con tarjeta
  - `POST /webhook/stripe` - Webhook para confirmaciones automáticas
- **Frontend:** Nueva página `/recharge/stripe` (`RechargePage.jsx`):
  - Paquetes de recarga con bonus progresivo (0%, 5%, 10%, 15%)
  - Toggle para elegir destino (Mi Saldo / Saldo Terceros para gestores)
  - Redirección a Stripe Checkout real
  - Polling de estado del pago tras retorno
  - Pantallas de éxito/error/cargando
- **Paquetes disponibles:**
  - R$ 50 → R$ 50 (sin bonus)
  - R$ 100 → R$ 105 (+5% bonus)
  - R$ 200 → R$ 220 (+10% bonus)
  - R$ 500 → R$ 575 (+15% bonus)
- **Usa:** emergentintegrations library con clave de prueba de Emergent

### 2026-03-18 - Notificaciones por Email Obligatorias
- **Servicio creado:** `/services/email_notifications.py`
- **Eventos notificados por email:**
  - Nuevo inicio de sesión (con fecha, dispositivo)
  - Cambio de contraseña
  - Recarga exitosa (Stripe, PIX)
  - Pago PIX recibido (para gestores)
  - Retiro iniciado / completado
  - Transferencia enviada
  - Actividad sospechosa
- **Template HTML profesional** con branding RIS App
- **Integración con Resend** usando las credenciales existentes
- **Notificaciones obligatorias** - no se pueden desactivar (seguridad)

### 2026-03-27 - Eliminación de Integración Stripe
- **Eliminado:** Todo el código relacionado con Stripe
  - `/app/backend/routes/stripe_payments.py` - Backend eliminado
  - `/app/frontend/src/pages/RechargePage.jsx` - Frontend eliminado
  - Rutas `/recharge/stripe` y `/recharge/success` - Eliminadas de App.jsx
  - Columna "USD → VES" - Eliminada del Admin Panel (pestaña Tasas)
  - `stripe==11.4.1` - Eliminado de requirements.txt
  - Referencias en `routes/__init__.py` - Eliminadas
- **Admin Panel:** Ahora solo muestra 2 tasas (RIS→VES y VES→RIS)

## Last Updated
2026-03-27 - Eliminación completa de integración Stripe

