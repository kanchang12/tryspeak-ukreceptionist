import stripe
import os

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
PRICE_ID = os.getenv('STRIPE_PRICE_ID')  # £75/month price

def create_customer(email, name, phone, auth0_user_id):
    """Create Stripe customer"""
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            phone=phone,
            metadata={
                'auth0_user_id': auth0_user_id,
                'source': 'tryspeak'
            }
        )
        return customer.id
    except Exception as e:
        print(f"Stripe create customer error: {e}")
        return None

def create_subscription(customer_id, coupon_code=None):
    """
    Create subscription for customer
    Returns subscription object with payment intent client_secret
    """
    try:
        params = {
            'customer': customer_id,
            'items': [{'price': PRICE_ID}],
            'payment_behavior': 'default_incomplete',
            'payment_settings': {
                'save_default_payment_method': 'on_subscription'
            },
            'expand': ['latest_invoice.payment_intent'],
            'metadata': {'product': 'tryspeak_subscription'}
        }
        
        # Apply referral discount if provided
        if coupon_code:
            params['coupon'] = coupon_code
        
        subscription = stripe.Subscription.create(**params)
        
        return {
            'subscription_id': subscription.id,
            'client_secret': subscription.latest_invoice.payment_intent.client_secret,
            'status': subscription.status
        }
    except Exception as e:
        print(f"Stripe create subscription error: {e}")
        return None

def get_subscription(subscription_id):
    """Get subscription details"""
    try:
        return stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        print(f"Stripe get subscription error: {e}")
        return None

def cancel_subscription(subscription_id, immediately=False):
    """Cancel subscription"""
    try:
        if immediately:
            # Cancel immediately
            stripe.Subscription.delete(subscription_id)
        else:
            # Cancel at period end
            stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        return True
    except Exception as e:
        print(f"Stripe cancel subscription error: {e}")
        return False

def reactivate_subscription(subscription_id):
    """Reactivate a cancelled subscription"""
    try:
        stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=False
        )
        return True
    except:
        return False

def create_referral_coupon():
    """Create £25 off coupon for referrals (one-time use)"""
    try:
        coupon = stripe.Coupon.create(
            amount_off=2500,  # £25 in pence
            currency='gbp',
            duration='once',
            name='Referral Discount',
            metadata={'type': 'referral'}
        )
        return coupon.id
    except:
        # Coupon creation failed, try to retrieve existing
        try:
            coupons = stripe.Coupon.list(limit=100)
            for c in coupons.data:
                if c.amount_off == 2500 and c.currency == 'gbp':
                    return c.id
        except:
            pass
        return None

def apply_referral_credit(customer_id, amount=2500, description="Referral credit"):
    """Apply credit to customer balance (£25 = 2500 pence)"""
    try:
        # Negative amount = credit
        stripe.Customer.modify(
            customer_id,
            balance=amount * -1
        )
        
        # Create balance transaction for audit trail
        stripe.CustomerBalanceTransaction.create(
            customer=customer_id,
            amount=amount * -1,
            currency='gbp',
            description=description
        )
        return True
    except Exception as e:
        print(f"Stripe apply credit error: {e}")
        return False

def create_customer_portal_session(customer_id, return_url):
    """Create Stripe customer portal session for managing subscription"""
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )
        return session.url
    except Exception as e:
        print(f"Stripe portal error: {e}")
        return None

def get_customer_invoices(customer_id, limit=10):
    """Get customer's invoices"""
    try:
        invoices = stripe.Invoice.list(
            customer=customer_id,
            limit=limit
        )
        return invoices.data
    except:
        return []

def get_payment_methods(customer_id):
    """Get customer's payment methods"""
    try:
        methods = stripe.PaymentMethod.list(
            customer=customer_id,
            type='card'
        )
        return methods.data
    except:
        return []

def verify_webhook_signature(payload, signature, webhook_secret):
    """Verify Stripe webhook signature"""
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, webhook_secret
        )
        return event
    except Exception as e:
        print(f"Webhook signature verification failed: {e}")
        return None

def handle_successful_payment(session):
    """Extract customer and subscription info from successful payment"""
    return {
        'customer_id': session.get('customer'),
        'subscription_id': session.get('subscription'),
        'email': session.get('customer_details', {}).get('email')
    }
