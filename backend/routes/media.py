"""
Media routes - Proxy for Twilio media files
"""
import logging
import os
import re
import httpx
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from routes.dependencies import get_current_user
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/media", tags=["media"])

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")


@router.get("/twilio/{path:path}")
async def proxy_twilio_media(path: str, current_user: User = Depends(get_current_user)):
    """
    Proxy Twilio media files to avoid authentication issues
    Converts: /api/media/twilio/AC.../Messages/MM.../Media/ME...
    To fetch from: https://api.twilio.com/2010-04-01/Accounts/AC.../Messages/MM.../Media/ME...
    """
    try:
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            raise HTTPException(status_code=500, detail="Twilio credentials not configured")
        
        # Build full Twilio URL
        twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{path}"
        
        logger.info(f"Proxying Twilio media: {twilio_url}")
        
        # Fetch from Twilio with authentication
        async with httpx.AsyncClient() as client:
            response = await client.get(
                twilio_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                follow_redirects=True,
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Twilio media fetch failed: {response.status_code}")
                raise HTTPException(status_code=404, detail="Media not found")
            
            # Return the media with appropriate content type
            content_type = response.headers.get("content-type", "image/jpeg")
            
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "private, max-age=86400",
                }
            )
            
    except httpx.RequestError as e:
        logger.error(f"Error fetching Twilio media: {e}")
        raise HTTPException(status_code=500, detail="Error fetching media")


def convert_twilio_url_to_proxy(url: str, base_url: str = "") -> str:
    """
    Convert a Twilio media URL to use our proxy
    
    Input: https://api.twilio.com/2010-04-01/Accounts/AC.../Messages/MM.../Media/ME...
    Output: /api/media/twilio/AC.../Messages/MM.../Media/ME...
    """
    if not url:
        return url
    
    # Extract the path after /Accounts/
    match = re.search(r'/Accounts/(AC[^/]+/.*)', url)
    if match:
        path = match.group(1)
        return f"{base_url}/api/media/twilio/{path}"
    
    return url
