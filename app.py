# main.py - TrySpeak Voice System (Twilio + ElevenLabs + Gemini)
# Replaces VAPI with custom voice agent

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import jwt
import stripe
from supabase import create_client
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import logging
import json
import base64
import asyncio
from threading import Thread
import queue

# Google services
import google.generativeai as genai
from google.cloud import speech_v1 as speech

# ElevenLabs
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

# Twilio
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from services.sms_service import send_sms
from services.cockroachdb_service import DB

logger = logging.getLogger(__name__)
load_dotenv()

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# =============================================================================
# CONFIG
# =============================================================================
AUTH_SECRET = os.getenv("AUTH_SECRET", "change-me")
serializer = URLSafeTimedSerializer(AUTH_SECRET)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
supabase_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://tryspeak-recep-451954006366.europe-west1.run.app")
stripe.api_key = STRIPE_SECRET_KEY

# Voice AI Config
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# Initialize services
genai.configure(api_key=GEMINI_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Julian voice ID (British male)
JULIAN_VOICE_ID = "yBUZAhdyZ3CJHqXPZ3zF"

# =============================================================================
# HELPER FUNCTIONS (Same as before)
# =============================================================================
def get_bearer_token():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.headers.get("X-Auth-Token") or None

def require_app_auth():
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
# VOICE AI HANDLER
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
        
        # Load owner & customer context
        self.load_context()
    
    def load_context(self):
        """Load owner and customer data from database"""
        self.owner = DB.find_one("business_owners", {"twilio_phone_number": self.to_number, "status": "active"})
        if not self.owner:
            logger.error(f"No owner found for number {self.to_number}")
            return
        
        # Check if caller is the owner
        self.is_owner = (self.from_number == self.owner.get("phone_number"))
        
        if not self.is_owner:
            # Load customer history
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
        """Generate system prompt based on caller type"""
        now = datetime.utcnow()
        current_date = now.strftime("%A, %d %B %Y")
        current_time = now.strftime("%H:%M")
        
        if self.is_owner:
            # Owner calling - give business intel
            next_booking = DB.find_one(
                "bookings",
                where={"business_owner_id": self.owner["id"], "status": "pending"},
                order_by="booking_date ASC"
            )
            
            schedule = "The calendar is blissfully empty, Gaffer."
            if next_booking:
                schedule = f"Your next appointment is {next_booking.get('customer_name')} at {next_booking.get('booking_time')} on {next_booking.get('booking_date')}."
            
            return f"""You are Julian, the loyal British Butler AI receptionist for {self.owner.get('business_name')}.

CURRENT DATE/TIME: {current_date} at {current_time}

TONE: Dry English wit, professional but warm. Use phrases like 'Right then', 'Gaffer', 'Lovely stuff', and 'Sorted'.

CONTEXT: The boss is calling to check in.
1. Greet warmly (e.g., 'Ah, the Gaffer—couldn't stay away, could you?')
2. Provide today's intel: {schedule}
3. Answer questions about bookings, schedule, or business
4. Be helpful but keep the British humor

RULES:
- Use metric/British terminology
- Keep responses concise (2-3 sentences max)
- If asked to book something, extract: name, phone, date, time, service
- Use JSON format for booking: {{"action": "create_booking", "customer_name": "...", "customer_phone": "...", "booking_date": "YYYY-MM-DD", "booking_time": "HH:MM", "service_type": "..."}}
"""
        else:
            # Customer calling
            customer_context = ""
            if self.customer:
                customer_context = f"RETURNING CUSTOMER: {self.customer.get('name', 'Customer')}\n"
                customer_context += f"Total previous calls: {self.customer.get('total_calls', 0)}\n"
                
                if self.customer.get('bookings'):
                    customer_context += "\nUPCOMING BOOKINGS:\n"
                    for b in self.customer['bookings']:
                        customer_context += f"- {b['booking_date']} at {b['booking_time']}: {b.get('service_type', 'Service')}\n"
            else:
                customer_context = "NEW CUSTOMER - First time calling\n"
            
            return f"""You are Julian, the professional British AI receptionist for {self.owner.get('business_name')}.

CURRENT DATE/TIME: {current_date} at {current_time}

{customer_context}

YOUR JOB:
1. Answer questions about services, pricing, availability
2. Help customers book appointments
3. Take messages for the owner
4. Handle emergencies appropriately

BOOKING PROCESS:
- Ask for: full name, phone number, preferred date/time, type of service
- If they say "tomorrow", that means {(now + timedelta(days=1)).strftime('%A, %d %B')}
- When you have all details, return JSON: {{"action": "create_booking", "customer_name": "...", "customer_phone": "...", "booking_date": "YYYY-MM-DD", "booking_time": "HH:MM", "service_type": "..."}}

EMERGENCY KEYWORDS: If you hear "burst pipe", "leak", "flooding", "no power", "sparks", "gas leak", mark as EMERGENCY

TONE: Professional, warm, British accent. Keep responses under 3 sentences.
"""
    
    async def process_speech(self, audio_data):
        """Process incoming speech and generate response"""
        try:
            # Speech-to-Text using Google Cloud Speech
            # Works automatically on Cloud Run (no JSON key needed)
            client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=audio_data)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
                sample_rate_hertz=8000,
                language_code="en-GB",
            )
            
            response = client.recognize(config=config, audio=audio)
            
            if not response.results:
                return None
            
            user_text = response.results[0].alternatives[0].transcript
            self.transcript.append({"role": "user", "content": user_text})
            logger.info(f"User said: {user_text}")
            
            # Get AI response from Gemini
            ai_response = await self.get_gemini_response(user_text)
            self.transcript.append({"role": "assistant", "content": ai_response})
            
            # Check for booking action
            if '"action": "create_booking"' in ai_response:
                await self.handle_booking(ai_response)
                # Remove JSON from spoken response
                ai_response = ai_response.split('{"action"')[0].strip()
            
            # Convert to speech using ElevenLabs
            audio = elevenlabs_client.text_to_speech.convert(
                voice_id=JULIAN_VOICE_ID,
                text=ai_response,
                model_id="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.75,
                    style=0.5,
                    use_speaker_boost=True
                )
            )
            
            return audio
            
        except Exception as e:
            logger.error(f"Speech processing error: {e}")
            return None
    
    async def get_gemini_response(self, user_text):
        """Get response from Gemini"""
        try:
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            # Build conversation context
            messages = [{"role": "user", "parts": [self.get_system_prompt()]}]
            for msg in self.conversation_history[-10:]:  # Last 10 messages
                messages.append({"role": msg["role"], "parts": [msg["content"]]})
            messages.append({"role": "user", "parts": [user_text]})
            
            response = model.generate_content(messages)
            ai_text = response.text
            
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": ai_text})
            
            return ai_text
            
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return "I apologize, I'm having a technical moment. Could you repeat that?"
    
    async def handle_booking(self, response_text):
        """Extract booking from AI response and save to DB"""
        try:
            # Extract JSON from response
            json_start = response_text.find('{"action"')
            json_str = response_text[json_start:]
            booking_data = json.loads(json_str)
            
            if booking_data.get("action") != "create_booking":
                return
            
            # Find or create customer
            customer = DB.find_one("their_customers", {
                "business_owner_id": self.owner["id"],
                "phone_number": booking_data.get("customer_phone", self.from_number)
            })
            
            if not customer:
                customer = DB.insert("their_customers", {
                    "business_owner_id": self.owner["id"],
                    "phone_number": booking_data.get("customer_phone", self.from_number),
                    "name": booking_data.get("customer_name", "Unknown"),
                    "total_calls": 0
                })
            
            # Create booking
            DB.insert("bookings", {
                "business_owner_id": self.owner["id"],
                "customer_id": customer["id"],
                "customer_name": booking_data.get("customer_name"),
                "customer_phone": booking_data.get("customer_phone", self.from_number),
                "booking_date": booking_data.get("booking_date"),
                "booking_time": booking_data.get("booking_time"),
                "service_type": booking_data.get("service_type", "General"),
                "notes": "",
                "status": "pending"
            })
            
            # Notify owner
            send_sms(
                to=self.owner["phone_number"],
                message=f"📅 NEW BOOKING\n{booking_data.get('customer_name')}\n{booking_data.get('booking_date')} at {booking_data.get('booking_time')}\n{booking_data.get('service_type')}"
            )
            
            logger.info(f"Booking created: {booking_data}")
            
        except Exception as e:
            logger.error(f"Booking error: {e}")
    
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
                "summary": full_transcript[:200],
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
                audio = elevenlabs_client.text_to_speech.convert(
                    voice_id=JULIAN_VOICE_ID,
                    text=greeting,
                    model_id="eleven_multilingual_v2"
                )
                
                # Send audio to Twilio
                audio_base64 = base64.b64encode(audio).decode('utf-8')
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
# ALL OTHER ROUTES (Same as original app.py)
# =============================================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/signup")
def signup_page():
    return render_template("signup.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/success")
def success_page():
    return render_template("success.html")


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/calls")
def calls_page():
    return render_template("calls.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")

@app.route("/referrals")
def referrals_page():
    return render_template("referrals.html")  # Create this later

# Auth
@app.route("/api/auth/request-otp", methods=["POST"])
def api_auth_request_otp():
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

# Dashboard APIs
@app.route("/api/customer/dashboard", methods=["GET"])
def get_customer_dashboard():
    owner, err = require_app_auth()
    if err:
        return err
    
    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402
    
    try:
        today = datetime.utcnow().date().isoformat()
        interactions = DB.find_many(
            "interactions",
            where={"business_owner_id": owner["id"]},
            order_by="created_at DESC",
            limit=100
        )
        
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

# Stripe billing
@app.route("/api/billing/checkout", methods=["POST"])
def api_billing_checkout():
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

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
   
    app.run(debug=False, host="0.0.0.0", port=5000)
