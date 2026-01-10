from functools import wraps
from flask import request, jsonify
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

# Client for frontend operations (uses anon key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client for backend operations (uses service role key)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def get_token_from_header():
    """Extract token from Authorization header"""
    auth = request.headers.get('Authorization', None)
    if not auth:
        return None
    
    parts = auth.split()
    if parts[0].lower() != 'bearer':
        return None
    elif len(parts) == 1:
        return None
    elif len(parts) > 2:
        return None
    
    return parts[1]

def verify_token(token):
    """Verify Supabase JWT token"""
    try:
        user = supabase.auth.get_user(token)
        return user.user if user else None
    except:
        return None

def requires_auth(f):
    """Decorator to protect routes with Supabase auth"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_header()
        
        if not token:
            return jsonify({'error': 'No authorization token'}), 401
        
        user = verify_token(token)
        
        if not user:
            return jsonify({'error': 'Invalid token'}), 401
        
        # Add user info to request
        request.current_user = user
        
        return f(*args, **kwargs)
    
    return decorated

def get_user_id():
    """Get current user ID from Supabase token"""
    if hasattr(request, 'current_user'):
        return request.current_user.id
    return None

def get_user_email():
    """Get current user email from Supabase token"""
    if hasattr(request, 'current_user'):
        return request.current_user.email
    return None

def create_user(email, password):
    """Create new user (called from backend)"""
    try:
        response = supabase_admin.auth.admin.create_user({
            'email': email,
            'password': password,
            'email_confirm': True
        })
        return response
    except Exception as e:
        print(f"Create user error: {e}")
        return None

def send_password_reset_email(email):
    """Send password reset email"""
    try:
        supabase.auth.reset_password_email(email)
        return True
    except:
        return False

def update_user_metadata(user_id, metadata):
    """Update user metadata"""
    try:
        supabase_admin.auth.admin.update_user_by_id(
            user_id,
            {'user_metadata': metadata}
        )
        return True
    except:
        return False
