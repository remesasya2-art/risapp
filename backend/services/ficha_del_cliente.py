"""La ficha de un cliente: sus datos en un PDF, armado al vuelo.

DE DONDE SALE

    Esto vivía dentro de `routes/google_drive.py`, y el PDF que armaba se
    subía a Google Drive. Ese camino se quitó: los datos de los clientes de
    una app financiera no tienen por qué vivir en una cuenta de Google —ni
    siquiera en la del dueño—, y el token que lo permitía era una credencial
    permanente guardada en la base.

    Ahora el PDF se arma cuando alguien lo pide y se le devuelve como
    descarga. No se guarda en ningún lado: en Railway el disco del contenedor
    se borra en cada despliegue, así que un archivo guardado ahí es un archivo
    que desaparece solo, y uno menos que cuidar.

QUE LLEVA, Y QUE NO

    Lleva los datos: nombre, correo, CPF, documento, teléfono, estado del KYC,
    rol y fecha de registro.

    NO lleva las fotos del documento ni la selfie, y eso es a propósito.

    El código las busca en el documento de `users` —`user_data.get(
    "id_document_image")`— y ahí no están: el KYC las guarda en la colección
    `verifications`. O sea que nunca salieron en la ficha, por un descuido que
    resultó ser la decisión correcta.

    Se deja así, y ahora escrito. Una ficha con el documento y la selfie de
    alguien es un archivo con el que se puede abrir una cuenta a nombre de esa
    persona; en cuanto se descarga sale del cofre, de la tabla de permisos y
    de la auditoría, y ya no se puede borrar. Si algún día hace falta, que sea
    una decisión tomada y no el resultado de "arreglar" esta función.
"""
import base64
import logging
import os
import tempfile
from datetime import datetime, timezone

from services import cofre

logger = logging.getLogger(__name__)


def armar(user_data: dict) -> bytes:
    """El PDF de este cliente, en memoria.

    Devuelve los BYTES y no una ruta a un archivo. La versión anterior
    escribía el PDF en un temporal y devolvía el camino, porque después había
    que dárselo a la biblioteca de Google. Ya no hay a quién dárselo, y un
    archivo temporal que nadie borra es un archivo con datos de un cliente
    tirado en el disco del servidor.
    """
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
    pdf.cell(0, 8, 'RISApp - Registro KYC', align='C', new_x="LMARGIN", new_y="NEXT")
    
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
        # Abrir es idempotente: sobre un valor ya en claro no hace nada. Va acá
        # igual porque este archivo puede recibir el documento crudo de la base.
        data = cofre.abrir(user_data.get(field, ""))
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
    pdf.cell(0, 6, f'Generado por RISApp - {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")}', align='C')
    
    # A memoria, no a disco.
    salida = bytes(pdf.output())

    for f in tmp_files:
        try:
            os.unlink(f)
        except OSError:
            # Un temporal que no se pudo borrar no vale tumbar el PDF que ya
            # está armado. `except:` pelado atrapaba hasta un Ctrl-C y un
            # KeyboardInterrupt, que no son «el archivo no se pudo borrar».
            pass

    return salida
