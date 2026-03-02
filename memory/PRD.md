# RIS App - Product Requirements Document

## Overview
**Nombre:** RIS - Billetera Digital para Remesas
**Descripción:** Aplicación web de billetera digital para transferencias de dinero entre Brasil y Venezuela
**Idioma:** Español

## User Personas
- **Usuarios en Brasil:** Trabajadores brasileños o venezolanos en Brasil que envían dinero a Venezuela
- **Beneficiarios en Venezuela:** Familiares que reciben remesas
- **Administradores:** Personal de RIS que procesa transacciones y verifica usuarios

## Core Requirements

### Autenticación
- [x] Login con email/contraseña
- [x] Login con Google OAuth
- [x] Registro de nuevos usuarios
- [x] Sistema de roles (user, admin, super_admin)

### Dashboard
- [x] Balance total en RIS
- [x] Tasa de cambio actual (RIS/VES)
- [x] Resumen de ingresos/gastos (30 días)
- [x] Acceso rápido a Recargar y Enviar
- [x] Transacciones recientes

### Recargas
- [x] PIX (Brasil) - Pago instantáneo
- [x] Bolívares (Venezuela) - Transferencia bancaria
- [x] Generación de QR Code PIX
- [x] Subida de comprobante para VES

### Envío de Remesas
- [x] Wizard de 3 pasos (monto → beneficiario → confirmación)
- [x] Gestión de beneficiarios guardados
- [x] Cálculo automático de conversión RIS → VES
- [x] Lista de bancos venezolanos

### Historial
- [x] Lista de transacciones con filtros
- [x] Estados: Completado, Pendiente, Rechazado
- [x] Detalles de cada transacción

### Perfil
- [x] Información del usuario
- [x] Estado de verificación KYC
- [x] Cambio de contraseña
- [x] Cerrar sesión

### Soporte
- [x] Chat con asistente virtual
- [x] Preguntas frecuentes rápidas
- [x] Historial de mensajes

### Panel de Administración
- [x] Resumen de estadísticas
- [x] Gestión de retiros pendientes
- [x] Gestión de recargas VES
- [x] Lista de usuarios
- [x] Verificaciones KYC pendientes
- [x] Configuración de tasas de cambio

## Design System - NexPay Style

### Colores
- **Fondo:** `radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)`
- **Color primario:** `#6366f1` (índigo)
- **Color éxito:** `#16a34a` (verde)
- **Color error:** `#dc2626` (rojo)
- **Color warning:** `#d97706` (ámbar)

### Tipografía
- **Fuente:** Inter, Helvetica, -apple-system, sans-serif
- **Encabezados:** 20-28px, font-weight: 700
- **Texto:** 14-16px, font-weight: 400-500

### Componentes
- **Tarjetas:** border-radius: 24px, box-shadow sutil, fondo blanco
- **Botones:** border-radius: 14px, height: 56px, font-weight: 600
- **Inputs:** border-radius: 14px, height: 56px, border: 1px solid #d1d5db
- **Badges:** border-radius: 9999px (pill)

## Technical Architecture

### Frontend
- **Framework:** React + Vite
- **Styling:** Tailwind CSS v4 + Inline styles
- **State:** React Context API
- **Router:** React Router v6

### Backend
- **Framework:** FastAPI (Python)
- **Database:** MongoDB
- **Authentication:** JWT tokens

### Deployment
- **Frontend:** Cloudflare Pages (Railway de producción)
- **Backend:** Railway
- **Preview:** Emergent Platform

## Completed Work - March 2, 2026

### Bug Fixes
- [x] Dashboard balance card not rendering - FIXED (changed to inline styles due to Tailwind v4 compatibility)
- [x] Admin Panel "Procesar" and "Rechazar" buttons not working - FIXED (corrected API endpoint calls to include `action` parameter)
- [x] **Registration Flow - FIXED (2026-03-02):** 
  - Problem: Page went blank after form submission
  - Root cause: Frontend was calling `register(name, email, password)` but backend requires two-step verification flow
  - Solution: Implemented complete two-step registration process:
    1. Step 1: Fill form → POST /api/auth/register → sends verification code
    2. Step 2: Enter verification code → POST /api/auth/verify-email → creates account and auto-logs in
  - Added "Confirm Password" field as requested
  - Removed placeholder text and icons as requested
  - Testing: 100% pass rate (5/5 tests)

### New Features (March 2, 2026)
- [x] **Dual Rate Management:** Added VES → RIS rate input in Admin Panel alongside existing RIS → VES rate (with independent update buttons)
- [x] **Voucher Viewing for Users:** Added "Ver comprobante" button (eye icon) in History page to view payment proof for completed withdrawals
- [x] **Voucher Modal:** Professional modal displaying transaction details and proof image
- [x] **WhatsApp Integration Verified:** Twilio WhatsApp notifications working correctly for new withdrawals
- [x] **Notification Bell:** Added notification bell icon with unread count to all main pages (Dashboard, Recharge, Send, History) - both desktop and mobile views
- [x] **Notifications Page Fixed:** Resolved blank page issue and back button navigation
- [x] **Admin User History:** Admin panel now shows complete user history with detailed modal - includes balance, stats, KYC info, all transactions, and beneficiaries
- [x] **Support Chat with Refresh:** Added refresh button and conversation history loading for support chat with WhatsApp integration
- [x] **VES Recharge System:** Complete VES recharge flow implemented with:
  - Bank selection (Banco de Venezuela, Banesco)
  - Payment type selection (Pago Móvil, Transferencia)
  - Dynamic payment details with copy buttons
  - Voucher/proof upload requirement
  - Pending review status after submission
  - Admin panel "Recargas VES" tab for approval/rejection

### Redesign
- [x] Login.jsx - NexPay style (previously approved)
- [x] Register.jsx - NexPay style (previously done)
- [x] Dashboard.jsx - Complete redesign with inline styles
- [x] Recharge.jsx - Complete redesign
- [x] Send.jsx - Complete redesign
- [x] History.jsx - Complete redesign
- [x] Profile.jsx - Complete redesign with push notifications toggle
- [x] Support.jsx - Complete redesign
- [x] AdminPanel.jsx - Complete redesign

### Localization
- [x] All UI text translated to Spanish

### Web Push Notifications (NEW)
- [x] Backend service (web_push_service.py) with pywebpush
- [x] VAPID key generation and configuration
- [x] API endpoints: /push/vapid-public-key, /push/subscribe, /push/unsubscribe, /push/status, /push/test
- [x] Service Worker (sw.js) for handling push events
- [x] Frontend push service (pushService.js)
- [x] Toggle in Profile page to enable/disable notifications
- [x] Test notification button

### Integrations
- [x] Mercado Pago PIX - Already implemented and working
- [x] Resend Email - Verification codes sent via email with custom domain `noreply@risappbr.com` (Verified 2026-03-02)
- [ ] Stripe - Removed (user decision to use Mercado Pago instead)

## Testing Results
- **Frontend Testing:** 100% pass rate (16/16 tests)
- **All pages verified:** Login, Dashboard, Recharge, Send, History, Profile, Support, Admin Panel
- **Design consistency verified:** NexPay style applied across all pages

## Pending/Future Tasks

### P0 - Critical
- [x] Admin Panel "Procesar" and "Rechazar" buttons - FIXED (2026-03-02)
- [x] Registration Flow - FIXED (2026-03-02) - Two-step verification flow working

### P1 - High Priority
- [ ] End-to-End test Web Push Notifications with transaction events
- [ ] End-to-End test PIX recharge flow with Mercado Pago
- [ ] End-to-End test Admin-to-User Chat Flow via WhatsApp

### P2 - Medium Priority
- [ ] Dark mode support
- [ ] Stripe integration (deprioritized - using Mercado Pago PIX)

### P3 - Low Priority
- [ ] Mobile app (React Native)
- [ ] Analytics dashboard

## Credentials
- **Super Admin:**
  - Email: marshalljulio46@gmail.com
  - Password: Admin2025!
