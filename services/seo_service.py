import os

BACKEND_URL = os.getenv('BACKEND_URL', 'https://tryspeak.com')

def get_page_meta(page):
    """Get SEO meta tags for each page"""
    
    meta_data = {
        'home': {
            'title': 'TrySpeak - AI Phone Receptionist for UK Tradespeople | Never Miss a Call',
            'description': 'AI phone receptionist that answers calls 24/7. Perfect for plumbers, electricians, builders. £75/month. British voice, instant setup, no missed calls.',
            'keywords': 'AI receptionist, phone answering service, virtual receptionist, UK tradespeople, plumber receptionist, electrician receptionist, 24/7 call answering',
            'og_type': 'website',
            'og_image': f'{BACKEND_URL}/static/images/og-image.jpg'
        },
        'signup': {
            'title': 'Sign Up - Get Your AI Receptionist | TrySpeak',
            'description': 'Start your free 20-minute setup call. AI receptionist ready in 2 hours. £75/month, cancel anytime. Used by 100+ UK businesses.',
            'keywords': 'signup, register, AI receptionist setup, virtual receptionist trial',
            'og_type': 'website',
            'og_image': f'{BACKEND_URL}/static/images/og-image.jpg'
        },
        'pricing': {
            'title': 'Pricing - £75/Month AI Receptionist | TrySpeak',
            'description': 'Simple pricing: £75/month for unlimited calls. No setup fees, no contracts. Cancel anytime. Used by UK plumbers, electricians, builders.',
            'keywords': 'pricing, cost, AI receptionist price, phone answering service cost',
            'og_type': 'website',
            'og_image': f'{BACKEND_URL}/static/images/og-image.jpg'
        }
    }
    
    return meta_data.get(page, meta_data['home'])

def generate_meta_tags(page='home'):
    """Generate HTML meta tags"""
    meta = get_page_meta(page)
    
    canonical_url = f"{BACKEND_URL}/{page if page != 'home' else ''}"
    
    return f"""
    <!-- Primary Meta Tags -->
    <title>{meta['title']}</title>
    <meta name="title" content="{meta['title']}">
    <meta name="description" content="{meta['description']}">
    <meta name="keywords" content="{meta['keywords']}">
    <meta name="robots" content="index, follow">
    <meta name="language" content="English">
    <meta name="author" content="TrySpeak">
    <link rel="canonical" href="{canonical_url}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="{meta['og_type']}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{meta['title']}">
    <meta property="og:description" content="{meta['description']}">
    <meta property="og:image" content="{meta['og_image']}">
    <meta property="og:site_name" content="TrySpeak">
    <meta property="og:locale" content="en_GB">

    <!-- Twitter -->
    <meta property="twitter:card" content="summary_large_image">
    <meta property="twitter:url" content="{canonical_url}">
    <meta property="twitter:title" content="{meta['title']}">
    <meta property="twitter:description" content="{meta['description']}">
    <meta property="twitter:image" content="{meta['og_image']}">

    <!-- Favicon -->
    <link rel="icon" type="image/png" sizes="32x32" href="/static/images/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/static/images/favicon-16x16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/static/images/apple-touch-icon.png">

    <!-- Additional SEO -->
    <meta name="theme-color" content="#4F46E5">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """

def generate_local_business_schema():
    """Generate JSON-LD structured data for local business"""
    return """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "LocalBusiness",
      "name": "TrySpeak",
      "description": "AI phone receptionist service for UK tradespeople and small businesses",
      "url": "https://tryspeak.com",
      "telephone": "+44-800-XXX-XXXX",
      "email": "hello@tryspeak.com",
      "address": {
        "@type": "PostalAddress",
        "addressCountry": "GB",
        "addressLocality": "Leeds",
        "addressRegion": "England"
      },
      "priceRange": "££",
      "aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": "4.9",
        "reviewCount": "127"
      },
      "openingHours": "Mo-Su 00:00-23:59",
      "sameAs": [
        "https://twitter.com/tryspeak",
        "https://linkedin.com/company/tryspeak"
      ]
    }
    </script>
    """

def generate_product_schema():
    """Generate JSON-LD for SaaS product"""
    return """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "TrySpeak AI Receptionist",
      "applicationCategory": "BusinessApplication",
      "operatingSystem": "Web, iOS, Android",
      "offers": {
        "@type": "Offer",
        "price": "75.00",
        "priceCurrency": "GBP",
        "priceSpecification": {
          "@type": "UnitPriceSpecification",
          "price": "75.00",
          "priceCurrency": "GBP",
          "billingDuration": "P1M",
          "billingIncrement": 1
        }
      },
      "aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": "4.9",
        "ratingCount": "127"
      },
      "description": "AI-powered phone receptionist for UK businesses. Answers calls 24/7, handles bookings, detects emergencies.",
      "screenshot": "https://tryspeak.com/static/images/screenshot.jpg"
    }
    </script>
    """

def generate_faq_schema():
    """Generate FAQ schema for better search results"""
    return """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "How much does TrySpeak cost?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "TrySpeak costs £75 per month with no setup fees or contracts. You can cancel anytime."
          }
        },
        {
          "@type": "Question",
          "name": "How long does setup take?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Setup takes 20-30 minutes for the initial interview call. Your AI receptionist will be ready within 2 hours."
          }
        },
        {
          "@type": "Question",
          "name": "Does the AI sound British?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Yes, TrySpeak uses natural British voices powered by ElevenLabs AI. Your customers will think they're speaking to a real receptionist."
          }
        },
        {
          "@type": "Question",
          "name": "Can it handle emergencies?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Yes, TrySpeak can detect emergency keywords and immediately notify you via SMS when urgent calls come in."
          }
        }
      ]
    }
    </script>
    """

def generate_breadcrumbs(page_name, page_url):
    """Generate breadcrumb schema"""
    return f"""
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      "itemListElement": [
        {{
          "@type": "ListItem",
          "position": 1,
          "name": "Home",
          "item": "{BACKEND_URL}"
        }},
        {{
          "@type": "ListItem",
          "position": 2,
          "name": "{page_name}",
          "item": "{BACKEND_URL}/{page_url}"
        }}
      ]
    }}
    </script>
    """
