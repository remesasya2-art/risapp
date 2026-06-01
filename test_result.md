#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================
# (Testing protocol preserved)
#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

user_problem_statement: "Mejora completa del sistema KYC del panel de administración: fix de bug de selfie (src vacío), lightbox con zoom/rotación/ESC, modal de rechazo con motivo obligatorio (6 motivos predefinidos), tabs Pendientes/Aprobados/Rechazados con contadores, buscador, fecha de envío relativa, historial de auditoría, nota interna del admin."

backend:
  - task: "GET /api/admin/kyc/list with tabs/counts/search"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Returns {counts: {pending, approved, rejected, total}, items: [...]} with normalized image fields. Filters by status & search (name/email/cpf/doc/phone). Verified manually via curl: 3 pending docs returned with selfie_image populated correctly."

  - task: "POST /api/admin/kyc/{id}/approve"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Updates verification + user status to approved/verified, writes audit log entry, sends notification. Tested with curl."

  - task: "POST /api/admin/kyc/{id}/reject with reason_code"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "6 predefined codes via /api/admin/kyc/rejection-reasons. 'other' requires reason_text (returns 400 otherwise). Builds final_reason 'Label: text', writes audit log."

  - task: "PATCH /api/admin/kyc/{id}/note (internal admin note)"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Stores admin_note string on verifications doc, logs change in kyc_audit_log only when content actually changes."

  - task: "GET /api/admin/kyc/{id}/history (audit log)"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Returns full audit trail (submitted, approved, rejected, note_updated) sorted desc."

  - task: "Image normalization (fix selfie bug)"
    implemented: true
    working: true
    file: "backend/routes/kyc_admin.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "_normalize_image() returns None for empty/placeholder/data:/data:, strings so frontend can fall back to placeholder. Eliminates src='data:,' issue."

frontend:
  - task: "KycPanel - tabs with counts + search"
    implemented: true
    working: true
    file: "frontend/src/components/admin/KycPanel.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Tabs: Pendientes/Aprobados/Rechazados with live counts. Debounced search (300ms) by name/email/doc. Cards show selfie thumbnail, badge, masked CPF, doc, phone, relative submission time."

  - task: "ImageLightbox - zoom/rotate/ESC/EXIF"
    implemented: true
    working: true
    file: "frontend/src/components/common/ImageLightbox.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Full-screen lightbox: zoom (+/-, wheel), rotate 90° (R key or button), pan via drag when zoomed, ←/→ navigation, ESC close, image-orientation:from-image for EXIF respect, download button. Body scroll locked while open."

  - task: "KycRejectModal - 6 predefined reasons"
    implemented: true
    working: true
    file: "frontend/src/components/admin/KycRejectModal.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Fetches reasons from API with fallback list. 'Otro motivo' forces obligatory comment with red highlight. Submit button disabled until validation passes."

  - task: "KycDetailModal - docs in row + internal note + audit history"
    implemented: true
    working: true
    file: "frontend/src/components/admin/KycDetailModal.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "3 doc tiles in a row (ID/CPF/Selfie) each with 'Cargado' or 'Faltante' indicator. Click opens lightbox. Organized user data grid with icons. Internal admin note textarea (admins-only). 'Ver historial' loads audit log inline. Sticky footer with Aprobar/Rechazar."

  - task: "AdminPanel integration"
    implemented: true
    working: true
    file: "frontend/src/pages/AdminPanel.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Old KYC block and modal removed. <KycPanel onChange={refreshKycStats}/> replaces it. Overview stats now read counts.pending from /admin/kyc/list."

metadata:
  created_by: "main_agent"
  version: "2.0"
  test_sequence: 1
  run_ui: true

test_plan:
  current_focus:
    - "KycPanel - tabs with counts + search"
    - "ImageLightbox - zoom/rotate/ESC/EXIF"
    - "KycRejectModal - 6 predefined reasons"
    - "KycDetailModal - docs in row + internal note + audit history"
    - "GET /api/admin/kyc/list with tabs/counts/search"
    - "POST /api/admin/kyc/{id}/approve"
    - "POST /api/admin/kyc/{id}/reject with reason_code"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      KYC admin system fully overhauled.

      What changed:
      - Removed selfie src='' bug by normalizing image strings server-side.
      - New /api/admin/kyc/* endpoints (list+counts, approve, reject with reason_code, note, history).
      - 6 predefined rejection reasons enforced by backend.
      - New KycPanel component with tabs/counts/search + relative dates.
      - New ImageLightbox with zoom/rotate/EXIF/keyboard shortcuts.
      - Internal admin note + audit log surfaced in detail modal.

      Test credentials (in /app/memory/test_credentials.md):
      - Admin: admin@risapp.test / Admin1234 (super_admin, 2FA bypassed)
      - Users with pending KYC: joao@/maria@/carlos@test.com / Pass1234

      Auth note: login uses /api/auth/login-password and triggers 2FA enrollment.
      For the test admin, 2FA was bypassed via DB flags (two_factor_skipped:true,
      two_factor_setup_completed:true). A long-lived session token was also
      pre-inserted; testing agent can either login fresh (skipping/handling 2FA)
      or set localStorage.session_token directly using the value documented below.

      Active session token for admin@risapp.test (valid 7d):
        u47IbeJOHZ-NYcAhii8pWSkE1Hh2jAJqsiWkNJYhk3g
