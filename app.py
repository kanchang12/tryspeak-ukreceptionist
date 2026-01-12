# =============================================================================
# COMPLETE TRYSPEAK SYSTEM
# - OTP Login
# - Onboarding with 14-day trial
# - Referral system (£25 off)
# - Manager Mode (reads last call + appointments)
# - Receptionist Mode (new callers)
# - Booking appointments via voice
# - Editing appointments via voice (Manager Mode)
# - Call list with AI summaries
# - Appointment calendar
# - Dashboard with stats
# - Stripe subscription (£75/month)
# - Twilio voice webhooks
# - Google Speech-to-Text
# - Google Gemini AI
# - Google Text-to-Speech
# =============================================================================

import os
import json
import base64
import asyncio
import logging
import queue
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv

# Supabase for OTP
from supabase import create_client

# Google AI Stack
from google import genai
from google.genai import types
from google.cloud import speech_v1 as speech
from google.cloud import texttospeech

# Twilio
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.rest import Client as TwilioClient

# Stripe
import stripe

# Auth
import jwt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# Services
from services.sms_service import send_sms
from services.cockroachdb_service import DB

# =============================================================================
# SETUP
# =============================================================================
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# =============================================================================
# CONFIG
# =============================================================================
AUTH_SECRET = os.getenv("AUTH_SECRET", "change-me")
serializer = URLSafeTimedSerializer(AUTH_SECRET)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
supabase_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://tryspeak.site")
stripe.api_key = STRIPE_SECRET_KEY

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

tts_client = texttospeech.TextToSpeechClient()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_bearer_token():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.headers.get("X-Auth-Token") or None


def require_app_auth():
    """Validates app token and returns owner row"""
    token = get_bearer_token()
    if not token:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    try:
        payload = serializer.loads(token, max_age=60 * 60 * 24 * 14)
        owner_id = payload.get("owner_id")
        if not owner_id:
            return None, (jsonify({"error": "Unauthorized"}), 401)
    except (SignatureExpired, BadSignature):
        return None, (jsonify({"error": "Unauthorized"}), 401)

    owner = DB.find_one("business_owners", {"id": owner_id})
    if not owner:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return owner, None


def subscription_gate(owner):
    """Check if user can access (trial or active subscription)"""
    if owner.get("status") != "active":
        return False, "Account inactive"

    sub = owner.get("subscription_status") or "trialing"
    if sub == "active":
        return True, None

    if sub == "trialing":
        trial_ends = owner.get("trial_ends_at")
        if not trial_ends:
            return True, None

        if isinstance(trial_ends, str):
            try:
                trial_ends = datetime.fromisoformat(trial_ends.replace("Z", "+00:00")).replace(tzinfo=None)
            except:
                trial_ends = None

        if not trial_ends:
            return True, None

        if datetime.utcnow() <= trial_ends.replace(tzinfo=None):
            return True, None

        return False, "Trial ended"

    return False, "Subscription inactive"


# =============================================================================
# VOICE CALL HANDLER CLASS
# =============================================================================
class VoiceCallHandler:
    def __init__(self, call_sid, from_number, to_number):
        self.call_sid = call_sid
        self.from_number = from_number
        self.to_number = to_number
        self.transcript = []
        self.audio_queue = queue.Queue()
        self.owner = None
        self.customer = None
        self.conversation_history = []
        self.is_owner = False
        
        # Load context
        self.load_context()
    
    def load_context(self):
        """Load owner and customer data from database"""
        self.owner = DB.find_one("business_owners", {"twilio_phone_number": self.to_number, "status": "active"})
        if not self.owner:
            logger.error(f"No owner found for number {self.to_number}")
            return
        
        # Check if caller is the owner (Manager Mode)
        self.is_owner = (self.from_number == self.owner.get("phone_number"))
        
        if not self.is_owner:
            # Load customer history for Receptionist Mode
            self.customer = DB.find_one("their_customers", {
                "business_owner_id": self.owner["id"],
                "phone_number": self.from_number
            })
            
            if self.customer:
                # Load past calls
                past_calls = DB.find_many(
                    "interactions",
                    where={"customer_id": self.customer["id"]},
                    order_by="created_at DESC",
                    limit=3
                )
                
                # Load upcoming bookings
                bookings = DB.find_many(
                    "bookings",
                    where={"customer_id": self.customer["id"], "status": "pending"},
                    order_by="booking_date ASC",
                    limit=5
                )
                
                self.customer['past_calls'] = past_calls
                self.customer['bookings'] = bookings
    
    def get_system_prompt(self):
        """Generate system prompt based on caller type (Manager vs Receptionist Mode)"""
        now = datetime.utcnow()
        current_date = now.strftime("%A, %d %B %Y")
        current_time = now.strftime("%H:%M")
        
        # Get today's appointment list
        today_bookings = DB.find_many(
            "bookings",
            where={
                "business_owner_id": self.owner["id"],
                "booking_date": now.strftime("%Y-%m-%d"),
                "status": "pending"
            },
            order_by="booking_time ASC"
        )
        
        appointments_today = ", ".join([
            f"{b['customer_name']} at {b['booking_time']}" 
            for b in today_bookings
        ]) if today_bookings else "No appointments today"
        
        if self.is_owner:
            # ==========================================
            # MANAGER MODE
            # ==========================================
            return f"""You are Julian, the loyal British Butler AI for {self.owner.get('business_name')}.

CURRENT DATE/TIME: {current_date} at {current_time}

MANAGER MODE - The boss is calling.

TODAY'S SCHEDULE: {appointments_today}

YOUR JOB:
1. Greet warmly (e.g., 'Ah, the Gaffer—checking in on the troops?')
2. Provide today's schedule
3. Help EDIT appointments if requested
4. Answer questions about bookings and customers
5. Use British wit and professional tone

EDITING APPOINTMENTS:
When the boss wants to change a meeting time, return JSON:
{{"action": "edit_booking", "customer_name": "John Smith", "old_time": "14:00", "new_time": "15:30"}}

TONE: Dry English wit. Use phrases like 'Right then', 'Gaffer', 'Lovely stuff', 'Sorted'.
"""
        else:
            # ==========================================
            # RECEPTIONIST MODE
            # ==========================================
            customer_context = ""
            if self.customer:
                # Returning customer - reference last call
                customer_context = f"RETURNING CUSTOMER: {self.customer.get('name', 'Customer')}\n"
                customer_context += f"Total previous calls: {self.customer.get('total_calls', 0)}\n"
                
                # Include last call summary
                if self.customer.get('past_calls'):
                    last_call = self.customer['past_calls'][0]
                    last_summary = last_call.get('summary', '')[:150]
                    customer_context += f"\nLAST CONVERSATION: {last_summary}\n"
                
                # Include upcoming bookings
                if self.customer.get('bookings'):
                    customer_context += "\nUPCOMING BOOKINGS:\n"
                    for b in self.customer['bookings']:
                        customer_context += f"- {b['booking_date']} at {b['booking_time']}: {b.get('service_type', 'Service')}\n"
            else:
                customer_context = "NEW CUSTOMER - First time calling\n"
            
            return f"""You are Julian, the professional British AI receptionist for {self.owner.get('business_name')}.

CURRENT DATE/TIME: {current_date} at {current_time}

RECEPTIONIST MODE

{customer_context}

TODAY'S SCHEDULE (for reference): {appointments_today}

YOUR JOB:
1. Answer questions about services, pricing, availability
2. Help customers book appointments
3. Check availability against today's schedule
4. Take messages for the owner
5. Handle emergencies appropriately

BOOKING PROCESS:
- Ask for: full name, phone number, preferred date/time, type of service
- If they say "tomorrow", that means {(now + timedelta(days=1)).strftime('%A, %d %B')}
- Check against existing appointments to avoid double-booking
- When you have all details, return JSON:
{{"action": "create_booking", "customer_name": "...", "customer_phone": "...", "booking_date": "YYYY-MM-DD", "booking_time": "HH:MM", "service_type": "..."}}

EMERGENCY KEYWORDS: If you hear "burst pipe", "leak", "flooding", "no power", "sparks", "gas leak", mark as EMERGENCY

TONE: Professional, warm, British accent. Keep responses under 3 sentences unless providing detailed info.
"""
    
    async def process_speech(self, audio_data):
        """Process incoming speech and generate response"""
        try:
            # ==========================================
            # SPEECH-TO-TEXT (Google Cloud Speech)
            # ==========================================
            stt_client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=audio_data)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
                sample_rate_hertz=8000,
                language_code="en-GB",
            )
            
            response = stt_client.recognize(config=config, audio=audio)
            
            if not response.results:
                return None
            
            user_text = response.results[0].alternatives[0].transcript
            
            if not user_text or len(user_text.strip()) < 2:
                return None
                
            self.transcript.append({"role": "user", "content": user_text})
            logger.info(f"User said: {user_text}")
            
            # ==========================================
            # AI RESPONSE (Google Gemini)
            # ==========================================
            ai_response = await self.get_gemini_response(user_text)
            self.transcript.append({"role": "assistant", "content": ai_response})
            
            # ==========================================
            # ACTION DETECTION (Booking/Editing)
            # ==========================================
            if '"action":' in ai_response:
                await self.handle_action(ai_response)
                # Remove JSON from spoken response
                ai_response = ai_response.split('{"action"')[0].strip()
            
            # ==========================================
            # TEXT-TO-SPEECH (Google Cloud TTS)
            # ==========================================
            input_text = texttospeech.SynthesisInput(text=ai_response)
            
            # British male voice
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-GB",
                name="en-GB-Neural2-B",  # British male
                ssml_gender=texttospeech.SsmlVoiceGender.MALE
            )
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MULAW,
                sample_rate_hertz=8000
            )
            
            tts_response = tts_client.synthesize_speech(
                request={
                    "input": input_text,
                    "voice": voice,
                    "audio_config": audio_config
                }
            )
            
            return tts_response.audio_content
            
        except Exception as e:
            logger.error(f"Speech processing error: {e}")
            return None
    
    async def get_gemini_response(self, user_text):
        """Get response from Gemini AI"""
        try:
            # Build conversation with system prompt first
            contents = [types.Content(
                role="user",
                parts=[types.Part(text=self.get_system_prompt())]
            )]
            
            # Add conversation history (last 10 messages)
            for msg in self.conversation_history[-10:]:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])]
                ))
            
            # Add current user message
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=user_text)]
            ))
            
            # Generate response
            response = gemini_client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=contents
            )
            
            ai_text = response.text
            
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": ai_text})
            
            return ai_text
            
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return "I apologize, I'm having a technical moment. Could you repeat that?"
    
    async def handle_action(self, response_text):
        """Handle booking/editing actions from AI response"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{"action"')
            json_str = response_text[json_start:]
            action_data = json.loads(json_str)
            
            action = action_data.get("action")
            
            if action == "create_booking":
                # ==========================================
                # CREATE BOOKING
                # ==========================================
                # Find or create customer
                customer = DB.find_one("their_customers", {
                    "business_owner_id": self.owner["id"],
                    "phone_number": action_data.get("customer_phone", self.from_number)
                })
                
                if not customer:
                    customer = DB.insert("their_customers", {
                        "business_owner_id": self.owner["id"],
                        "phone_number": action_data.get("customer_phone", self.from_number),
                        "name": action_data.get("customer_name", "Unknown"),
                        "total_calls": 0
                    })
                
                # Create booking
                DB.insert("bookings", {
                    "business_owner_id": self.owner["id"],
                    "customer_id": customer["id"],
                    "customer_name": action_data.get("customer_name"),
                    "customer_phone": action_data.get("customer_phone", self.from_number),
                    "booking_date": action_data.get("booking_date"),
                    "booking_time": action_data.get("booking_time"),
                    "service_type": action_data.get("service_type", "General"),
                    "notes": action_data.get("notes", ""),
                    "status": "pending"
                })
                
                # Notify owner
                send_sms(
                    to=self.owner["phone_number"],
                    message=f"📅 NEW BOOKING\n{action_data.get('customer_name')}\n{action_data.get('booking_date')} at {action_data.get('booking_time')}\n{action_data.get('service_type')}"
                )
                
                logger.info(f"Booking created: {action_data}")
            
            elif action == "edit_booking":
                # ==========================================
                # EDIT BOOKING (Manager Mode)
                # ==========================================
                customer_name = action_data.get("customer_name")
                old_time = action_data.get("old_time")
                new_time = action_data.get("new_time")
                
                # Find booking by customer name and old time
                booking = DB.find_one("bookings", {
                    "business_owner_id": self.owner["id"],
                    "customer_name": customer_name,
                    "booking_time": old_time,
                    "status": "pending"
                })
                
                if booking:
                    DB.update("bookings", {"id": booking["id"]}, {
                        "booking_time": new_time
                    })
                    
                    logger.info(f"Booking edited: {customer_name} moved from {old_time} to {new_time}")
                
        except Exception as e:
            logger.error(f"Action handling error: {e}")
    
    def save_call_log(self, duration):
        """Save call to database after completion"""
        try:
            # Find/create customer
            customer = DB.find_one("their_customers", {
                "business_owner_id": self.owner["id"],
                "phone_number": self.from_number
            })
            
            if customer:
                DB.update("their_customers", {"id": customer["id"]}, {
                    "total_calls": customer.get("total_calls", 0) + 1
                })
                customer_id = customer["id"]
            else:
                new_customer = DB.insert("their_customers", {
                    "business_owner_id": self.owner["id"],
                    "phone_number": self.from_number,
                    "name": "Owner" if self.is_owner else "New Customer",
                    "total_calls": 1
                })
                customer_id = new_customer["id"]
            
            # Build full transcript
            full_transcript = "\n".join([f"{m['role']}: {m['content']}" for m in self.transcript])
            
            # ==========================================
            # GENERATE AI SUMMARY
            # ==========================================
            try:
                summary_prompt = f"Summarize this call in 1-2 sentences:\n{full_transcript}"
                summary_response = gemini_client.models.generate_content(
                    model='gemini-2.0-flash-exp',
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part(text=summary_prompt)]
                    )]
                )
                ai_summary = summary_response.text
            except:
                ai_summary = full_transcript[:200]
            
            # Detect emergency
            emergency_keywords = ["emergency", "burst", "leak", "flooding", "sparks", "gas leak"]
            is_emergency = any(kw in full_transcript.lower() for kw in emergency_keywords)
            
            # Detect booking
            is_booking = "create_booking" in full_transcript
            
            # Save interaction
            DB.insert("interactions", {
                "vapi_call_id": self.call_sid,
                "business_owner_id": self.owner["id"],
                "customer_id": customer_id,
                "type": "owner_test" if self.is_owner else ("booking" if is_booking else "inbound_call"),
                "caller_phone": self.from_number,
                "call_duration": duration,
                "recording_url": "",
                "transcript": full_transcript,
                "summary": ai_summary,
                "is_emergency": is_emergency
            })
            
            if is_emergency and not self.is_owner:
                send_sms(
                    to=self.owner["phone_number"],
                    message=f"🚨 EMERGENCY CALL\n{self.from_number}\n{full_transcript[:100]}"
                )
            
            logger.info(f"Call logged: {self.call_sid}")
            
        except Exception as e:
            logger.error(f"Call log error: {e}")


# =============================================================================
# TWILIO WEBHOOKS
# =============================================================================
@app.route("/api/twilio/voice", methods=["POST"])
def twilio_voice():
    """Handle incoming call from Twilio"""
    from_number = request.form.get("From")
    to_number = request.form.get("To")
    call_sid = request.form.get("CallSid")
    
    logger.info(f"Incoming call: {from_number} -> {to_number} (SID: {call_sid})")
    
    response = VoiceResponse()
    response.say("Please wait while we connect you.", voice="Polly.Brian")
    
    connect = Connect()
    connect.stream(url=f"wss://{request.host}/api/twilio/stream")
    response.append(connect)
    
    return str(response), 200, {'Content-Type': 'text/xml'}


@sock.route('/api/twilio/stream')
def twilio_stream(ws):
    """WebSocket handler for audio streaming"""
    call_sid = None
    from_number = None
    to_number = None
    handler = None
    start_time = datetime.utcnow()
    
    logger.info("WebSocket connected")
    
    try:
        while True:
            message = ws.receive()
            if not message:
                break
            
            data = json.loads(message)
            event = data.get("event")
            
            if event == "start":
                call_sid = data["start"]["callSid"]
                from_number = data["start"]["customParameters"].get("From")
                to_number = data["start"]["customParameters"].get("To")
                
                handler = VoiceCallHandler(call_sid, from_number, to_number)
                logger.info(f"Call started: {call_sid}")
                
                # Send initial greeting
                greeting = "Hello! How can I help you today?"
                
                input_text = texttospeech.SynthesisInput(text=greeting)
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-GB",
                    name="en-GB-Neural2-B",
                    ssml_gender=texttospeech.SsmlVoiceGender.MALE
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MULAW,
                    sample_rate_hertz=8000
                )
                tts_response = tts_client.synthesize_speech(
                    request={"input": input_text, "voice": voice, "audio_config": audio_config}
                )
                
                # Send audio to Twilio
                audio_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
                ws.send(json.dumps({
                    "event": "media",
                    "media": {"payload": audio_base64}
                }))
            
            elif event == "media" and handler:
                # Incoming audio from caller
                payload = data["media"]["payload"]
                audio_data = base64.b64decode(payload)
                
                # Process speech asynchronously
                loop = asyncio.new_event_loop()
                response_audio = loop.run_until_complete(handler.process_speech(audio_data))
                loop.close()
                
                if response_audio:
                    audio_base64 = base64.b64encode(response_audio).decode('utf-8')
                    ws.send(json.dumps({
                        "event": "media",
                        "media": {"payload": audio_base64}
                    }))
            
            elif event == "stop":
                if handler:
                    duration = int((datetime.utcnow() - start_time).total_seconds())
                    handler.save_call_log(duration)
                logger.info(f"Call ended: {call_sid}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ws.close()


# =============================================================================
# HTML PAGES
# =============================================================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/calls")
def calls_page():
    return render_template("calls.html")

@app.route("/admin")
def admin_page():
    return render_template("admin_dashboard.html")


# =============================================================================
# AUTH - OTP LOGIN
# =============================================================================
@app.route("/api/auth/request-otp", methods=["POST"])
def api_auth_request_otp():
    """Send OTP to user's phone"""
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    
    if not phone or not phone.startswith("+"):
        return jsonify({"error": "Phone must include country code"}), 400
    
    owner = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
    if not owner:
        return jsonify({"error": "No account for this phone"}), 404
    
    try:
        supabase_anon.auth.sign_in_with_otp({"phone": phone})
        return jsonify({"status": "sent"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/verify-otp", methods=["POST"])
def api_auth_verify_otp():
    """Verify OTP and return auth token"""
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()
    
    if not phone or not otp:
        return jsonify({"error": "Missing phone or otp"}), 400
    
    try:
        out = supabase_anon.auth.verify_otp({"phone": phone, "token": otp, "type": "sms"})
        session = getattr(out, "session", None)
        if not session or not session.access_token:
            return jsonify({"error": "Invalid OTP"}), 401
        
        owner = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
        if not owner:
            return jsonify({"error": "No account for this phone"}), 403
        
        ok, msg = subscription_gate(owner)
        if not ok:
            return jsonify({"error": msg, "needs_payment": True}), 402
        
        token = serializer.dumps({"owner_id": owner["id"]})
        return jsonify({"token": token, "owner_id": owner["id"]}), 200
    except Exception as e:
        logger.error(f"OTP verify error: {e}")
        return jsonify({"error": str(e)}), 400


# =============================================================================
# ONBOARDING & REGISTRATION
# =============================================================================
@app.route("/api/admin/onboarding/<onboarding_id>/create-account", methods=["POST"])
def create_account_from_onboarding(onboarding_id):
    """Admin creates account with 14-day free trial and referral code"""
    try:
        onboarding = DB.find_one("onboarding_calls", {"id": onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404

        business_name = onboarding["signup_name"]
        business_type = onboarding["business_type"]
        
        # Generate referral code
        referral_code = f"{business_name.upper().replace(' ', '-')}-{onboarding['signup_phone'][-4:]}"
        
        # Check who referred them
        referred_by_code = None
        signup = DB.find_one("signups", {"phone_number": onboarding["signup_phone"]})
        if signup:
            referred_by_code = signup.get("referral_code_used")
        
        # Create business owner with 14-day trial
        owner_data = {
            "email": onboarding.get("signup_email", ""),
            "phone_number": onboarding["signup_phone"],
            "business_name": business_name,
            "business_type": business_type,
            "twilio_phone_number": None,  # Admin assigns later
            "referral_code": referral_code,
            "referred_by_code": referred_by_code,
            "subscription_status": "trialing",
            "trial_ends_at": datetime.utcnow() + timedelta(days=14),
            "status": "active",
        }
        
        owner = DB.insert("business_owners", owner_data)
        
        DB.update(
            "onboarding_calls",
            {"id": onboarding_id},
            {"status": "completed", "business_owner_id": owner["id"]},
        )
        
        # SMS notification
        send_sms(
            to=onboarding["signup_phone"],
            message=f"""Account created! 🎉

14-day FREE trial starts now.

Admin will assign your phone number.

Your referral code: {referral_code}
Each referral = £25 off!

Login: {APP_BASE_URL}/login"""
        )
        
        return jsonify({
            "status": "success",
            "owner_id": owner["id"],
            "referral_code": referral_code,
            "trial_ends": owner_data["trial_ends_at"].isoformat()
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/assign-number", methods=["POST"])
def assign_twilio_number():
    """Admin manually assigns Twilio number to business owner"""
    data = request.json or {}
    owner_id = data.get("owner_id")
    twilio_number = data.get("twilio_number")
    
    if not owner_id or not twilio_number:
        return jsonify({"error": "Missing owner_id or twilio_number"}), 400
    
    owner = DB.find_one("business_owners", {"id": owner_id})
    if not owner:
        return jsonify({"error": "Owner not found"}), 404
    
    DB.update("business_owners", {"id": owner_id}, {"twilio_phone_number": twilio_number})
    
    # Configure Twilio webhook
    if twilio_client:
        try:
            twilio_client.incoming_phone_numbers.list(phone_number=twilio_number)[0].update(
                voice_url=f"{APP_BASE_URL}/api/twilio/voice",
                voice_method='POST'
            )
        except:
            pass
    
    # Send SMS with number
    send_sms(
        to=owner["phone_number"],
        message=f"""Your AI receptionist is ready! 🎉

Forward calls to: {twilio_number}

Dial *21*{twilio_number}# to activate call forwarding.

Login: {APP_BASE_URL}/login

Referral code: {owner.get('referral_code')}"""
    )
    
    return jsonify({"status": "success", "phone_number": twilio_number}), 200


# =============================================================================
# REFERRAL SYSTEM
# =============================================================================
@app.route("/api/referrals/check", methods=["POST"])
def check_referral_code():
    """Validate referral code and return referrer info"""
    data = request.json or {}
    code = data.get("code", "").strip().upper()
    
    if not code:
        return jsonify({"valid": False}), 200
    
    referrer = DB.find_one("business_owners", {"referral_code": code})
    if referrer:
        return jsonify({
            "valid": True,
            "referrer_name": referrer.get("business_name"),
            "discount": 25  # £25 off first month for BOTH parties
        }), 200
    
    return jsonify({"valid": False}), 200


@app.route("/api/referrals/stats", methods=["GET"])
def get_referral_stats():
    """Get referral statistics and earnings"""
    owner, err = require_app_auth()
    if err:
        return err
    
    # Count referrals
    referrals = DB.find_many("business_owners", {"referred_by_code": owner.get("referral_code")})
    
    # Calculate earnings (£25 per active referral)
    active_referrals = [r for r in referrals if r.get("subscription_status") == "active"]
    total_referrals = len(referrals)
    total_earnings = len(active_referrals) * 25
    
    return jsonify({
        "referral_code": owner.get("referral_code"),
        "total_referrals": total_referrals,
        "active_referrals": len(active_referrals),
        "total_earnings": total_earnings,
        "referrals": [{
            "business_name": r.get("business_name"),
            "created_at": r.get("created_at"),
            "status": r.get("subscription_status")
        } for r in referrals]
    }), 200


# =============================================================================
# DASHBOARD APIS
# =============================================================================
@app.route("/api/customer/dashboard", methods=["GET"])
def get_customer_dashboard():
    """Get dashboard stats"""
    owner, err = require_app_auth()
    if err:
        return err
    
    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402
    
    try:
        today = datetime.utcnow().date().isoformat()
        
        # Get all interactions
        interactions = DB.find_many(
            "interactions",
            where={"business_owner_id": owner["id"]},
            order_by="created_at DESC",
            limit=100
        )
        
        # Filter today's calls
        today_calls = [i for i in interactions if i.get("created_at", "").startswith(today)]
        
        calls_today = len(today_calls)
        emergencies_today = sum(1 for i in today_calls if i.get("is_emergency"))
        bookings_today = sum(1 for i in today_calls if i.get("type") == "booking")
        
        return jsonify({
            "calls_today": calls_today,
            "emergencies_today": emergencies_today,
            "bookings_today": bookings_today,
            "business_name": owner.get("business_name") or "Your Business",
            "vapi_phone_number": owner.get("twilio_phone_number"),
            "referral_code": owner.get("referral_code"),
            "subscription_status": owner.get("subscription_status") or "trialing",
            "trial_ends_at": owner.get("trial_ends_at"),
        }), 200
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/customer/calls", methods=["GET"])
def get_customer_calls():
    """Get call history with AI summaries"""
    owner, err = require_app_auth()
    if err:
        return err
    
    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402
    
    try:
        limit = int(request.args.get("limit", 20))
        calls = DB.find_many(
            "interactions",
            where={"business_owner_id": owner["id"]},
            order_by="created_at DESC",
            limit=limit,
        )
        return jsonify(calls), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/customer/bookings", methods=["GET"])
def get_bookings():
    """Get appointment list"""
    owner, err = require_app_auth()
    if err:
        return err
    
    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402
    
    try:
        bookings = DB.find_many(
            "bookings",
            where={"business_owner_id": owner["id"]},
            order_by="booking_date ASC",
            limit=100
        )
        return jsonify(bookings), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/customer/call-forwarding", methods=["GET", "POST"])
def call_forwarding_toggle():
    """Toggle call forwarding"""
    owner, err = require_app_auth()
    if err:
        return err
    
    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402
    
    if request.method == "GET":
        return jsonify({
            "enabled": owner.get("call_forwarding_enabled", False),
            "forwarding_number": owner.get("forwarding_number", ""),
            "vapi_number": owner.get("twilio_phone_number", "")
        }), 200
    
    data = request.json or {}
    enabled = data.get("enabled", False)
    forwarding_number = data.get("forwarding_number", "")
    
    DB.update("business_owners", {"id": owner["id"]}, {
        "call_forwarding_enabled": enabled,
        "forwarding_number": forwarding_number
    })
    
    return jsonify({"status": "updated", "enabled": enabled}), 200


# =============================================================================
# STRIPE SUBSCRIPTION
# =============================================================================
@app.route("/api/billing/checkout", methods=["POST"])
def api_billing_checkout():
    """Create Stripe checkout session for £75/month subscription"""
    owner, err = require_app_auth()
    if err:
        return err
    
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return jsonify({"error": "Stripe not configured"}), 500
    
    try:
        customer_id = owner.get("stripe_customer_id")
        if not customer_id:
            cust = stripe.Customer.create(
                phone=owner.get("phone_number"),
                metadata={"owner_id": str(owner["id"])},
            )
            customer_id = cust["id"]
            DB.update("business_owners", {"id": owner["id"]}, {"stripe_customer_id": customer_id})
        
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{APP_BASE_URL}/dashboard?paid=1",
            cancel_url=f"{APP_BASE_URL}/dashboard?paid=0",
        )
        return jsonify({"checkout_url": session["url"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/stripe/webhook", methods=["POST"])
def api_stripe_webhook():
    """Handle Stripe subscription webhooks"""
    if not STRIPE_WEBHOOK_SECRET:
        return jsonify({"error": "Stripe webhook not configured"}), 500
    
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
    etype = event["type"]
    obj = event["data"]["object"]
    
    try:
        if etype in ("customer.subscription.created", "customer.subscription.updated"):
            sub_id = obj["id"]
            customer_id = obj["customer"]
            status = obj["status"]
            
            owner = DB.find_one("business_owners", {"stripe_customer_id": customer_id})
            if owner:
                DB.update("business_owners", {"id": owner["id"]}, {
                    "stripe_subscription_id": sub_id,
                    "subscription_status": status
                })
        
        elif etype == "customer.subscription.deleted":
            customer_id = obj["customer"]
            owner = DB.find_one("business_owners", {"stripe_customer_id": customer_id})
            if owner:
                DB.update("business_owners", {"id": owner["id"]}, {"subscription_status": "canceled"})
    except Exception as e:
        return jsonify({"error": str(e)}), 200
    
    return jsonify({"received": True}), 200


# =============================================================================
# ADMIN PANEL
# =============================================================================
@app.route("/api/admin/pending-onboardings", methods=["GET"])
def get_pending_onboardings():
    """Get list of pending onboarding calls"""
    try:
        pending = DB.find_many(
            "onboarding_calls",
            where={"status": "pending"},
            order_by="created_at ASC",
        )
        
        for call in pending:
            created = call.get("created_at")
            if created:
                waiting_hours = (datetime.utcnow() - created).total_seconds() / 3600
                call["hours_waiting"] = round(waiting_hours, 1)
        
        return jsonify(pending), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/onboarding/<onboarding_id>", methods=["GET"])
def get_onboarding_detail(onboarding_id):
    """Get onboarding call details"""
    try:
        onboarding = DB.find_one("onboarding_calls", {"id": onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404
        return jsonify(onboarding), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
