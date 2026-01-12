from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
CORS(app)

# Supabase DB class
from supabase import create_client, Client
import logging
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Client = None
supabase_admin: Client = None

def _ensure_connected():
    global supabase, supabase_admin
    if supabase_admin is None:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("Supabase connected")
        except Exception as e:
            logger.error(f"Supabase init failed: {e}")
            raise

class DB:
    @staticmethod
    def insert(table: str, data: dict):
        _ensure_connected()
        try:
            result = supabase_admin.table(table).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            return None
    
    @staticmethod
    def find_one(table: str, where: dict):
        _ensure_connected()
        try:
            query = supabase_admin.table(table).select('*')
            for key, value in where.items():
                query = query.eq(key, value)
            result = query.limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Find one failed: {e}")
            return None
    
    @staticmethod
    def find_many(table: str, where: dict = None, order_by: str = None, limit: int = None):
        _ensure_connected()
        try:
            query = supabase_admin.table(table).select('*')
            
            if where:
                for key, value in where.items():
                    query = query.eq(key, value)
            
            if order_by:
                parts = order_by.split()
                column = parts[0]
                ascending = len(parts) == 1 or parts[1].upper() == 'ASC'
                query = query.order(column, desc=not ascending)
            
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Find many failed: {e}")
            return []
    
    @staticmethod
    def update(table: str, where: dict, data: dict):
        _ensure_connected()
        try:
            query = supabase_admin.table(table).update(data)
            for key, value in where.items():
                query = query.eq(key, value)
            query.execute()
            return True
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False
    
    @staticmethod
    def delete(table: str, where: dict):
        _ensure_connected()
        try:
            query = supabase_admin.table(table).delete()
            for key, value in where.items():
                query = query.eq(key, value)
            query.execute()
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False
    
    @staticmethod
    def query(sql: str, params: list = None):
        logger.warning("Raw SQL queries not directly supported with Supabase client")
        return []

DB = DB()

# Helper functions
def send_sms(to, message):
    print(f"SMS to {to}: {message}")
    return True

def create_vapi_assistant(name, system_prompt, voice_id):
    return {"id": "asst_stub", "phoneNumber": "+441234567890"}

def generate_assistant_prompt(transcript, business_type, business_name):
    return f"You are a helpful assistant for {business_name}, a {business_type} business."

# ============================================================================
# CUSTOMER PAGES
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

# ============================================================================
# CUSTOMER AUTH API
# ============================================================================

@app.route("/api/auth/send-otp", methods=["POST"])
def send_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    user = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
    
    if not user:
        return jsonify({"error": "Account not found or inactive"}), 404
    
    if not user.get("vapi_phone_number"):
        return jsonify({"error": "Account setup incomplete. Contact support."}), 403
    
    try:
        if supabase:
            supabase.auth.sign_in_with_otp({"phone": phone})
        return jsonify({"status": "OTP sent"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()
    
    if not phone or not otp:
        return jsonify({"error": "Phone and OTP required"}), 400
    
    try:
        if supabase:
            response = supabase.auth.verify_otp({"phone": phone, "token": otp, "type": "sms"})
            
            if not response.user:
                return jsonify({"error": "Invalid OTP"}), 401
            
            user = DB.find_one("business_owners", {"phone_number": phone, "status": "active"})
            
            if not user:
                return jsonify({"error": "Account not found"}), 404
            
            return jsonify({
                "token": response.session.access_token,
                "owner_id": user["id"],
                "refresh_token": response.session.refresh_token
            }), 200
        else:
            return jsonify({"error": "Supabase not configured"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 401

# ============================================================================
# ONBOARDING API
# ============================================================================

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

# ============================================================================
# VAPI WEBHOOKS
# ============================================================================

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
        
        is_owner = (from_number == owner.get('phone_number'))
        
        if is_owner:
            # OWNER calling - get business stats
            today = datetime.utcnow().date().isoformat()
            
            # Get today's bookings
            bookings = DB.find_many('bookings', 
                where={'business_owner_id': owner['id'], 'appointment_date': today},
                order_by='appointment_time ASC',
                limit=5
            )
            
            bookings_text = ""
            if bookings:
                bookings_text = "\nToday's bookings:\n" + "\n".join([
                    f"- {b['customer_name']} at {b['appointment_time']} for {b.get('service', 'service')}"
                    for b in bookings
                ])
            
            context = f"""You are talking to {owner.get('business_name')} owner.{bookings_text}
Help them manage their business."""
            
            return jsonify({"context": context}), 200
        
        # CUSTOMER calling - get their history
        customer = DB.find_one('their_customers', {
            'business_owner_id': owner['id'],
            'phone_number': from_number
        })
        
        context = ""
        if customer:
            # Get upcoming bookings
            today = datetime.utcnow().date().isoformat()
            upcoming = DB.find_many('bookings',
                where={
                    'business_owner_id': owner['id'],
                    'customer_phone': from_number
                },
                order_by='appointment_date ASC',
                limit=3
            )
            
            # Filter for future bookings
            upcoming = [b for b in upcoming if b['appointment_date'] >= today]
            
            if upcoming:
                next_booking = upcoming[0]
                date_obj = datetime.fromisoformat(next_booking['appointment_date'])
                date_str = date_obj.strftime('%A, %B %d')
                context = f"Returning customer {customer.get('name', '')}. Next booking: {date_str} at {next_booking['appointment_time']}. "
            else:
                context = f"Returning customer {customer.get('name', 'this customer')}. No upcoming bookings. "
        
        return jsonify({"context": context}), 200
    except Exception as e:
        logger.error(f"Error in call-started: {e}")
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
            # Update total calls
            DB.update('their_customers', 
                     {'id': customer['id']},
                     {'total_calls': customer.get('total_calls', 0) + 1})
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
        logger.error(f"Error in call-ended: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# CUSTOMER DASHBOARD API
# ============================================================================

def verify_auth():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.split(' ')[1]
    try:
        if supabase:
            user = supabase.auth.get_user(token)
            if user:
                phone = user.user.phone
                owner = DB.find_one('business_owners', {'phone_number': phone})
                return owner['id'] if owner else None
    except:
        return None


@app.route('/api/customer/dashboard', methods=['GET'])
def get_customer_dashboard():
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Get today's interactions for stats
        today = datetime.utcnow().date().isoformat()
        interactions = DB.find_many('interactions',
                                   where={'business_owner_id': owner_id},
                                   limit=100)
        
        # Filter for today and count
        today_interactions = [i for i in interactions if i.get('created_at', '').startswith(today)]
        total_calls = len(today_interactions)
        emergencies = sum(1 for i in today_interactions if i.get('is_emergency'))
        bookings_count = sum(1 for i in today_interactions if i.get('type') == 'booking')
        
        owner = DB.find_one('business_owners', {'id': owner_id})
        
        return jsonify({
            "calls_today": total_calls,
            "emergencies_today": emergencies,
            "bookings_today": bookings_count,
            "business_name": owner.get('business_name') if owner else 'Your Business',
            "vapi_phone_number": owner.get('vapi_phone_number') if owner else None,
            "vapi_assistant_id": owner.get('vapi_assistant_id') if owner else None
        }), 200
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/calls', methods=['GET'])
def get_customer_calls():
    owner_id = verify_auth()
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


@app.route('/api/customer/bookings', methods=['GET'])
def get_bookings():
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        bookings = DB.find_many('bookings', 
                               where={'business_owner_id': owner_id}, 
                               order_by='appointment_date DESC, appointment_time DESC',
                               limit=100)
        return jsonify(bookings), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/bookings', methods=['POST'])
def create_booking():
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    
    booking_data = {
        'business_owner_id': owner_id,
        'customer_name': data['customer_name'],
        'customer_phone': data['customer_phone'],
        'appointment_date': data['appointment_date'],
        'appointment_time': data['appointment_time'],
        'service': data.get('service', ''),
        'notes': data.get('notes', ''),
        'status': 'confirmed'
    }
    
    try:
        booking = DB.insert('bookings', booking_data)
        
        send_sms(
            to=data['customer_phone'],
            message=f"Booking confirmed: {data['appointment_date']} at {data['appointment_time']}. {data.get('service', '')}"
        )
        
        return jsonify(booking), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/bookings/<booking_id>', methods=['PUT'])
def update_booking(booking_id):
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    
    try:
        booking = DB.find_one('bookings', {'id': booking_id, 'business_owner_id': owner_id})
        if not booking:
            return jsonify({"error": "Not found"}), 404
        
        update_data = {
            'customer_name': data['customer_name'],
            'customer_phone': data['customer_phone'],
            'appointment_date': data['appointment_date'],
            'appointment_time': data['appointment_time'],
            'service': data.get('service', ''),
            'notes': data.get('notes', '')
        }
        
        DB.update('bookings', {'id': booking_id}, update_data)
        
        return jsonify({"status": "updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/bookings/<booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        booking = DB.find_one('bookings', {'id': booking_id, 'business_owner_id': owner_id})
        if not booking:
            return jsonify({"error": "Not found"}), 404
        
        DB.delete('bookings', {'id': booking_id})
        
        return jsonify({"status": "deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/messages', methods=['GET'])
def get_messages():
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        messages = DB.find_many('messages', 
                               where={'business_owner_id': owner_id}, 
                               order_by='created_at DESC',
                               limit=50)
        return jsonify(messages), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/customer/messages', methods=['POST'])
def send_message():
    owner_id = verify_auth()
    if not owner_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    
    message_data = {
        'business_owner_id': owner_id,
        'customer_phone': data['customer_phone'],
        'message': data['message'],
        'direction': 'outbound'
    }
    
    try:
        message = DB.insert('messages', message_data)
        send_sms(to=data['customer_phone'], message=data['message'])
        
        return jsonify(message), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/vapi/config', methods=['GET'])
def get_vapi_config():
    return jsonify({"public_key": os.getenv("VAPI_PUBLIC_KEY", "")}), 200

# ============================================================================
# ADMIN - ONBOARDING CALLS LIST ONLY
# ============================================================================

@app.route('/admin/login')
def admin_login_page():
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard_page():
    return render_template('admin_dashboard.html')

@app.route('/admin')
def admin_redirect():
    return render_template('admin_login.html')

ADMIN_PHONE = os.getenv('ADMIN_PHONE')

@app.route("/api/admin/auth/send-otp", methods=["POST"])
def admin_send_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    
    if not phone:
        return jsonify({"error": "Phone number required"}), 400
    
    if phone != ADMIN_PHONE:
        return jsonify({"error": "Access denied. Not an admin number."}), 403
    
    try:
        if supabase:
            supabase.auth.sign_in_with_otp({"phone": phone})
        return jsonify({"status": "OTP sent"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/auth/verify-otp", methods=["POST"])
def admin_verify_otp():
    data = request.json or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()
    
    if not phone or not otp:
        return jsonify({"error": "Phone and OTP required"}), 400
    
    if phone != ADMIN_PHONE:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        if supabase:
            response = supabase.auth.verify_otp({
                "phone": phone,
                "token": otp,
                "type": "sms"
            })
            
            if not response.user:
                return jsonify({"error": "Invalid OTP"}), 401
            
            return jsonify({
                "token": response.session.access_token,
                "is_admin": True
            }), 200
        else:
            return jsonify({"error": "Supabase not configured"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 401


def verify_admin_auth():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return False
    
    token = auth_header.split(' ')[1]
    try:
        if supabase:
            user = supabase.auth.get_user(token)
            if user and user.user.phone == ADMIN_PHONE:
                return True
    except:
        return False
    return False


@app.route('/api/admin/onboarding-calls', methods=['GET'])
def get_all_onboarding_calls():
    if not verify_admin_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        calls = DB.find_many('onboarding_calls', 
                            order_by='created_at DESC',
                            limit=100)
        return jsonify(calls), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
