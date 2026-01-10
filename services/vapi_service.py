import requests
import os

VAPI_API_KEY = os.getenv('VAPI_API_KEY')
VAPI_BASE_URL = "https://api.vapi.ai"
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')


def create_vapi_assistant(name, system_prompt, voice_id):
    """
    Creates a new VAPI assistant with phone number
    """
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Create assistant
    assistant_payload = {
        "name": name,
        "voice": {
            "provider": "elevenlabs",
            "voiceId": voice_id
        },
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                }
            ]
        },
        "firstMessage": "Good morning, thanks for calling. How can I help you today?",
        "endCallMessage": "Brilliant, we'll be in touch. Have a lovely day!",
        "serverUrl": f"{BACKEND_URL}/api/vapi/call-started",
        "endCallFunctionEnabled": True
    }
    
    response = requests.post(
        f"{VAPI_BASE_URL}/assistant",
        headers=headers,
        json=assistant_payload
    )
    response.raise_for_status()
    
    assistant = response.json()
    
    # Provision phone number for this assistant
    phone_payload = {
        "assistantId": assistant['id'],
        "provider": "vapi"  # Use VAPI's built-in Twilio
    }
    
    phone_response = requests.post(
        f"{VAPI_BASE_URL}/phone-number",
        headers=headers,
        json=phone_payload
    )
    phone_response.raise_for_status()
    
    phone_data = phone_response.json()
    assistant['phoneNumber'] = phone_data.get('number', phone_data.get('phoneNumber'))
    
    return assistant


def update_vapi_assistant(assistant_id, system_prompt):
    """
    Updates an existing assistant's prompt
    """
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                }
            ]
        }
    }
    
    response = requests.patch(
        f"{VAPI_BASE_URL}/assistant/{assistant_id}",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    
    return response.json()
