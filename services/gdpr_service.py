from datetime import datetime, timedelta
from services.cockroachdb_service import DB
import json

def track_consent(user_id, email, ip_address, consent_type='full'):
    """Track user consent for GDPR"""
    consent_data = {
        'user_id': user_id,
        'email': email,
        'ip_address': ip_address,
        'consent_type': consent_type,
        'privacy_policy_version': '1.0',
        'terms_version': '1.0',
        'consented_at': datetime.utcnow()
    }
    return DB.insert('user_consents', consent_data)

def withdraw_consent(user_id):
    """User withdraws consent - mark for deletion"""
    DB.update('business_owners', 
             {'id': user_id}, 
             {'consent_withdrawn': True, 'marked_for_deletion': True})
    return True

def export_user_data(user_id):
    """Export all user data (GDPR right to data portability)"""
    
    # Get business owner data
    owner = DB.find_one('business_owners', {'id': user_id})
    
    if not owner:
        return None
    
    # Get all related data
    customers = DB.find_many('their_customers', {'business_owner_id': user_id})
    interactions = DB.find_many('interactions', {'business_owner_id': user_id})
    
    # Remove sensitive internal fields
    for record in [owner] + customers + interactions:
        if record:
            record.pop('id', None)
            record.pop('created_at', None)
    
    export_data = {
        'export_date': datetime.utcnow().isoformat(),
        'business_owner': owner,
        'customers': customers,
        'interactions': interactions,
        'note': 'This is your complete data as stored in TrySpeak'
    }
    
    return export_data

def delete_user_data(user_id):
    """
    Permanently delete all user data (GDPR right to be forgotten)
    
    IMPORTANT: Some data must be retained for legal/financial reasons:
    - Invoices (7 years for tax)
    - Payment records (7 years)
    - Contracts (term + 6 years)
    """
    
    # Delete interactions
    DB.query("DELETE FROM interactions WHERE business_owner_id = %s", [user_id])
    
    # Delete their customers
    DB.query("DELETE FROM their_customers WHERE business_owner_id = %s", [user_id])
    
    # Anonymize business owner (keep for financial records but remove PII)
    DB.update('business_owners', 
             {'id': user_id},
             {
                 'email': f'deleted-{user_id}@deleted.com',
                 'phone_number': 'DELETED',
                 'business_name': 'DELETED',
                 'onboarding_transcript': 'DELETED',
                 'vapi_assistant_id': None,
                 'status': 'deleted',
                 'deleted_at': datetime.utcnow()
             })
    
    return True

def anonymize_old_data():
    """
    Automatically anonymize data older than retention period
    Run this as a cron job daily
    """
    # Delete interactions older than 90 days
    cutoff = datetime.utcnow() - timedelta(days=90)
    DB.query("""
        DELETE FROM interactions 
        WHERE created_at < %s 
        AND is_emergency = false
    """, [cutoff])
    
    # Delete inactive accounts (no login in 2 years)
    inactive_cutoff = datetime.utcnow() - timedelta(days=730)
    DB.query("""
        UPDATE business_owners 
        SET status = 'archived',
            email = CONCAT('archived-', id, '@deleted.com'),
            phone_number = 'DELETED'
        WHERE last_login < %s 
        AND status = 'active'
    """, [inactive_cutoff])
    
    return True

def get_data_retention_summary(user_id):
    """Show user what data we have and when it will be deleted"""
    owner = DB.find_one('business_owners', {'id': user_id})
    
    if not owner:
        return None
    
    interaction_count = DB.query("""
        SELECT COUNT(*) as count FROM interactions 
        WHERE business_owner_id = %s
    """, [user_id])[0]['count']
    
    customer_count = DB.query("""
        SELECT COUNT(*) as count FROM their_customers 
        WHERE business_owner_id = %s
    """, [user_id])[0]['count']
    
    return {
        'personal_info': {
            'email': owner.get('email'),
            'phone': owner.get('phone_number'),
            'business_name': owner.get('business_name'),
            'retention': 'Until account closed + 7 years for financial records'
        },
        'call_recordings': {
            'count': interaction_count,
            'retention': 'Automatically deleted after 90 days'
        },
        'customer_data': {
            'count': customer_count,
            'retention': 'Until you delete your account'
        },
        'transcripts': {
            'retention': 'Stored securely, deleted on account closure'
        },
        'financial_records': {
            'retention': '7 years (legal requirement for tax purposes)'
        }
    }

def check_data_breach_notification_required(affected_users):
    """
    Check if data breach requires notification under GDPR
    Must notify within 72 hours if high risk to rights and freedoms
    """
    # This is a placeholder - implement actual breach detection logic
    return {
        'notification_required': len(affected_users) > 0,
        'deadline': datetime.utcnow() + timedelta(hours=72),
        'affected_count': len(affected_users),
        'authority': 'ICO (UK Information Commissioner\'s Office)'
    }
