from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
from datetime import datetime
import jwt
from supabase import create_client

load_dotenv()

app = Flask(__name__)
CORS(app)

from services.cockroachdb_service import DB
from services.vapi_service import create_vapi_assistant
from services.sms_service import send_sms
from services.prompt_generator import generate_assistant_prompt

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]

supabase_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================================================================
# HTML PAGES
# ============================================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/success')
def success_page():
    return render_template('success.html')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')

@app.route('/calls')
def calls_page():
    return render_template('calls.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# ============================================================================
# API ROUTES
# ============================================================================
import os
from flask import request, jsonify
from werkzeug.security import check_password_hash
from itsdangerous import URLSafeTimedSerializer

AUTH_SECRET = os.getenv("AUTH_SECRET", "change-me")
serializer = URLSafeTimedSerializer(AUTH_SECRET)


import secrets
from datetime import datetime, timedelta



@app.route("/api/auth/request-otp", methods=["POST"])
def api_auth_request_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()

    if not phone or not phone.startswith("+"):
        return jsonify({"error": "Phone must include country code, e.g. +447..." }), 400

    # ✅ IMPORTANT: allow OTP send ONLY if business exists
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
        out = supabase_anon.auth.verify_otp({
            "phone": phone,
            "token": otp,
            "type": "sms"
        })

        session = getattr(out, "session", None)
        if not session or not session.access_token:
            return jsonify({"error": "OTP verified but no session returned"}), 401

        access_token = session.access_token

        # ✅ verify Supabase token and read user id
        decoded = jwt.decode(
            access_token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        auth_user_id = decoded.get("sub")

        if not auth_user_id:
            return jsonify({"error": "Invalid Supabase token"}), 401

        # ✅ MUST be active business owner in your DB
        owner = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
        if not owner:
            return jsonify({"error": "No account for this phone"}), 403

        # optional: store auth_user_id once (so you can map later)
        if not owner.get("auth_user_id"):
            DB.update("business_owners", {"id": owner["id"]}, {"auth_user_id": auth_user_id})

        token = serializer.dumps({"owner_id": owner["id"]})
        return jsonify({"token": token, "owner_id": owner["id"]}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400





@app.route('/api/onboarding/start', methods=['POST'])
def start_onboarding():
    data = request.json
    
    signup_data = {
        'name': data['name'],
        'email': data['email'],
        'phone_number': data['phone'],
        'business_name': data['business'],
        'business_type': data['businessType'],
        'message': data.get('message', ''),
        'referral_code_used': data.get('referralCode'),
        'status': 'awaiting_call'
    }
    
    try:
        DB.insert('signups', signup_data)
        
        onboarding_phone = os.getenv('VAPI_ONBOARDING_PHONE', '0800 XXX XXX')
        
        send_sms(
            to=data['phone'],
            message=f"""Hi {data['name']}! Welcome to TrySpeak.

Call this number NOW: {onboarding_phone}

- TrySpeak"""
        )
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin", methods=["GET", "POST"])
def admin():
    token_ok = False

    if request.method == "POST":
        token = request.form.get("token")
        if token == os.getenv("ADMIN_TOKEN"):
            token_ok = True

    if not token_ok:
        return render_template("admin.html", logged_in=False)

    calls = DB.find_many(
        "onboarding_calls",
        order_by="created_at DESC",
        limit=50
    )

    return render_template("admin.html", logged_in=True, calls=calls)


@app.route('/api/onboarding/webhook/call-ended', methods=['POST'])
def onboarding_call_ended():
    data = request.json
    call = data.get('call', {})
    customer_phone = call.get('customer', {}).get('number')
    transcript = data.get('transcript', '')
    recording_url = data.get('recordingUrl', '')
    started_at = call.get('startedAt')
    ended_at = call.get('endedAt')
    
    duration = None
    if started_at and ended_at:
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
            duration = int((end - start).total_seconds())
        except:
            pass
    
    try:
        signup = DB.find_one('signups', {'phone_number': customer_phone})
        if not signup:
            return jsonify({"error": "Signup not found"}), 404
        
        onboarding_data = {
            'signup_email': signup['email'],
            'signup_phone': customer_phone,
            'signup_name': signup['name'],
            'business_type': signup['business_type'],
            'vapi_call_id': call.get('id'),
            'call_started_at': started_at,
            'call_ended_at': ended_at,
            'call_duration': duration,
            'full_transcript': transcript,
            'recording_url': recording_url,
            'status': 'pending'
        }
        
        DB.insert('onboarding_calls', onboarding_data)
        
        send_sms(to=customer_phone, message=f"Thanks {signup['name']}! Ready in 2 hours.")
        
        admin_phone = os.getenv('ADMIN_PHONE')
        if admin_phone:
            send_sms(to=admin_phone, message=f"🔔 New: {signup['name']}")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/pending-onboardings', methods=['GET'])
def get_pending_onboardings():
    try:
        pending = DB.find_many('onboarding_calls', 
                               where={'status': 'pending'}, 
                               order_by='created_at ASC')
        
        for call in pending:
            created = call.get('created_at')
            if created:
                waiting_hours = (datetime.utcnow() - created).total_seconds() / 3600
                call['hours_waiting'] = round(waiting_hours, 1)
        
        return jsonify(pending), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/onboarding/<onboarding_id>', methods=['GET'])
def get_onboarding_detail(onboarding_id):
    try:
        onboarding = DB.find_one('onboarding_calls', {'id': onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404
        return jsonify(onboarding), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/onboarding/<onboarding_id>/create-assistant', methods=['POST'])
def create_assistant_from_onboarding(onboarding_id):
    try:
        onboarding = DB.find_one('onboarding_calls', {'id': onboarding_id})
        if not onboarding:
            return jsonify({"error": "Not found"}), 404
        
        transcript = onboarding['full_transcript']
        business_type = onboarding['business_type']
        business_name = onboarding['signup_name']
        
        system_prompt = generate_assistant_prompt(transcript, business_type, business_name)
        
        assistant = create_vapi_assistant(
            name=f"{business_name} Receptionist",
            system_prompt=system_prompt,
            voice_id="XB0fDUnXU5powFXDhCwa"
        )
        
        referral_code = f"{business_name.upper().replace(' ', '-')}-{onboarding['signup_phone'][-4:]}"
        
        owner_data = {
            'email': onboarding['signup_email'],
            'phone_number': onboarding['signup_phone'],
            'business_name': business_name,
            'business_type': business_type,
            'vapi_assistant_id': assistant['id'],
            'vapi_phone_number': assistant['phoneNumber'],
            'referral_code': referral_code,
            'status': 'active'
        }
        
        owner = DB.insert('business_owners', owner_data)
        
        DB.update('onboarding_calls', 
                 {'id': onboarding_id}, 
                 {'status': 'completed', 'business_owner_id': owner['id']})
        
        temp_password = f"TrySpeak{onboarding['signup_phone'][-4:]}"
        
        send_sms(
            to=onboarding['signup_phone'],
            message=f"""Ready! 🎉

Forward to: {assistant['phoneNumber']}

Login: {onboarding['signup_email']}
Pass: {temp_password}

Code: {referral_code}"""
        )
        
        return jsonify({
            "status": "success",
            "phone_number": assistant['phoneNumber']
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vapi/call-started', methods=['POST'])
def customer_call_started():
    data = request.json
    call = data.get('call', {})
    to_number = call.get('phoneNumberId')
    from_number = call.get('customer', {}).get('number')
    
    try:
        owner = DB.find_one('business_owners', {'vapi_phone_number': to_number})
        if not owner:
            return jsonify({"context": ""}), 200
        
        customer = DB.find_one('their_customers', {
            'business_owner_id': owner['id'],
            'phone_number': from_number
        })
        
        context = ""
        if customer:
            context = f"Returning customer: {customer.get('name', 'this customer')}. "
        
        return jsonify({"context": context}), 200
    except:
        return jsonify({"context": ""}), 200


@app.route('/api/vapi/call-ended', methods=['POST'])
def customer_call_ended():
    data = request.json
    call = data.get('call', {})
    to_number = call.get('phoneNumberId')
    from_number = call.get('customer', {}).get('number')
    transcript = data.get('transcript', '')
    recording_url = data.get('recordingUrl', '')
    duration = call.get('duration', 0)
    
    try:
        owner = DB.find_one('business_owners', {'vapi_phone_number': to_number})
        if not owner:
            return jsonify({"error": "Not found"}), 404
        
        customer = DB.find_one('their_customers', {
            'business_owner_id': owner['id'],
            'phone_number': from_number
        })
        
        if customer:
            DB.query(
                "UPDATE their_customers SET total_calls = total_calls + 1 WHERE id = %s",
                [customer['id']]
            )
            customer_id = customer['id']
        else:
            new_customer = DB.insert('their_customers', {
                'business_owner_id': owner['id'],
                'phone_number': from_number,
                'total_calls': 1
            })
            customer_id = new_customer['id']
        
        emergency_keywords = ['burst', 'leak', 'emergency', 'urgent', 'flooding', 'sparks']
        is_emergency = any(kw in transcript.lower() for kw in emergency_keywords)
        
        DB.insert('interactions', {
            'business_owner_id': owner['id'],
            'customer_id': customer_id,
            'type': 'inbound_call',
            'caller_phone': from_number,
            'call_duration': duration,
            'recording_url': recording_url,
            'transcript': transcript,
            'summary': transcript[:200],
            'is_emergency': is_emergency
        })
        
        if is_emergency:
            send_sms(to=owner['phone_number'], message=f"🚨 EMERGENCY: {transcript[:100]}")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/dashboard', methods=['GET'])
def get_customer_dashboard():
    owner_id = request.headers.get('X-Owner-ID')
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        stats = DB.query(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_emergency THEN 1 ELSE 0 END) as emergencies,
                SUM(CASE WHEN type = 'booking' THEN 1 ELSE 0 END) as bookings
               FROM interactions 
               WHERE business_owner_id = %s 
               AND created_at >= CURRENT_DATE""",
            [owner_id]
        )[0]
        
        owner = DB.find_one('business_owners', {'id': owner_id})
        
        return jsonify({
            "calls_today": stats['total'],
            "emergencies_today": stats['emergencies'],
            "bookings_today": stats['bookings'],
            "business_name": owner.get('business_name') if owner else 'Your Business'
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/calls', methods=['GET'])
def get_customer_calls():
    owner_id = request.headers.get('X-Owner-ID')
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        limit = int(request.args.get('limit', 20))
        calls = DB.find_many('interactions', 
                            where={'business_owner_id': owner_id}, 
                            order_by='created_at DESC', 
                            limit=limit)
        return jsonify(calls), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
