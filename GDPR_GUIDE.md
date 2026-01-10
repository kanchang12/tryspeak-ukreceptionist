# GDPR COMPLIANCE GUIDE

## What's Implemented

✅ **Privacy Policy** - Comprehensive, legally compliant  
✅ **Terms of Service** - Clear terms and limitations  
✅ **Consent Tracking** - Log when users accept policies  
✅ **Data Export** - Users can download their data  
✅ **Data Deletion** - "Right to be forgotten"  
✅ **Data Retention** - Automatic deletion policies  
✅ **Cookie Banner** - (needs to be added to frontend)  

## GDPR Requirements Checklist

### ✅ Lawful Basis for Processing
- [x] Contract performance (providing service)
- [x] Consent (marketing)
- [x] Legitimate interest (service improvement)
- [x] Legal obligation (financial records)

### ✅ Data Subject Rights
- [x] Right to access (export endpoint)
- [x] Right to rectification (update profile)
- [x] Right to erasure (delete account)
- [x] Right to restrict processing (withdraw consent)
- [x] Right to data portability (JSON export)
- [x] Right to object (opt-out)

### ✅ Transparency
- [x] Clear privacy policy
- [x] Explain data collection
- [x] List third parties
- [x] State retention periods

### ✅ Security
- [x] HTTPS encryption
- [x] Secure authentication (Auth0)
- [x] Access controls
- [x] Regular security updates

### ⚠️ Still Needed
- [ ] Cookie consent banner on website
- [ ] Data Protection Impact Assessment (DPIA)
- [ ] Appoint Data Protection Officer (if >250 employees)
- [ ] Register with ICO (if processing sensitive data)
- [ ] Staff training on GDPR

## Using the GDPR Service

### Track Consent
```python
from services.gdpr_service import track_consent

track_consent(
    user_id='user-123',
    email='user@example.com',
    ip_address=request.remote_addr,
    consent_type='full'
)
```

### Export User Data
```python
from services.gdpr_service import export_user_data
import json

data = export_user_data('user-123')
json_data = json.dumps(data, indent=2)

# Send as download or email
```

### Delete User Data
```python
from services.gdpr_service import delete_user_data

# Permanently delete (except financial records)
delete_user_data('user-123')
```

### Data Retention Summary
```python
from services.gdpr_service import get_data_retention_summary

summary = get_data_retention_summary('user-123')
# Shows what data we have and when it expires
```

## Automatic Data Cleanup

Run this daily as a cron job:

```python
from services.gdpr_service import anonymize_old_data

# Deletes:
# - Call recordings > 90 days old
# - Inactive accounts > 2 years
anonymize_old_data()
```

Setup cron:
```bash
# Add to crontab
0 2 * * * cd /path/to/app && python -c "from services.gdpr_service import anonymize_old_data; anonymize_old_data()"
```

## Data Breach Response

If you suspect a data breach:

1. **Immediate Actions:**
   - Contain the breach
   - Assess severity
   - Document everything

2. **Notification (if required):**
   - Notify ICO within 72 hours if high risk
   - Email: casework@ico.org.uk
   - Tel: 0303 123 1113

3. **User Notification:**
   - If high risk to users, notify them directly
   - Explain what happened
   - What data was affected
   - What you're doing about it

## Financial Records Exception

**IMPORTANT:** Under UK law, you MUST keep financial records for 7 years:
- Invoices
- Payments
- Subscriptions
- Tax documents

Even if a user requests deletion, you must retain these records (but anonymize personal details).

## Subject Access Requests (SAR)

When a user requests their data:

1. **Verify Identity** - Ensure it's really them
2. **Respond within 30 days** - Can extend to 60 if complex
3. **Provide Data Free** - Unless excessive/repeat requests
4. **Format:** Machine-readable (JSON) + human-readable explanation

## Marketing Opt-Out

Always include unsubscribe link in marketing emails:
```html
<a href="{{ BACKEND_URL }}/unsubscribe?token={{ user_token }}">Unsubscribe</a>
```

## Cookie Banner (TO ADD)

Add this to all pages:
```html
<div id="cookie-banner" style="position: fixed; bottom: 0; width: 100%; background: #333; color: white; padding: 15px; text-align: center;">
    <p>We use essential cookies for authentication and security. No tracking. 
    <a href="/privacy" style="color: #4F46E5;">Privacy Policy</a>
    <button onclick="document.getElementById('cookie-banner').style.display='none'" style="margin-left: 20px; padding: 5px 15px;">Accept</button>
    </p>
</div>
```

## ICO Registration

Register with ICO if you:
- Process personal data as a business
- Are not exempt (e.g., core business activity)

Cost: £40-60/year
Website: ico.org.uk/registration

## Regular Reviews

Review and update annually:
- [ ] Privacy Policy
- [ ] Terms of Service
- [ ] Data retention practices
- [ ] Security measures
- [ ] Third-party processors

## Documentation to Keep

Maintain records of:
- Data processing activities
- Consent records
- Data breach incidents
- DPIA (if conducted)
- Staff training records
- Third-party agreements

## Questions?

**Information Commissioner's Office (ICO):**
- Website: ico.org.uk
- Helpline: 0303 123 1113
- Live chat available

**Legal Advice:**
Consult a UK privacy lawyer for complex situations.
