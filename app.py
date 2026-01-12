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
@app.route("/api/onboarding/start", methods=["POST", "GET"])
def start_onboarding():
    data = request.json

    signup_data = {
        "name": data["name"],
        "email": data.get("email", ""),  # can be blank if you want later
        "phone_number": data["phone"],
        "business_name": data["business"],
        "business_type": data["businessType"],
        "message": data.get("message", ""),
        "referral_code_used": data.get("referralCode"),
        "status": "awaiting_call",
    }

    try:
        DB.insert("signups", signup_data)

        onboarding_phone = os.getenv("VAPI_ONBOARDING_PHONE", "0800 XXX XXX")

        send_sms(
            to=data["phone"],
            message=f"""Hi {data['name']}! Welcome to TrySpeak.

Call this number NOW: {onboarding_phone}

- TrySpeak""",
        )

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/onboarding/webhook/call-ended", methods=["POST", "GET"])
def onboarding_call_ended():
    data = request.json
    call = data.get("call", {})
    customer_phone = call.get("customer", {}).get("number")
    transcript = data.get("transcript", "")
    recording_url = data.get("recordingUrl", "")
    started_at = call.get("startedAt")
    ended_at = call.get("endedAt")

    duration = None
    if started_at and ended_at:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            duration = int((end - start).total_seconds())
        except:
            pass

    try:
        signup = DB.find_one("signups", {"phone_number": customer_phone})
        if not signup:
            return jsonify({"error": "Signup not found"}), 404

        onboarding_data = {
            "signup_email": signup.get("email", ""),
            "signup_phone": customer_phone,
            "signup_name": signup["name"],
            "business_type": signup["business_type"],
            "vapi_call_id": call.get("id"),
            "call_started_at": started_at,
            "call_ended_at": ended_at,
            "call_duration": duration,
            "full_transcript": transcript,
            "recording_url": recording_url,
            "status": "pending",
        }

        DB.insert("onboarding_calls", onboarding_data)

        send_sms(to=customer_phone, message=f"Thanks {signup['name']}! Ready in 2 hours.")

        admin_phone = os.getenv("ADMIN_PHONE")
        if admin_phone:
            send_sms(to=admin_phone, message=f"🔔 New: {signup['name']}")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
@app.route("/api/vapi/call-started", methods=["POST", "GET"])
def customer_call_started():
    logger.info("🔔 VAPI call-started webhook received")
    data = request.json
    logger.info(f"Webhook data: {data}")
    
    call = data.get("call", {})
    to_number = call.get("phoneNumberId")
    from_number = call.get("customer", {}).get("number")

    try:
        owner = DB.find_one("business_owners", {"vapi_phone_number": to_number})
        if not owner:
            logger.warning(f"No owner found for: {to_number}")
            return jsonify({}), 200

        customer = DB.find_one(
            "their_customers",
            {"business_owner_id": owner["id"], "phone_number": from_number}
        )

        if not customer:
            logger.info(f"NEW customer: {from_number}")
            return jsonify({
                "messages": [{
                    "role": "system",
                    "content": f"NEW CUSTOMER calling from {from_number}. First time calling. Greet warmly."
                }]
            }), 200

        past_calls = DB.find_many(
            "interactions",
            where={"customer_id": customer["id"]},
            order_by="created_at DESC",
            limit=3
        )

        if past_calls:
            last_call = past_calls[0]
            last_summary = last_call.get("summary") or last_call.get("transcript", "")[:150]
            
            history_lines = []
            for call in past_calls:
                date = str(call.get("created_at", ""))[:10]
                summary = call.get("summary", "No details")[:80]
                history_lines.append(f"- {date}: {summary}")

            context = f"""RETURNING CUSTOMER: {customer.get('name', 'Customer')}
Phone: {from_number}
Total calls: {customer.get('total_calls', 0)}

LAST CALL: {last_summary}

HISTORY:
{chr(10).join(history_lines)}

Acknowledge their history and ask if this is a follow-up."""
        else:
            context = f"RETURNING CUSTOMER: {from_number}. Total calls: {customer.get('total_calls', 0)}"

        logger.info(f"✅ Context sent for customer {customer['id']}")
        
        return jsonify({
            "messages": [{
                "role": "system",
                "content": context
            }]
        }), 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({}), 200


@app.route("/api/vapi/call-ended", methods=["POST", "GET"])
def customer_call_ended():
    logger.info("🔔 VAPI call-ended webhook received")
    data = request.json
    
    call = data.get("call", {})
    to_number = call.get("phoneNumberId")
    from_number = call.get("customer", {}).get("number")
    transcript = data.get("transcript", "")
    recording_url = data.get("recordingUrl", "")
    duration = call.get("duration", 0)

    try:
        owner = DB.find_one("business_owners", {"vapi_phone_number": to_number})
        if not owner:
            logger.error(f"No owner for: {to_number}")
            return jsonify({"error": "Not found"}), 404

        customer = DB.find_one(
            "their_customers",
            {"business_owner_id": owner["id"], "phone_number": from_number}
        )

        if customer:
            updated_calls = customer.get("total_calls", 0) + 1
            DB.update(
                "their_customers",
                {"id": customer["id"]},
                {"total_calls": updated_calls}
            )
            customer_id = customer["id"]
        else:
            new_customer = DB.insert(
                "their_customers",
                {"business_owner_id": owner["id"], "phone_number": from_number, "total_calls": 1}
            )
            customer_id = new_customer["id"]

        emergency_keywords = ["burst", "leak", "emergency", "urgent", "flooding", "sparks"]
        is_emergency = any(kw in transcript.lower() for kw in emergency_keywords)

        DB.insert(
            "interactions",
            {
                "business_owner_id": owner["id"],
                "customer_id": customer_id,
                "type": "inbound_call",
                "caller_phone": from_number,
                "call_duration": duration,
                "recording_url": recording_url,
                "transcript": transcript,
                "summary": transcript[:200],
                "is_emergency": is_emergency,
            }
        )

        logger.info(f"✅ Call saved for customer {customer_id}")

        if is_emergency:
            send_sms(to=owner["phone_number"], message=f"🚨 EMERGENCY: {transcript[:100]}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
