import logging
import requests
import json
from django.conf import settings

logger = logging.getLogger(__name__)

# Settings variables can be configured in settings.py or env variables
EVOLUTION_API_URL = getattr(settings, 'EVOLUTION_API_URL', None)
EVOLUTION_API_KEY = getattr(settings, 'EVOLUTION_API_KEY', None)
EVOLUTION_INSTANCE = getattr(settings, 'EVOLUTION_INSTANCE', None)

def clean_phone_number(phone):
    """
    Cleans phone numbers into a WhatsApp-compatible standard format.
    Removes '+', spaces, parenthesis, and dashes.
    Example: +55 (11) 99999-9999 -> 5511999999999
    """
    if not phone:
        return ""
    cleaned = "".join(c for c in str(phone) if c.isdigit())
    return cleaned

def send_whatsapp_otp(phone_number, otp_code):
    """
    Sends an OTP verification code via Evolution API.
    If credentials are missing or the request fails, it falls back to console logging
    to allow locally sandbox-safe testing.
    """
    cleaned_number = clean_phone_number(phone_number)
    message_text = (
        f"🔒 *Nuviie Hub - Recuperação de Senha*\n\n"
        f"Seu código de verificação de segurança (OTP) é: *{otp_code}*\n\n"
        f"Este código é válido por 10 minutos. Se você não solicitou este código, ignore esta mensagem."
    )
    
    # Check if Evolution API is configured
    if not all([EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE]):
        logger.warning("WhatsApp settings not fully configured. SIMULATING OTP SEND.")
        simulated_log = f"\n[WHATSAPP SIMULATOR] Sending OTP to {cleaned_number}: \n{message_text}\n"
        print(simulated_log)
        return True, "Simulated send successfully."

    # Build Evolution API request URL and headers
    # Endpoint typically: {URL}/message/sendText/{instance}
    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }
    # Evolution API v2: campos `text`/`delay`/`linkPreview` ficam na raiz do payload.
    payload = {
        "number": cleaned_number,
        "text": message_text,
        "delay": 500,
        "linkPreview": False,
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            logger.info(f"WhatsApp OTP sent to {cleaned_number} via Evolution API.")
            return True, "Enviado com sucesso via WhatsApp."
        else:
            logger.error(f"Evolution API error: {response.status_code} - {response.text}")
            # Fallback to console print so developers can see the OTP if API fails
            print(f"\n[WHATSAPP FALLBACK] API failed ({response.status_code}). OTP is: {otp_code}\n")
            return False, f"API retornou status {response.status_code}"
    except Exception as e:
        logger.exception("Error connecting to Evolution API")
        print(f"\n[WHATSAPP FALLBACK] Request failed. OTP is: {otp_code}\n")
        return False, str(e)
