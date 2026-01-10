# PWA (Progressive Web App) SETUP

## What's Included

✅ `manifest.json` - PWA configuration
✅ `sw.js` - Service worker for offline support
✅ Install prompt
✅ Push notifications support
✅ Offline caching
✅ App shortcuts

---

## Required Icons

Create these PNG icons and save in `/static/images/`:

**Sizes needed:**
- icon-72.png (72x72)
- icon-96.png (96x96)
- icon-128.png (128x128)
- icon-144.png (144x144)
- icon-152.png (152x152)
- icon-192.png (192x192) ⭐ Required
- icon-384.png (384x384)
- icon-512.png (512x512) ⭐ Required

**Other images:**
- screenshot-mobile.png (540x720) - For app stores
- screenshot-desktop.png (1280x720) - For app stores
- badge-72.png (72x72) - For notifications

**Tool to create icons:**
https://realfavicongenerator.net/

Upload your logo, download all sizes.

---

## Add to HTML Templates

Add these to `<head>` in all templates:

```html
<!-- PWA Manifest -->
<link rel="manifest" href="/static/manifest.json">

<!-- Theme Color -->
<meta name="theme-color" content="#4F46E5">

<!-- Apple Touch Icon -->
<link rel="apple-touch-icon" href="/static/images/icon-192.png">

<!-- iOS Meta Tags -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="TrySpeak">

<!-- Service Worker Registration -->
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js')
      .then(reg => console.log('Service Worker registered'))
      .catch(err => console.log('Service Worker registration failed'));
  });
}
</script>
```

---

## Install Prompt

Add install button to dashboard:

```html
<button id="installBtn" style="display: none;">
  📱 Install App
</button>

<script>
let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  document.getElementById('installBtn').style.display = 'block';
});

document.getElementById('installBtn').addEventListener('click', async () => {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`User ${outcome} the install prompt`);
    deferredPrompt = null;
    document.getElementById('installBtn').style.display = 'none';
  }
});
</script>
```

---

## Push Notifications

### Backend Setup

Add to Flask app:

```python
from pywebpush import webpush, WebPushException
import json

def send_push_notification(subscription, title, body, url):
    """Send push notification to user"""
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                'title': title,
                'body': body,
                'url': url
            }),
            vapid_private_key=os.getenv('VAPID_PRIVATE_KEY'),
            vapid_claims={
                'sub': 'mailto:hello@tryspeak.com'
            }
        )
        return True
    except WebPushException as e:
        print(f"Push notification failed: {e}")
        return False
```

### Frontend Setup

```javascript
// Request notification permission
async function requestNotificationPermission() {
  const permission = await Notification.requestPermission();
  
  if (permission === 'granted') {
    // Subscribe to push notifications
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: 'YOUR_VAPID_PUBLIC_KEY'
    });
    
    // Send subscription to backend
    await fetch('/api/notifications/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription)
    });
  }
}
```

### Generate VAPID Keys

```bash
pip install pywebpush

python -c "from pywebpush import vapid; print(vapid.Vapid().generate_keys().to_dict())"
```

Add keys to .env:
```
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
```

---

## Testing PWA

### Chrome DevTools:
1. Open DevTools (F12)
2. Go to Application tab
3. Check:
   - Manifest loads correctly
   - Service Worker registered
   - Icons present
   - Install prompt works

### Lighthouse Audit:
1. DevTools → Lighthouse
2. Select "Progressive Web App"
3. Click "Generate report"
4. Fix any issues

### Test Install:
1. Open site in Chrome/Edge
2. Click install icon in address bar
3. Or menu → "Install TrySpeak"

---

## Offline Support

The service worker caches:
- Dashboard page
- Calls page
- Referrals page
- CSS/JS files

**Users can view cached data even offline.**

To add more pages to cache, edit `sw.js`:

```javascript
const urlsToCache = [
  '/',
  '/dashboard',
  '/calls',
  '/referrals',
  '/settings',  // Add more pages
  '/static/css/style.css'
];
```

---

## iOS Installation

**iPhone/iPad:**
1. Open site in Safari
2. Tap Share button
3. Scroll down → "Add to Home Screen"
4. Tap "Add"

**Note:** iOS has limited PWA support (no push notifications)

---

## Android Installation

**Chrome/Edge:**
1. Visit site
2. Tap menu (3 dots)
3. "Install app" or "Add to Home screen"

**Or:**
- Automatic install prompt after 2+ visits

---

## App Store Submission (Optional)

### Google Play Store (TWA - Trusted Web Activity)

Use **Bubblewrap** to package PWA:

```bash
npm install -g @bubblewrap/cli

bubblewrap init --manifest https://tryspeak.com/static/manifest.json
bubblewrap build
```

Upload APK to Google Play Console.

### Apple App Store

Not recommended - Apple requires native features.

Use **Capacitor** instead:

```bash
npm install @capacitor/core @capacitor/cli

npx cap init TrySpeak com.tryspeak.app
npx cap add ios
npx cap open ios
```

---

## Update PWA

When you update the app:

1. **Change cache version** in `sw.js`:
```javascript
const CACHE_NAME = 'tryspeak-v2';  // Increment version
```

2. **Deploy updated files**

3. **Service worker auto-updates** on next visit

4. **Optional:** Show update prompt:
```javascript
registration.addEventListener('updatefound', () => {
  const newWorker = registration.installing;
  newWorker.addEventListener('statechange', () => {
    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
      // Show "Update available" prompt
      if (confirm('New version available! Reload?')) {
        window.location.reload();
      }
    }
  });
});
```

---

## Checklist

Before launch:
- [ ] All required icons created (192px, 512px minimum)
- [ ] manifest.json accessible at /static/manifest.json
- [ ] Service worker registered on all pages
- [ ] Install prompt tested
- [ ] Lighthouse PWA score > 90
- [ ] Works offline (basic pages cached)
- [ ] Theme color matches brand
- [ ] Screenshots added to manifest
- [ ] Tested on iOS and Android

---

## Resources

**PWA Builder:** https://www.pwabuilder.com/  
**Manifest Generator:** https://www.simicart.com/manifest-generator.html/  
**Icon Generator:** https://realfavicongenerator.net/  
**Google PWA Guide:** https://web.dev/progressive-web-apps/  
**Push Notifications:** https://web.dev/push-notifications-overview/
