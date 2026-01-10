# SEO SETUP GUIDE

## What's Implemented

✅ **Meta Tags** - Title, description, keywords for every page  
✅ **Open Graph** - Facebook/LinkedIn sharing cards  
✅ **Twitter Cards** - Twitter sharing previews  
✅ **Structured Data** - JSON-LD schemas for Google  
✅ **Sitemap.xml** - Auto-generated sitemap  
✅ **Robots.txt** - Search engine instructions  
✅ **Canonical URLs** - Prevent duplicate content  
✅ **Local Business Schema** - For Google Business Profile  
✅ **Product Schema** - For Google Shopping  
✅ **FAQ Schema** - Featured snippets in search  
✅ **Breadcrumbs** - Better navigation in search results  

---

## Immediate Actions (Do Now)

### 1. Google Search Console
1. Go to https://search.google.com/search-console
2. Add property: `tryspeak.com`
3. Verify ownership (DNS or HTML file method)
4. Submit sitemap: `https://tryspeak.com/sitemap.xml`

### 2. Google Business Profile
1. Go to https://business.google.com
2. Create business profile
3. Verify address (postcard or phone)
4. Add photos, hours, description
5. Link to website

### 3. Create Social Media Images
Create these images:
- **OG Image:** 1200x630px (for Facebook/LinkedIn)
- **Twitter Image:** 1200x628px
- **Favicon:** 32x32px and 16x16px
- **Apple Touch Icon:** 180x180px

Save in `/static/images/`

### 4. Google Analytics (Optional)
1. Create account at analytics.google.com
2. Get tracking ID (G-XXXXXXXXXX)
3. Add to every page:
```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

---

## SEO Checklist

### Technical SEO
- [x] Sitemap.xml generated
- [x] Robots.txt configured
- [x] Canonical URLs on all pages
- [x] HTTPS enabled (required)
- [x] Mobile responsive
- [x] Fast loading speed
- [ ] Schema markup tested (use Google Rich Results Test)
- [ ] No broken links
- [ ] 404 page created

### On-Page SEO
- [x] Unique title tags (50-60 characters)
- [x] Meta descriptions (150-160 characters)
- [x] H1 tags on every page
- [x] Alt text for images
- [x] Internal linking
- [x] Keyword optimization
- [ ] Content updated regularly

### Local SEO
- [x] Local business schema
- [ ] Google Business Profile created
- [ ] NAP (Name, Address, Phone) consistent
- [ ] Local keywords ("Leeds plumber", "UK electrician")
- [ ] Location pages if serving multiple areas

### Off-Page SEO
- [ ] Backlinks from industry sites
- [ ] Social media profiles created
- [ ] Business directories (Yelp, Trustpilot, etc.)
- [ ] Guest posts on relevant blogs
- [ ] PR and media mentions

---

## Target Keywords

### Primary Keywords:
- AI receptionist
- Virtual receptionist UK
- AI phone answering service
- Automated receptionist

### Long-Tail Keywords:
- AI receptionist for plumbers
- AI receptionist for electricians
- Virtual receptionist for small business UK
- 24/7 phone answering service UK
- AI call answering for tradespeople

### Local Keywords:
- AI receptionist Leeds
- Virtual receptionist London
- Phone answering service Manchester
- (Add your target cities)

---

## Content Strategy

### Blog Posts to Create:
1. "How AI Receptionists Help Plumbers Never Miss Emergency Calls"
2. "The Complete Guide to Virtual Receptionists for UK Tradespeople"
3. "AI vs Human Receptionist: Cost Comparison for Small Businesses"
4. "10 Ways Electricians Lose Money from Missed Calls"
5. "How to Set Up Call Forwarding on iPhone and Android"

### Landing Pages to Create:
- `/for-plumbers` - Plumber-specific page
- `/for-electricians` - Electrician-specific page
- `/for-builders` - Builder-specific page
- `/pricing` - Detailed pricing page
- `/how-it-works` - Explainer page

---

## Social Media Cards Preview

Test how your site looks when shared:
- **Facebook:** https://developers.facebook.com/tools/debug/
- **Twitter:** https://cards-dev.twitter.com/validator
- **LinkedIn:** Just paste URL in post composer

---

## Page Speed Optimization

1. **Compress images:**
```bash
# Use TinyPNG or ImageOptim
# Target: < 100KB per image
```

2. **Enable gzip compression** (if not auto-enabled):
```python
# In Flask
from flask_compress import Compress
compress = Compress(app)
```

3. **Use CDN for static files:**
- Cloudflare (free tier)
- AWS CloudFront
- Google Cloud CDN

4. **Lazy load images:**
```html
<img src="image.jpg" loading="lazy" alt="Description">
```

---

## Monitoring & Analytics

### Track These Metrics:
- Organic traffic (Google Analytics)
- Keyword rankings (Google Search Console)
- Page load speed (PageSpeed Insights)
- Bounce rate
- Conversion rate (signups)
- Backlinks (Ahrefs, SEMrush)

### Monthly SEO Tasks:
- Review Search Console for errors
- Update meta descriptions based on CTR
- Create 1-2 new blog posts
- Build 5-10 backlinks
- Update old content
- Monitor competitors

---

## Schema Markup Testing

Test your structured data:
1. Go to https://search.google.com/test/rich-results
2. Enter your URL
3. Fix any errors
4. Retest after fixes

---

## Local Business Listings

Add TrySpeak to:
- Google Business Profile
- Bing Places
- Apple Maps
- Yelp
- Trustpilot
- Clutch (for B2B)
- Capterra (for software)

Keep NAP (Name, Address, Phone) identical everywhere.

---

## Advanced SEO (Later)

### After Launch:
- Create video content (YouTube SEO)
- Podcast appearances
- Webinars
- Case studies with clients
- Industry partnerships
- Press releases
- Influencer collaborations

### Tools to Use:
- **Keyword Research:** Google Keyword Planner, Ahrefs, SEMrush
- **Rank Tracking:** Ahrefs, SEMrush, SERPWatcher
- **Backlinks:** Ahrefs, Majestic
- **Technical SEO:** Screaming Frog, Sitebulb
- **Page Speed:** GTmetrix, PageSpeed Insights

---

## Expected Results

### Month 1:
- Site indexed by Google
- Basic rankings for brand keywords
- 100-200 organic visitors

### Month 3:
- Ranking for long-tail keywords
- 500-1000 organic visitors
- First organic signups

### Month 6:
- Ranking for competitive keywords
- 2000-5000 organic visitors
- Consistent organic signups

### Month 12:
- Top 3 for target keywords
- 10,000+ organic visitors
- SEO as main acquisition channel

---

## Questions?

**Google Support:** https://support.google.com/webmasters  
**Schema.org Docs:** https://schema.org  
**Moz SEO Guide:** https://moz.com/beginners-guide-to-seo
