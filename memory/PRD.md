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
- Real-time exchange rates

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

### Session: 2026-02-13
- **PIX Pending Transaction Feature**:
  - New endpoint `GET /api/pix/pending` to retrieve pending PIX transactions
  - Auto-detection of expired transactions (>30 minutes)
  - Frontend automatically shows pending transaction when user returns to recharge screen
  - Shows "pending_review" status when proof has been uploaded
  - User can cancel pending transaction and create a new one

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

### P1 - Verification
- WhatsApp webhook URL updated by user - needs verification that notifications work

### P2 - Future
- Stripe integration for recharges (blocked on user's Stripe account)
- Push notifications implementation

## Key Endpoints

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
- **Preview**: https://pix-incomplete.preview.emergentagent.com (Emergent)
