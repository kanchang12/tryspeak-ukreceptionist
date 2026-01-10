# STRIPE SETUP GUIDE

## Step 1: Create Stripe Account
1. Go to https://stripe.com
2. Sign up
3. Complete business verification (required for live mode)

## Step 2: Get API Keys
1. Go to Developers > API Keys
2. Copy:
   - **Publishable key** → STRIPE_PUBLISHABLE_KEY
   - **Secret key** → STRIPE_SECRET_KEY

**For testing:** Use test mode keys (start with `pk_test_` and `sk_test_`)
**For production:** Use live mode keys (start with `pk_live_` and `sk_live_`)

## Step 3: Create Product and Price
1. Go to Products > Add Product
2. Name: "TrySpeak AI Receptionist"
3. Description: "AI phone receptionist for UK tradespeople"
4. Price: £75.00 GBP
5. Billing: Recurring, Monthly
6. Click "Save product"
7. **Copy Price ID** (starts with `price_`) → STRIPE_PRICE_ID

## Step 4: Create Webhook
1. Go to Developers > Webhooks
2. Click "Add endpoint"
3. Endpoint URL: `https://your-domain.com/api/stripe/webhook`
4. Select events to listen to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Click "Add endpoint"
6. **Copy Signing Secret** → STRIPE_WEBHOOK_SECRET

## Step 5: Enable Customer Portal
1. Go to Settings > Billing > Customer portal
2. Enable portal
3. Configure:
   - Allow customers to update payment methods: ✅
   - Allow customers to cancel subscriptions: ✅
   - Allow customers to update subscriptions: ❌
4. Save

## Step 6: Create Referral Coupon (Optional)
This is done automatically by the code, but you can create manually:
1. Go to Products > Coupons
2. Click "Create coupon"
3. Amount off: £25.00
4. Currency: GBP
5. Duration: Once
6. Name: "Referral Discount"

## How It Works

### Payment Flow:
1. User completes onboarding interview
2. Admin creates their assistant
3. User receives SMS with login details
4. User logs in → sees payment page
5. User enters card details
6. Stripe processes payment
7. Webhook confirms payment
8. User's account activated

### Subscription Management:
- User can update payment method via Customer Portal
- User can cancel subscription (cancels at end of period)
- Failed payments trigger email to update payment method
- Invoices sent automatically each month

### Referral Discounts:
1. User A refers User B
2. User B signs up with User A's referral code
3. User B gets £25 off first month (pays £50 instead of £75)
4. User A gets £25 credit on next bill
5. Handled automatically by Stripe

## Testing

### Test Cards:
```
Success: 4242 4242 4242 4242
Decline: 4000 0000 0000 0002
3D Secure: 4000 0027 6000 3184

Any future expiry date
Any 3-digit CVC
```

### Test Webhook Locally:
```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:5000/api/stripe/webhook

# Trigger test event
stripe trigger checkout.session.completed
```

## Production Checklist

Before going live:
- [ ] Switch to live API keys
- [ ] Complete business verification
- [ ] Set up bank account for payouts
- [ ] Configure email receipts
- [ ] Test full payment flow
- [ ] Set up fraud detection rules
- [ ] Configure tax settings (if applicable)
- [ ] Set up dunning (retry failed payments)

## Security Notes
- Never expose secret key in frontend
- Always verify webhook signatures
- Use HTTPS in production
- Store keys in environment variables
- Regularly rotate API keys

## Monitoring
- Dashboard > Payments: See all transactions
- Dashboard > Subscriptions: Monitor active subscriptions
- Dashboard > Customers: View customer details
- Dashboard > Disputes: Handle chargebacks
