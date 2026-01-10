from flask import Response
from datetime import datetime
import os

BACKEND_URL = os.getenv('BACKEND_URL', 'https://tryspeak.com')

def generate_sitemap():
    """Generate sitemap.xml for search engines"""
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    
    pages = [
        {'url': '', 'priority': '1.0', 'changefreq': 'weekly'},
        {'url': 'signup', 'priority': '0.9', 'changefreq': 'monthly'},
        {'url': 'login', 'priority': '0.7', 'changefreq': 'monthly'},
        {'url': 'privacy', 'priority': '0.5', 'changefreq': 'yearly'},
        {'url': 'terms', 'priority': '0.5', 'changefreq': 'yearly'},
    ]
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for page in pages:
        url = f"{BACKEND_URL}/{page['url']}" if page['url'] else BACKEND_URL
        xml += f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{page['changefreq']}</changefreq>
    <priority>{page['priority']}</priority>
  </url>\n"""
    
    xml += '</urlset>'
    
    return Response(xml, mimetype='application/xml')

def generate_robots_txt():
    """Generate robots.txt"""
    
    robots = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /dashboard
Disallow: /api/

Sitemap: {BACKEND_URL}/sitemap.xml
"""
    
    return Response(robots, mimetype='text/plain')
