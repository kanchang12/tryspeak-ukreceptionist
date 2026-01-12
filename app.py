# app.py  (FINAL)
# - Supabase OTP login (phone)
# - Referral stored
# - 14-day trial + Stripe subscription (checkout + webhook)
# - Subscription gate on login + customer APIs
#
# ENV required:
#   AUTH_SECRET
#   ADMIN_TOKEN
#   SUPABASE_URL
#   SUPABASE_ANON_KEY
#   SUPABASE_JWT_SECRET
#   STRIPE_SECRET_KEY
#   STRIPE_WEBHOOK_SECRET
#   STRIPE_PRICE_ID
#   APP_BASE_URL   (default https://tryspeak.site)
#   VAPI_ONBOARDING_PHONE
#   ADMIN_PHONE (optional)
#
# DB tables assumed:
#   signups (has referral_code_used)
#   onboarding_calls
#   business_owners:
#     id, phone_number, vapi_phone_number, business_name, business_type, vapi_assistant_id,
#     referral_code, referred_by_code,
#     subscription_status, trial_ends_at,
#     stripe_customer_id, stripe_subscription_id,
#     status
#
# NOTE: OTP SMS is handled by Supabase/Twilio. Your send_sms() is NOT used for OTP.

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

import jwt
import stripe
from supabase import create_client
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import logging
from services.sms_service import send_sms
from services.vapi_service import create_vapi_assistant, generate_assistant_prompt

logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
CORS(app)

from services.cockroachdb_service import DB

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
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://tryspeak.site")

stripe.api_key = STRIPE_SECRET_KEY


# =============================================================================
# HELPERS
# =============================================================================
def get_bearer_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # fallback: old style
    return request.headers.get("X-Auth-Token") or None


def require_app_auth():
    """
    Validates YOUR app token (itsdangerous) and returns owner row.
    Frontend should send: Authorization: Bearer <token>
    """
    token = get_bearer_token()
    if not token:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    try:
        payload = serializer.loads(token, max_age=60 * 60 * 24 * 14)  # 14 days
        owner_id = payload.get("owner_id")
        if not owner_id:
            return None, (jsonify({"error": "Unauthorized"}), 401)
    except SignatureExpired:
        return None, (jsonify({"error": "Session expired"}), 401)
    except BadSignature:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    owner = DB.find_one("business_owners", {"id": owner_id})
    if not owner:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    return owner, None


def subscription_gate(owner):
    """
    Returns (ok:bool, message:str|None)
    """
    # if you want to allow even when status field is inactive, remove this
    if owner.get("status") != "active":
        return False, "Account inactive"

    sub = owner.get("subscription_status") or "trialing"
    if sub == "active":
        return True, None

    if sub == "trialing":
        trial_ends = owner.get("trial_ends_at")
        if not trial_ends:
            return True, None

        # normalize
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


def decode_supabase_access_token(access_token: str):
    """
    Verify Supabase JWT and return dict with at least {"sub": "...", "phone": "+44..."}.
    """
    decoded = jwt.decode(
        access_token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    return decoded


# =============================================================================
# HTML PAGES
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


# =============================================================================
# AUTH (SUPABASE OTP)
# =============================================================================
@app.route("/api/auth/request-otp", methods=["POST", "GET"])
def api_auth_request_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()

    if not phone or not phone.startswith("+"):
        return jsonify({"error": "Phone must include country code, e.g. +447..." }), 400

    # Allow OTP only if business owner exists
    owner = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
    if not owner:
        return jsonify({"error": "No account for this phone"}), 404

    try:
        supabase_anon.auth.sign_in_with_otp({"phone": phone})
        return jsonify({"status": "sent"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/verify-otp", methods=["POST", "GET"])
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

        # ✅ Skip JWT decode, Supabase already validated it
        # Just get user from session
        user = getattr(out, "user", None)
        if not user:
            return jsonify({"error": "No user found"}), 401

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
# BILLING (STRIPE)
# =============================================================================
@app.route("/api/billing/checkout", methods=["POST", "GET"])
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


@app.route("/api/stripe/webhook", methods=["POST", "GET"])
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
            status = obj["status"]  # active, trialing, past_due, canceled, unpaid...

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
        # Don't fail the webhook hard; Stripe retries anyway
        return jsonify({"error": str(e)}), 200

    return jsonify({"received": True}), 200


# =============================================================================
# ONBOARDING
# =============================================================================





# =============================================================================
# ADMIN (TOKEN FORM + PENDING LIST API)
# =============================================================================
@app.route("/admin", methods=["GET", "POST"])
def admin():
    token_ok = False
    if request.method == "POST":
        token = request.form.get("token")
        if token and token == os.getenv("ADMIN_TOKEN"):
            token_ok = True

    if not token_ok:
        return render_template("admin.html", logged_in=False)

    calls = DB.find_many("onboarding_calls", order_by="created_at DESC", limit=50)
    return render_template("admin.html", logged_in=True, calls=calls)


@app.route("/api/admin/pending-onboardings", methods=["GET"])
def get_pending_onboardings():
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
    try:
        onboarding = DB.find_one("onboarding_calls", {"id": onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404
        return jsonify(onboarding), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/onboarding/<onboarding_id>/create-assistant", methods=["POST", "GET"])
def create_assistant_from_onboarding(onboarding_id):
    try:
        onboarding = DB.find_one("onboarding_calls", {"id": onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404

        transcript = onboarding["full_transcript"]
        business_type = onboarding["business_type"]
        business_name = onboarding["signup_name"]

        system_prompt = generate_assistant_prompt(transcript, business_type, business_name)

        assistant = create_vapi_assistant(
            name=f"{business_name} Receptionist",
            system_prompt=system_prompt,
            voice_id="XB0fDUnXU5powFXDhCwa",
        )

        referral_code = f"{business_name.upper().replace(' ', '-')}-{onboarding['signup_phone'][-4:]}"
        referred_by_code = None

        # pull referral used at signup
        signup = DB.find_one("signups", {"phone_number": onboarding["signup_phone"]})
        if signup:
            referred_by_code = signup.get("referral_code_used")

        owner_data = {
            "email": onboarding.get("signup_email", ""),
            "phone_number": onboarding["signup_phone"],
            "business_name": business_name,
            "business_type": business_type,
            "vapi_assistant_id": assistant["id"],
            "vapi_phone_number": assistant["phoneNumber"],
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

        # Keep this SMS minimal (NO password, because login is OTP)
        send_sms(
            to=onboarding["signup_phone"],
            message=f"""Ready! 🎉

Forward to: {assistant['phoneNumber']}

Login: {APP_BASE_URL}/login
(Use OTP on your mobile)

Referral: {referral_code}""",
        )

        return jsonify({"status": "success", "phone_number": assistant["phoneNumber"]}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# VAPI WEBHOOKS (unchanged)
# =============================================================================

# =============================================================================
# CALL FORWARDING TOGGLE
# =============================================================================
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
            "vapi_number": owner.get("vapi_phone_number", "")
        }), 200

    # POST - Update settings
    data = request.json or {}
    enabled = data.get("enabled", False)
    forwarding_number = data.get("forwarding_number", "")

    DB.update("business_owners", {"id": owner["id"]}, {
        "call_forwarding_enabled": enabled,
        "forwarding_number": forwarding_number
    })

    return jsonify({"status": "updated", "enabled": enabled}), 200


# =============================================================================
# BOOKINGS API
# =============================================================================
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


@app.route("/api/vapi/create-booking", methods=["POST"])
def vapi_create_booking():
    """VAPI calls this when customer books appointment"""
    data = request.get_json(silent=True) or {}
    
    customer_phone = data.get("customer_phone")
    booking_date = data.get("booking_date")
    booking_time = data.get("booking_time")
    customer_name = data.get("customer_name", "Unknown")
    service_type = data.get("service_type", "General")
    notes = data.get("notes", "")
    
    # Get context from VAPI
    call_data = data.get("call", {})
    phoneNumberId = call_data.get("phoneNumberId")
    
    if not phoneNumberId:
        return jsonify({"error": "No phone context"}), 400
    
    owner = DB.find_one("business_owners", {"vapi_phone_number": phoneNumberId})
    if not owner:
        return jsonify({"error": "Owner not found"}), 404
    
    # Find/create customer
    customer = DB.find_one("their_customers", {
        "business_owner_id": owner["id"],
        "phone_number": customer_phone
    })
    if not customer:
        customer = DB.insert("their_customers", {
            "business_owner_id": owner["id"],
            "phone_number": customer_phone,
            "name": customer_name,
            "total_calls": 0
        })
    
    # Create booking
    booking = DB.insert("bookings", {
        "business_owner_id": owner["id"],
        "customer_id": customer["id"],
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "booking_date": booking_date,
        "booking_time": booking_time,
        "service_type": service_type,
        "notes": notes,
        "status": "pending"
    })
    
    # Notify owner
    send_sms(
        to=owner["phone_number"],
        message=f"📅 NEW BOOKING\n{customer_name}\n{booking_date} at {booking_time}\n{service_type}"
    )
    
    return jsonify({
        "success": True,
        "message": f"Booking confirmed for {booking_date} at {booking_time}"
    }), 200

@app.route("/api/vapi/call-started", methods=["POST", "GET"])
def customer_call_started():
    if request.method == "GET":
        return "Webhook ready"
    
    data = request.get_json(silent=True) or {}
    message = data.get("message", {})
    call = message.get("call", {})
    phoneNumber = message.get("phoneNumber", {})
    
    to_number = phoneNumber.get("number")
    from_number = call.get("customer", {}).get("number")

    if not to_number or not from_number:
        return jsonify({}), 200

    owner = DB.find_one("business_owners", {"vapi_phone_number": to_number})
    if not owner:
        return jsonify({}), 200

    # ---------------------------------------------------------
    # OWNER DIFFERENTIATION LOGIC (British Butler Persona)
    # ---------------------------------------------------------
    if from_number == owner.get("phone_number"):
        try:
            # Fetch the very next pending appointment for this owner
            next_booking = DB.find_one(
                "bookings", 
                where={"business_owner_id": owner["id"], "status": "pending"},
                order_by="booking_date ASC, booking_time ASC"
            )
            
            if next_booking:
                schedule_update = (
                    f"Your next client is {next_booking.get('customer_name', 'someone')} "
                    f"at {next_booking.get('booking_time')} for {next_booking.get('service_type', 'a service')}."
                )
            else:
                schedule_update = "The calendar is looking suspiciously empty. A rare moment of peace for you."

            return jsonify({
                "messages": [{
                    "role": "system",
                    "content": f"""
                    IDENTITY: You are the AI personal assistant for {owner.get('business_name')}. 
                    The person you are speaking to is your employer (the Boss).
                    
                    TONE: Heavy English humor. Think dry, witty, and slightly posh—like a loyal but sarcastic British butler. 
                    Use phrases like 'Right then', 'Gaffer', 'Lovely stuff', 'Absolute shambles', or 'A spot of tea'.
                    
                    CURRENT INTEL: {schedule_update}
                    
                    INSTRUCTIONS: 
                    1. Greet the boss with a witty remark about them checking up on you.
                    2. Discreetly mention the next appointment info provided above.
                    3. Ask if they want a summary of the 'local riff-raff' (recent customer calls) or if they're just testing your circuits.
                    """
                }]
            }), 200
        except Exception as e:
            logger.error(f"Error in owner-start logic: {e}")
            # Fallback so the call doesn't drop if DB fails
            return jsonify({"messages": [{"role": "system", "content": "Hello Boss. Systems are nominal."}]}), 200

    # ---------------------------------------------------------
    # REGULAR CUSTOMER LOGIC
    # ---------------------------------------------------------
    customer = DB.find_one("their_customers", {
        "business_owner_id": owner["id"],
        "phone_number": from_number
    })
    
    if not customer:
        return jsonify({
            "messages": [{
                "role": "system",
                "content": f"New customer calling {owner.get('business_name')}. Be professional and helpful."
            }]
        }), 200

    # Returning customer context
    past_calls = DB.find_many("interactions", where={"customer_id": customer["id"]}, order_by="created_at DESC", limit=3)
    
    context = f"RETURNING CUSTOMER: {customer.get('name', 'Customer')}. "
    if past_calls:
        summaries = [c.get("summary", "") for c in past_calls]
        context += f"Last notes: {' | '.join(summaries)}"

    return jsonify({
        "messages": [{
            "role": "system",
            "content": context + "\nWelcome them back warmly."
        }]
    }), 200


@app.route("/api/vapi/call-ended", methods=["POST", "GET"])
def customer_call_ended():
    if request.method == "GET":
        return "Webhook ready"
    
    data = request.get_json(silent=True) or {}
    message = data.get("message", {})
    call = message.get("call", {})
    phoneNumber = message.get("phoneNumber", {})
    
    vapi_call_id = call.get("id")
    to_number = phoneNumber.get("number")
    from_number = call.get("customer", {}).get("number")
    transcript = message.get("transcript", "")
    duration = int(message.get("durationSeconds", 0))
    recording_url = message.get("recordingUrl", "")

    if not to_number or not from_number or not vapi_call_id:
        return jsonify({"status": "ok"}), 200

    # Check for duplicate webhook events
    existing = DB.find_one("interactions", {"vapi_call_id": vapi_call_id})
    if existing:
        return jsonify({"status": "duplicate"}), 200

    owner = DB.find_one("business_owners", {"vapi_phone_number": to_number})
    if not owner:
        return jsonify({"status": "owner_not_found"}), 200

    # ---------------------------------------------------------
    # SKIP LOGGING IF OWNER IS CALLING
    # ---------------------------------------------------------
    if from_number == owner.get("phone_number"):
        return jsonify({"status": "owner_test_not_logged"}), 200

    # Find or create the customer record
    customer = DB.find_one("their_customers", {
        "business_owner_id": owner["id"], 
        "phone_number": from_number
    })
    
    if customer:
        DB.update("their_customers", {"id": customer["id"]}, {
            "total_calls": (customer.get("total_calls") or 0) + 1
        })
        customer_id = customer["id"]
    else:
        new_cust = DB.insert("their_customers", {
            "business_owner_id": owner["id"],
            "phone_number": from_number,
            "total_calls": 1,
            "name": "New Customer"
        })
        customer_id = new_cust["id"]

    # Simple keyword detection for tagging
    is_emergency = any(kw in transcript.lower() for kw in ["emergency", "urgent", "burst", "leak", "flood"])
    is_booking = any(kw in transcript.lower() for kw in ["book", "appointment", "schedule"])

    # Save the interaction
    DB.insert("interactions", {
        "vapi_call_id": vapi_call_id,
        "business_owner_id": owner["id"],
        "customer_id": customer_id,
        "type": "booking" if is_booking else "inbound_call",
        "caller_phone": from_number,
        "call_duration": duration,
        "recording_url": recording_url,
        "transcript": transcript,
        "summary": transcript[:200] if transcript else "No transcript available",
        "is_emergency": is_emergency,
    })

    if is_emergency:
        send_sms(
            to=owner["phone_number"], 
            message=f"🚨 Emergency Alert: A caller is reporting an urgent issue. Transcript: {transcript[:100]}..."
        )

    return jsonify({"status": "success"}), 200

# =============================================================================
# CUSTOMER APIs (auth + subscription gate)
# =============================================================================
@app.route("/api/customer/dashboard", methods=["GET"])

def get_customer_dashboard():
    owner, err = require_app_auth()
    if err:
        return err

    ok, msg = subscription_gate(owner)
    if not ok:
        return jsonify({"error": msg, "needs_payment": True}), 402

    try:
        # ✅ Use Supabase filters instead of broken raw SQL
        today = datetime.utcnow().date().isoformat()
        
        # Get all interactions for this owner
        interactions = DB.find_many(
            "interactions",
            where={"business_owner_id": owner["id"]},
            order_by="created_at DESC",
            limit=100
        )
        
        # Filter today's calls in Python
        today_calls = [i for i in interactions if i.get("created_at", "").startswith(today)]
        
        calls_today = len(today_calls)
        emergencies_today = sum(1 for i in today_calls if i.get("is_emergency"))
        bookings_today = sum(1 for i in today_calls if i.get("type") == "booking")

        return jsonify({
            "calls_today": calls_today,
            "emergencies_today": emergencies_today,
            "bookings_today": bookings_today,
            "business_name": owner.get("business_name") or "Your Business",
            "vapi_phone_number": owner.get("vapi_phone_number"),  # ← ADD THIS
            "referral_code": owner.get("referral_code"),  # ← ADD THIS
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


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = 5000
    app.run(debug=True, host="0.0.0.0", port=port)
