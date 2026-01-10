# SUPABASE AUTHENTICATION SETUP

## Step 1: Create Supabase Project

1. Go to https://supabase.com
2. Sign up (free tier: unlimited users)
3. Click "New Project"
4. Choose organization, name project "TrySpeak"
5. Set strong database password
6. Select region (closest to your users)
7. Wait 2 minutes for project to spin up

---

## Step 2: Get API Keys

1. Go to Project Settings > API
2. Copy these values to .env:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_ANON_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY` (keep secret!)

Example:
```bash
SUPABASE_URL=https://abc123xyz.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Step 3: Configure Email Settings

### Email Templates
1. Go to Authentication > Email Templates
2. Customize these templates:
   - **Confirm Signup** - Welcome email
   - **Reset Password** - Password reset link
   - **Magic Link** - Passwordless login (optional)

### Email Provider (Optional)
For production, use custom SMTP:
1. Go to Authentication > Settings > Auth providers
2. Enable Email
3. Add SMTP settings (SendGrid, Mailgun, etc)

For development, Supabase's built-in emails work fine.

---

## Step 4: Configure Auth Settings

Go to Authentication > Settings:

**Site URL:** `https://tryspeak.com`
**Redirect URLs:** 
```
https://tryspeak.com/callback
https://tryspeak.com/dashboard
http://localhost:5000/callback (for dev)
```

**JWT Expiry:** 3600 seconds (1 hour) - adjust as needed

**Disable email confirmations** (optional for MVP):
- Go to Authentication > Settings
- Turn off "Enable email confirmations"
- Users can login immediately after signup

---

## Step 5: Enable Social Login (Optional)

Go to Authentication > Providers and enable:
- **Google** - Most common for UK businesses
- **Microsoft** - For enterprise customers
- **Apple** - For iOS users

Each provider needs OAuth credentials from their developer console.

---

## How It Works

### User Signup Flow:
```python
from services.supabase_auth import sign_up

# Backend
response = sign_up(
    email="user@example.com",
    password="SecurePass123",
    user_metadata={
        "business_name": "Smith Plumbing",
        "phone": "+447911123456"
    }
)

if response:
    # User created, email sent
    access_token = response.session.access_token
    user_id = response.user.id
```

**Frontend:**
```javascript
const response = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        email: 'user@example.com',
        password: 'SecurePass123',
        businessName: 'Smith Plumbing'
    })
});

const { access_token, user } = await response.json();
localStorage.setItem('access_token', access_token);
```

---

### User Login Flow:
```python
from services.supabase_auth import sign_in

response = sign_in(
    email="user@example.com",
    password="SecurePass123"
)

if response:
    access_token = response.session.access_token
    # Return token to frontend
```

**Frontend:**
```javascript
const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        email: 'user@example.com',
        password: 'SecurePass123'
    })
});

const { access_token } = await response.json();
localStorage.setItem('access_token', access_token);

// Redirect to dashboard
window.location.href = '/dashboard';
```

---

### Protected Routes:
```python
from services.supabase_auth import requires_auth, get_user_id

@app.route('/api/dashboard')
@requires_auth
def get_dashboard():
    user_id = get_user_id()
    # user_id is automatically available
    return jsonify({"data": "protected"})
```

**Frontend calls:**
```javascript
const token = localStorage.getItem('access_token');

fetch('/api/dashboard', {
    headers: {
        'Authorization': `Bearer ${token}`
    }
})
```

---

### Password Reset:
```python
from services.supabase_auth import reset_password_email

# Send reset email
reset_password_email("user@example.com")
```

User clicks link in email → redirected to your reset page with token → they enter new password.

---

## Database Integration

Supabase auth creates a `auth.users` table automatically.

Link it to your business_owners table:

```sql
ALTER TABLE business_owners 
ADD COLUMN auth_user_id UUID REFERENCES auth.users(id);

CREATE INDEX idx_auth_user_id ON business_owners(auth_user_id);
```

Then when user signs up:
```python
# 1. Create auth user
response = sign_up(email, password, metadata)

# 2. Create business owner record
DB.insert('business_owners', {
    'auth_user_id': response.user.id,
    'email': email,
    'business_name': metadata['business_name']
})
```

---

## Session Management

**Token Refresh:**
```javascript
// Check if token expired
async function refreshToken() {
    const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${localStorage.getItem('refresh_token')}`
        }
    });
    
    const { access_token } = await response.json();
    localStorage.setItem('access_token', access_token);
}
```

**Auto-refresh on page load:**
```javascript
window.addEventListener('load', async () => {
    const token = localStorage.getItem('access_token');
    if (token) {
        // Verify token is still valid
        const response = await fetch('/api/auth/verify', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) {
            // Token expired, try refresh
            await refreshToken();
        }
    }
});
```

---

## Security Best Practices

1. **NEVER expose service_role key** - Only use in backend
2. **Use HTTPS in production** - Required for secure cookies
3. **Validate email format** - Before calling Supabase
4. **Rate limit auth endpoints** - Prevent brute force
5. **Log authentication events** - For security audits
6. **Use strong password policy** - Min 8 chars, require numbers

---

## Testing

### Test Signup:
```bash
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test123!"}'
```

### Test Login:
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test123!"}'
```

### Test Protected Route:
```bash
curl http://localhost:5000/api/dashboard \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## Troubleshooting

**"Invalid API key"**
- Check SUPABASE_URL and SUPABASE_ANON_KEY in .env
- Make sure no extra spaces

**"Email not confirmed"**
- Disable email confirmations in Supabase settings
- Or check spam folder for confirmation email

**"Token expired"**
- Implement token refresh
- Or user needs to login again

**"CORS error"**
- Add your domain to Supabase allowed URLs
- Check Flask CORS configuration

---

## Cost

**Free Tier Includes:**
- 50,000 monthly active users
- 500MB database
- 1GB file storage
- 2GB bandwidth
- Unlimited API requests

**Paid Plans:**
- $25/month: 100,000 MAU, 8GB database
- $599/month: 200,000 MAU, 32GB database

For TrySpeak at 100 customers = $0/month (way under free limit)

---

## Supabase Dashboard

Access at: https://supabase.com/dashboard/project/YOUR_PROJECT_ID

**Useful features:**
- **Authentication > Users**: See all registered users
- **Table Editor**: View/edit database directly
- **Logs**: Debug API calls
- **Storage**: For file uploads (if needed)

---

## Advantages Over Auth0

✅ **Free forever** for most startups  
✅ **Database included** (PostgreSQL)  
✅ **Simpler setup** (5 minutes vs 30 minutes)  
✅ **Direct database access** (run SQL queries)  
✅ **Built-in storage** (for file uploads)  
✅ **Real-time subscriptions** (if you need WebSockets)  
✅ **Open source** (can self-host if needed)  

---

## Resources

**Docs:** https://supabase.com/docs/guides/auth  
**Dashboard:** https://supabase.com/dashboard  
**Python Client:** https://github.com/supabase-community/supabase-py  
**Support:** https://supabase.com/support
