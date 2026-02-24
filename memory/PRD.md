# RIS App - Product Requirements Document

## Project Overview
RIS (Remesas Internacionales Seguras) is a mobile and web money transfer application for sending remittances between Brazil and Venezuela.

## Core Features

### Authentication
- Email/password registration with SMS verification (Twilio)
- Google OAuth login (Emergent-managed)
- KYC verification with document upload and selfie

### Money Transfer
- **Recharges**: PIX payments (Brazil) and VES bank transfers (Venezuela)
- **Withdrawals**: Send RIS to Venezuelan bank accounts
- Real-time exchange rates (auto-updates every 10 seconds)

### Admin Panel
- User management (view, verify KYC, soft-delete)
- Transaction management (approve/reject recharges and withdrawals)
- Support chat with image upload capability
- Rate management

## Technical Architecture

### Infrastructure (Production)
- **Frontend**: Cloudflare Pages (web app)
- **Backend**: Railway (FastAPI)
- **Database**: Railway (MongoDB)
- **CI/CD**: GitHub -> Railway auto-deploy

### Tech Stack
- **Frontend**: Expo (React Native), expo-router
- **Backend**: FastAPI (Python)
- **Database**: MongoDB (Motor async driver)
- **SMS**: Twilio
- **Payments**: Mercado Pago (PIX)

## What's Been Implemented

### Session: 2026-02-24
- **Real-Time Exchange Rate System COMPLETED**:
  - Created `RateContext.tsx` - Global context that polls `/api/rate` every 10 seconds
  - Wrapped entire app with `RateProvider` in `_layout.tsx`
  - Refactored `index.tsx` (Dashboard) to use `useRate()` hook
  - Refactored `send.tsx` (Enviar a Venezuela) to use `useRate()` hook
  - Refactored `recharge-ves.tsx` (Recargar con Bolívares) to use `useRate()` hook
  - Removed all duplicate rate-fetching logic from individual pages
  - All screens now show consistent rates: ris_to_ves and ves_to_ris
  - Sidebar widget shows "EN VIVO" (live) indicator with real-time rates

### Session: 2026-02-13
- **PIX Pending Transaction Feature**:
  - New endpoint `GET /api/pix/pending` to retrieve pending PIX transactions
  - Auto-detection of expired transactions (>30 minutes)
  - Frontend automatically shows pending transaction when user returns to recharge screen
  - Shows "pending_review" status when proof has been uploaded
  - User can cancel pending transaction and create a new one

- **Optional PIX Voucher Upload**:
  - Added "Listo, ya pagué" primary button for users who completed payment
  - Voucher upload section now marked as "optional" with "Acelera la verificación" badge
  - Users can rely on automatic Mercado Pago verification without uploading proof

- **Enhanced Support Chat**:
  - Real-time connection status indicator (online/reconnecting/offline)
  - Automatic message retry with exponential backoff (up to 3 retries)
  - Quick reply buttons for common questions
  - Visual feedback for message status (sending/sent/error)
  - Tap-to-retry for failed messages
  - Connection warning banner when offline
  - Vibration notification for new admin messages (mobile)
  - Improved UI with better styling and animations

- **Push Notifications System**:
  - Implemented Expo Push Notifications API for mobile devices
  - Added `send_push_notification()` function in backend using Expo Push API
  - Added `send_push_to_user()` and `send_push_to_admins()` helper functions
  - Modified `create_notification()` to automatically send push notifications
  - New endpoints:
    - `POST /api/push/test` - Test push notification for current user
    - `POST /api/push/send-to-user/{user_id}` - Admin endpoint to send push to specific user
  - Re-enabled push notification setup in AuthContext.tsx
  - Push notifications triggered on: transaction updates, support messages, verifications

### Previous Sessions
- Full infrastructure migration to Railway (backend + database)
- Admin panel redesign with professional dark theme
- User soft-delete functionality for super_admin
- Image upload in admin support chat
- Gallery upload option for PIX proofs
- Unique constraints for email and CPF
- Exchange rate bug fixes
- Pull-to-refresh cache-busting improvements

## Pending Tasks

### P1 - High Priority
- **Professional Design Improvements**: Update UI of all user screens to match "Nubank" banking app aesthetic (user requested)
- **Support Button for Unauthenticated Users**: Complete modal for users who cannot log in to contact support

### P2 - Future Enhancements
- Stripe integration for recharges (blocked on user's Stripe account)
- Push notifications verification (waiting for user to re-open mobile app)
- Automate Cloudflare deployment from GitHub

### P3 - Low Priority
- Refactor GlobalHeader.tsx usage across all screens
- Configure ESLint properly for TypeScript

## Recent Fixes (2026-02-24)

### Real-Time Exchange Rates Fixed
- All screens now use centralized `RateContext` for consistent rate display
- Rate polling every 10 seconds ensures near real-time updates
- Dashboard shows: "1 RIS = X VES" 
- Recharge VES shows: "X VES = 1 RIS" (for VES to RIS conversion)
- Send screen shows: "1 RIS = X VES" (for RIS to VES conversion)

## Key Endpoints

### Exchange Rates
- `GET /api/rate` - Get current exchange rates (ris_to_ves, ves_to_ris, ris_to_brl)

### PIX Payments
- `POST /api/pix/create` - Create PIX payment
- `GET /api/pix/pending` - Get pending PIX transaction
- `POST /api/pix/upload-proof` - Upload payment proof
- `POST /api/pix/cancel` - Cancel pending PIX

### User Management
- `POST /api/auth/login-password` - Login
- `POST /api/auth/register` - Register
- `GET /api/auth/me` - Get current user
- `DELETE /api/admin/users/{user_id}` - Soft delete user

## Test Credentials
- **Super Admin**: marshalljulio46@gmail.com / Admin2025!
- **Test User 1**: test@ris.app / Test1234!
- **Test User 2**: prueba@ris.app / Prueba123!

## Deployment URLs
- **Frontend**: https://risapp.pages.dev (Cloudflare)
- **Backend**: https://risapp-production.up.railway.app (Railway)
- **Preview**: https://realtime-exchange-1.preview.emergentagent.com (Emergent)
