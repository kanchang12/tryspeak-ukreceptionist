from functools import wraps
from flask import request, jsonify
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def requires_auth(f):
    """Decorator to protect routes with Supabase Auth"""
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

def sign_up(email, password, user_metadata=None):
    """Sign up new user"""
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": user_metadata or {}
            }
        })
        return response
    except Exception as e:
        print(f"Sign up failed: {e}")
        return None

def sign_in(email, password):
    """Sign in existing user"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return response
    except Exception as e:
        print(f"Sign in failed: {e}")
        return None

def sign_out(token):
    """Sign out user"""
    try:
        supabase.auth.sign_out()
        return True
    except Exception as e:
        print(f"Sign out failed: {e}")
        return False

def reset_password_email(email):
    """Send password reset email"""
    try:
        supabase.auth.reset_password_for_email(email)
        return True
    except Exception as e:
        print(f"Password reset failed: {e}")
        return False

def update_user(token, updates):
    """Update user metadata"""
    try:
        response = supabase.auth.update_user({
            "data": updates
        })
        return response
    except Exception as e:
        print(f"Update user failed: {e}")
        return None
