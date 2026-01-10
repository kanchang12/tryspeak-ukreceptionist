from services.cockroachdb_service import DB
from services.stripe_service import apply_referral_credit, create_referral_coupon
from services.sms_service import send_sms
from datetime import datetime
import os

BACKEND_URL = os.getenv('BACKEND_URL')

def generate_referral_code(business_name, phone):
    """Generate unique referral code"""
    clean_name = business_name.upper().replace(' ', '-').replace("'", "")[:20]
    code = f"{clean_name}-{phone[-4:]}"
    return code

def create_referral_record(referrer_id, referee_email, referral_code):
    """Track new referral"""
    referral_data = {
        'referrer_id': referrer_id,
        'referee_email': referee_email,
        'referral_code': referral_code,
        'status': 'pending',
        'referrer_credit_amount': 25.00,
        'referee_discount_amount': 25.00
    }
    
    try:
        return DB.insert('referrals', referral_data)
    except:
        # Duplicate - referrer already referred this email
        return None

def apply_referee_discount(referee_id, referral_code):
    """
    Apply £25 discount to new customer's first payment
    Returns Stripe coupon code
    """
    # Find referral record
    referral = DB.query("""
        SELECT * FROM referrals 
        WHERE referral_code = %s 
        AND referee_id IS NULL
        LIMIT 1
    """, [referral_code])
    
    if not referral:
        return None
    
    referral = referral[0]
    
    # Update referral with referee_id
    DB.update('referrals', 
             {'id': referral['id']}, 
             {'referee_id': referee_id, 'status': 'active'})
    
    # Create or get Stripe coupon
    coupon_code = create_referral_coupon()
    
    if coupon_code:
        # Mark discount as applied
        DB.update('referrals', 
                 {'id': referral['id']}, 
                 {'referee_discount_applied': True})
    
    return coupon_code

def apply_referrer_credit(referral_id):
    """
    Give £25 credit to referrer after referee pays first time
    """
    referral = DB.find_one('referrals', {'id': referral_id})
    
    if not referral or referral['referrer_credit_applied']:
        return False
    
    # Get referrer
    referrer = DB.find_one('business_owners', {'id': referral['referrer_id']})
    
    if not referrer or not referrer.get('stripe_customer_id'):
        return False
    
    # Apply £25 credit in Stripe
    success = apply_referral_credit(
        referrer['stripe_customer_id'],
        2500,  # £25 in pence
        f"Referral credit for {referral['referee_email']}"
    )
    
    if success:
        # Mark credit as applied
        DB.update('referrals', 
                 {'id': referral_id}, 
                 {
                     'referrer_credit_applied': True,
                     'completed_at': datetime.utcnow(),
                     'status': 'completed'
                 })
        
        # Send notification SMS
        send_sms(
            to=referrer['phone_number'],
            message=f"🎉 You earned £25! {referral['referee_email']} just signed up using your code. Credit applied to your account."
        )
        
        return True
    
    return False

def get_referral_stats(user_id):
    """Get referral statistics for user"""
    referrals = DB.query("""
        SELECT 
            COUNT(*) as total_referrals,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN referrer_credit_applied THEN referrer_credit_amount ELSE 0 END) as total_earned
        FROM referrals
        WHERE referrer_id = %s
    """, [user_id])
    
    if not referrals:
        return {
            'total_referrals': 0,
            'completed': 0,
            'active': 0,
            'pending': 0,
            'total_earned': 0
        }
    
    return referrals[0]

def get_referral_details(user_id, limit=10):
    """Get detailed referral list"""
    referrals = DB.query("""
        SELECT 
            r.*,
            bo.business_name as referee_business_name,
            bo.status as referee_status
        FROM referrals r
        LEFT JOIN business_owners bo ON r.referee_id = bo.id
        WHERE r.referrer_id = %s
        ORDER BY r.created_at DESC
        LIMIT %s
    """, [user_id, limit])
    
    return referrals

def check_referral_code_valid(referral_code):
    """Check if referral code exists and is valid"""
    owner = DB.find_one('business_owners', {'referral_code': referral_code})
    
    if not owner:
        return False
    
    if owner.get('status') != 'active':
        return False
    
    return True

def process_successful_referral_payment(referee_id):
    """
    Called after referee's first successful payment
    Gives credit to referrer
    """
    # Find the referral
    referral = DB.query("""
        SELECT * FROM referrals 
        WHERE referee_id = %s 
        AND status = 'active'
        AND referrer_credit_applied = false
        LIMIT 1
    """, [referee_id])
    
    if not referral:
        return False
    
    return apply_referrer_credit(referral[0]['id'])

def get_referral_link(user_id):
    """Generate shareable referral link"""
    owner = DB.find_one('business_owners', {'id': user_id})
    
    if not owner:
        return None
    
    referral_code = owner.get('referral_code')
    
    if not referral_code:
        return None
    
    return f"{BACKEND_URL}/signup?ref={referral_code}"

def get_share_messages(user_id):
    """Get pre-written share messages"""
    owner = DB.find_one('business_owners', {'id': user_id})
    
    if not owner:
        return None
    
    referral_code = owner.get('referral_code')
    link = get_referral_link(user_id)
    business_name = owner.get('business_name', 'My business')
    
    return {
        'sms': f"Just started using TrySpeak - AI receptionist that never misses calls. Get £25 off: {link}",
        
        'whatsapp': f"I've been using TrySpeak for my business and it's brilliant! AI receptionist handles all calls. Use code {referral_code} for £25 off: {link}",
        
        'email_subject': "Check out TrySpeak - £25 off",
        
        'email_body': f"""Hi,

I've been using TrySpeak for {business_name} and it's been a game-changer. It's an AI phone receptionist that handles calls 24/7 - never misses a booking or emergency.

Costs less than £3/day and you can try it with £25 off your first month using my code: {referral_code}

Sign up here: {link}

Highly recommend it!""",
        
        'twitter': f"Using @TrySpeak AI receptionist for my business - never miss a call again! Get £25 off with code {referral_code}: {link}",
        
        'link': link,
        'code': referral_code
    }
