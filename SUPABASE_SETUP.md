# SUPABASE SETUP GUIDE

## Step 1: Create Supabase Project
1. Go to https://supabase.com
2. Sign up (free tier: 50,000 users)
3. Click "New Project"
4. Name: "TrySpeak"
5. Database Password: Generate strong password
6. Region: Europe West (London) for UK
7. Click "Create new project"

## Step 2: Get API Keys
1. Go to Project Settings > API
2. Copy these values to .env:
   - **Project URL** → SUPABASE_URL
   - **anon public** → SUPABASE_KEY
   - **service_role** → SUPABASE_SERVICE_KEY

**IMPORTANT:** Never expose service_role key in frontend!

## Step 3: Configure Authentication
1. Go to Authentication > Providers
2. **Email** - Already enabled ✅
3. **Enable Email Confirmations:**
   - Authentication > Settings
   - Enable "Confirm email"
4. **Optional:** Enable Google/Facebook login

## Step 4: Email Templates
1. Go to Authentication > Email Templates
2. Customize these templates:
   - **Confirm signup** - Welcome email
   - **Reset password** - Password reset
   - **Magic link** - Passwordless login

Example welcome email:
```html
<h2>Welcome to TrySpeak!</h2>
<p>Click below to confirm your email:</p>
<a href="{{ .ConfirmationURL }}">Confirm Email</a>
```

## Step 5: Configure Redirect URLs
1. Go to Authentication > URL Configuration
2. **Site URL:** `https://tryspeak.com`
3. **Redirect URLs:** Add these:
```
https://tryspeak.com/dashboard
https://tryspeak.com/login
http://localhost:5000/dashboard  (for dev)
```

## Step 6: Row Level Security (Optional)
If storing user data in Supabase tables:

```sql
-- Enable RLS on your tables
ALTER TABLE business_owners ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own data
CREATE POLICY "Users can view own data"
ON business_owners
FOR SELECT
USING (auth.uid() = user_id);
```

---

## How It Works

### User Signup Flow:
1. User enters email/password on frontend
2. Frontend calls Supabase signup:
```javascript
const { data, error } = await supabase.auth.signUp({
  email: email,
  password: password
})
```
3. Supabase sends confirmation email
4. User clicks link → verified
5. User can login

### User Login Flow:
1. User enters email/password
2. Frontend calls Supabase login:
```javascript
const { data, error } = await supabase.auth.signInWithPassword({
  email: email,
  password: password
})
```
3. Supabase returns JWT token
4. Frontend stores token
5. Sends token with every API request

### Protected API Routes:
```python
from services.supabase_auth_service import requires_auth

@app.route('/api/protected')
@requires_auth
def protected_route():
    user_id = get_user_id()
    return jsonify({"message": "Authenticated!"})
```

---

## Frontend Integration

### Install Supabase JS:
```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
```

### Initialize:
```javascript
const supabaseUrl = 'https://xxx.supabase.co';
const supabaseKey = 'your-anon-key';
const supabase = supabase.createClient(supabaseUrl, supabaseKey);
```

### Signup:
```javascript
async function signup(email, password) {
  const { data, error } = await supabase.auth.signUp({
    email: email,
    password: password
  });
  
  if (error) {
    console.error('Signup error:', error.message);
  } else {
    console.log('Check your email for confirmation!');
  }
}
```

### Login:
```javascript
async function login(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: email,
    password: password
  });
  
  if (error) {
    console.error('Login error:', error.message);
  } else {
    // Store token
    localStorage.setItem('access_token', data.session.access_token);
    // Redirect to dashboard
    window.location.href = '/dashboard';
  }
}
```

### Logout:
```javascript
async function logout() {
  await supabase.auth.signOut();
  localStorage.removeItem('access_token');
  window.location.href = '/';
}
```

### Get Current User:
```javascript
const { data: { user } } = await supabase.auth.getUser();
console.log('Current user:', user);
```

### Password Reset:
```javascript
async function resetPassword(email) {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: 'https://tryspeak.com/reset-password'
  });
}
```

### Call Protected API:
```javascript
const token = localStorage.getItem('access_token');

fetch('/api/dashboard', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

---

## Social Login (Optional)

### Enable Google:
1. Go to Authentication > Providers
2. Enable Google
3. Get OAuth credentials from Google Cloud Console
4. Add Client ID and Secret

### Frontend Code:
```javascript
async function loginWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google'
  });
}
```

---

## Security Best Practices

✅ **Use HTTPS in production**  
✅ **Never expose service_role key in frontend**  
✅ **Enable email confirmation**  
✅ **Set token expiry (default: 1 hour)**  
✅ **Use Row Level Security if storing data in Supabase**  
✅ **Validate tokens on backend**  

---

## Advantages Over Auth0

✅ **Free tier:** 50,000 users vs 7,000  
✅ **Simpler setup:** No complex configuration  
✅ **Built-in database:** Can store data in same place  
✅ **Better docs:** Easier to understand  
✅ **Real-time subscriptions:** Bonus feature  

---

## Testing

### Test Signup:
```bash
curl -X POST https://xxx.supabase.co/auth/v1/signup \
  -H "apikey: your-anon-key" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

### Test Login:
```bash
curl -X POST https://xxx.supabase.co/auth/v1/token?grant_type=password \
  -H "apikey: your-anon-key" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

---

## Troubleshooting

**"Email not confirmed"**
→ Check spam folder or disable email confirmation in settings

**"Invalid API key"**
→ Check you're using anon key in frontend, service key in backend

**"User already registered"**
→ Use login instead, or reset password

**Token expired**
→ Refresh token or re-login

---

## Migration from Auth0

If you were using Auth0:
1. Export user emails from Auth0
2. Create users in Supabase with temp passwords
3. Send password reset emails to all users
4. Update frontend to use Supabase SDK
5. Update backend to use supabase_auth_service.py

---

## Resources

**Supabase Docs:** https://supabase.com/docs/guides/auth  
**JS Client Docs:** https://supabase.com/docs/reference/javascript/auth-signup  
**Python Client:** https://github.com/supabase/supabase-py  
**Dashboard:** https://supabase.com/dashboard
