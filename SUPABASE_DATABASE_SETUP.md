# SUPABASE DATABASE SETUP

## Get Your Database Connection String

1. Go to your Supabase project: https://supabase.com/dashboard/project/YOUR_PROJECT
2. Click "Project Settings" (gear icon bottom left)
3. Go to "Database" tab
4. Scroll to "Connection string"
5. Select "URI" format
6. Copy the connection string

It looks like:
```
postgresql://postgres:[YOUR-PASSWORD]@db.abc123xyz.supabase.co:5432/postgres
```

7. **Replace `[YOUR-PASSWORD]` with your actual database password**

8. Add to `.env`:
```
SUPABASE_DATABASE_URL=postgresql://postgres:your-real-password@db.abc123xyz.supabase.co:5432/postgres
```

---

## Tables Are Auto-Created

When you start the app, it will automatically create these tables:
- `signups`
- `onboarding_calls`
- `business_owners`
- `their_customers`
- `interactions`
- `referrals`
- `user_consents` (GDPR)

**No manual SQL needed!**

---

## View Your Data

1. Go to Supabase dashboard
2. Click "Table Editor" (left sidebar)
3. You'll see all TrySpeak tables appear after first app start

---

## Separate from Your Other App

Your existing tables (`care_home_data`, `tenants`, etc) won't be affected.

All TrySpeak tables will be in the same database but completely separate.

---

## Test Connection

```bash
# Test if database is accessible
psql "postgresql://postgres:password@db.xxx.supabase.co:5432/postgres"

# Should connect successfully
```

---

## That's It!

Supabase handles:
✅ User authentication (auth.users table)
✅ Your business data (TrySpeak tables)
✅ File storage (if needed later)
✅ Real-time subscriptions (if needed later)

**All in one place. No CockroachDB needed.**
