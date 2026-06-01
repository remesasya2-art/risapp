"""
Google Drive integration for KYC document backup
"""
import os
import io
import base64
import logging
import tempfile
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from routes.dependencies import get_admin_user, get_super_admin
from models.user import User
from database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth/drive", tags=["Google Drive"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# Redirect to frontend route instead of backend (bypasses Cloudflare blocking)
GOOGLE_DRIVE_REDIRECT_URI = os.environ.get("GOOGLE_DRIVE_REDIRECT_URI", "")


@router.get("/connect")
async def connect_drive(admin: User = Depends(get_super_admin)):
    """Start Google Drive OAuth flow (admin only)"""
    import urllib.parse
    
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_DRIVE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
        "state": admin.user_id
    }
    authorization_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
    return {"authorization_url": authorization_url}


@router.post("/exchange-code")
async def exchange_code(request_data: dict, admin: User = Depends(get_super_admin)):
    """Exchange authorization code for tokens - called from frontend"""
    import httpx
    
    code = request_data.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Código no proporcionado")
    
    try:
        # Exchange code for tokens directly via HTTP (no PKCE needed)
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_DRIVE_REDIRECT_URI,
                "grant_type": "authorization_code"
            })
        
        if resp.status_code != 200:
            logger.error(f"Token exchange failed: {resp.text}")
            raise HTTPException(status_code=400, detail=f"Google error: {resp.json().get('error_description', resp.text)}")
        
        tokens = resp.json()
        
        for key in [admin.user_id, "global"]:
            await db.drive_credentials.update_one(
                {"admin_id": key},
                {"$set": {
                    "admin_id": key,
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens.get("refresh_token"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "scopes": tokens.get("scope", "").split(),
                    "expiry": None,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )

        logger.info(f"Drive credentials saved for admin {admin.user_id}")
        return {"success": True, "message": "Google Drive conectado exitosamente"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Drive code exchange error: {e}")
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")


@router.get("/status")
async def drive_status(admin: User = Depends(get_super_admin)):
    """Check if Drive is connected"""
    creds = await db.drive_credentials.find_one({"admin_id": admin.user_id})
    if not creds:
        creds = await db.drive_credentials.find_one({"admin_id": "global"})
    return {"connected": bool(creds and creds.get("refresh_token"))}


async def get_drive_service(admin_id: str):
    """Build Drive service with stored credentials"""
    creds_doc = await db.drive_credentials.find_one({"admin_id": admin_id})
    if not creds_doc:
        creds_doc = await db.drive_credentials.find_one({"admin_id": "global"})
    if not creds_doc:
        raise HTTPException(status_code=400, detail="Google Drive no conectado. Haz clic en 'Conectar Drive' primero.")

    creds = Credentials(
        token=creds_doc["access_token"],
        refresh_token=creds_doc.get("refresh_token"),
        token_uri=creds_doc["token_uri"],
        client_id=creds_doc["client_id"],
        client_secret=creds_doc["client_secret"],
        scopes=creds_doc.get("scopes", [])
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        await db.drive_credentials.update_one(
            {"admin_id": admin_id},
            {"$set": {
                "access_token": creds.token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
            }}
        )

    return build('drive', 'v3', credentials=creds)


async def get_or_create_folder(service, name, parent_id=None):
    """Find or create a folder in Drive"""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, spaces='drive', fields='files(id,name)').execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        metadata['parents'] = [parent_id]

    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']


def generate_client_pdf(user_data: dict) -> str:
    """Generate a client profile PDF with all KYC data and images"""
    from fpdf import FPDF
    from PIL import Image as PILImage
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Header
    pdf.set_fill_color(30, 58, 138)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_y(8)
    pdf.cell(0, 12, 'FICHA DE CLIENTE', align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'RIS App - Registro KYC', align='C', new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_y(48)
    pdf.set_text_color(0, 0, 0)
    
    # Personal info section
    pdf.set_fill_color(243, 244, 246)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 10, '  DATOS PERSONALES', fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    fields = [
        ("Nombre Completo", user_data.get("full_name", user_data.get("name", "No disponible"))),
        ("Email", user_data.get("email", "No disponible")),
        ("CPF", user_data.get("cpf_number", user_data.get("cpf", "No disponible"))),
        ("RNM / Documento", user_data.get("document_number", "No disponible")),
        ("Telefono", user_data.get("phone_number", "No disponible")),
        ("Estado KYC", "Verificado" if user_data.get("verification_status") == "verified" else "Pendiente"),
        ("Rol", user_data.get("role", "user")),
        ("Fecha de Registro", str(user_data.get("created_at", "No disponible"))[:19]),
        ("Email Verificado", "Si" if user_data.get("email_verified") else "No"),
    ]
    
    pdf.set_font('Helvetica', '', 11)
    for label, value in fields:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(60, 7, f'  {label}:', new_x="RIGHT")
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(0, 7, f'  {value}', new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(6)
    
    # Images section
    pdf.set_fill_color(243, 244, 246)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, '  DOCUMENTOS KYC', fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    
    image_fields = {
        "picture": "Foto de Perfil",
        "id_document_image": "Documento de Identidad",
        "cpf_image": "CPF",
        "selfie_image": "Selfie"
    }
    
    tmp_files = []
    for field, label in image_fields.items():
        data = user_data.get(field, "")
        if not data or not data.startswith("data:"):
            continue
        
        try:
            header, b64 = data.split(",", 1)
            img_bytes = base64.b64decode(b64)
            
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name
                tmp_files.append(tmp_path)
            
            if pdf.get_y() > 220:
                pdf.add_page()
            
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(107, 114, 128)
            pdf.cell(0, 7, f'  {label}', new_x="LMARGIN", new_y="NEXT")
            
            img = PILImage.open(tmp_path)
            w, h = img.size
            max_w = 80
            ratio = max_w / w
            img_h = h * ratio
            if img_h > 80:
                img_h = 80
                ratio = img_h / h
                max_w = w * ratio
            
            pdf.image(tmp_path, x=15, w=max_w, h=img_h)
            pdf.ln(4)
            
        except Exception as e:
            logger.error(f"Error adding image {field}: {e}")
    
    # Footer
    pdf.ln(8)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 6, f'Generado por RIS App - {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")}', align='C')
    
    # Save PDF
    pdf_path = tempfile.mktemp(suffix=".pdf")
    pdf.output(pdf_path)
    
    for f in tmp_files:
        try:
            os.unlink(f)
        except:
            pass
    
    return pdf_path


@router.post("/upload-kyc/{user_id}")
async def upload_kyc_to_drive(user_id: str, admin: User = Depends(get_super_admin)):
    """Generate client profile PDF and upload to Google Drive"""
    service = await get_drive_service(admin.user_id)

    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Create folder
    root_folder_id = await get_or_create_folder(service, "RIS_App_KYC")

    user_name = user.get("full_name", user.get("email", "usuario")).replace(" ", "_")
    cpf = user.get("cpf_number", user.get("cpf", "sin_id"))
    
    # Generate PDF
    pdf_path = generate_client_pdf(user)
    
    try:
        # Upload PDF to Drive
        filename = f"Ficha_{user_name}_{cpf}.pdf"
        media = MediaFileUpload(pdf_path, mimetype='application/pdf', resumable=True)
        file_metadata = {
            'name': filename,
            'parents': [root_folder_id]
        }
        file = service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        drive_link = file.get('webViewLink')
        
        # Save link in user document
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "drive_kyc_link": drive_link,
                "drive_uploaded_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"KYC PDF uploaded to Drive for {user_id} by admin {admin.user_id}")
        
        return {
            "message": f"Ficha de cliente subida a Google Drive",
            "filename": filename,
            "link": drive_link
        }
    finally:
        os.unlink(pdf_path)
