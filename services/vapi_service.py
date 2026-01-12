import os
import requests
import logging

logger = logging.getLogger(__name__)

VAPI_API_KEY = os.getenv("VAPI_API_KEY")
VAPI_BASE_URL = "https://api.vapi.ai"

def create_vapi_assistant(name: str, system_prompt: str, voice_id: str) -> dict:
    """Create VAPI assistant and return {id, phoneNumber}"""
    if not VAPI_API_KEY:
        raise Exception("VAPI_API_KEY not configured")
    
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    assistant_data = {
        "name": name,
        "model": {
            "provider": "openai",
            "model": "gpt-4",
            "messages": [{"role": "system", "content": system_prompt}]
        },
        "voice": {
            "provider": "11labs",
            "voiceId": voice_id
        }
    }
    
    response = requests.post(
        f"{VAPI_BASE_URL}/assistant",
        headers=headers,
        json=assistant_data
    )
    response.raise_for_status()
    assistant = response.json()
    
    phone_data = {
        "assistantId": assistant["id"],
        "name": f"{name} Phone"
    }
    
    phone_response = requests.post(
        f"{VAPI_BASE_URL}/phone-number",
        headers=headers,
        json=phone_data
    )
    phone_response.raise_for_status()
    phone = phone_response.json()
    
    return {
        "id": assistant["id"],
        "phoneNumber": phone.get("number", "")
    }

def generate_assistant_prompt(transcript: str, business_type: str, business_name: str) -> str:
    """Generate system prompt from onboarding transcript"""
    return f"""You are a professional AI receptionist for {business_name}, a {business_type} business.

Based on onboarding: {transcript[:300]}

Handle calls professionally, take bookings, identify emergencies."""
