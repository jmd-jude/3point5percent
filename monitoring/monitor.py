import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from supabase import create_client

def get_system_health(supabase):
    """Get overall system health metrics"""
    from datetime import datetime, timedelta
    
    # Get all articles
    all_articles = supabase.table('news_articles').select('*').execute()
    
    if not all_articles.data:
        return {
            'total_articles': 0,
            'last_7_days': 0,
            'last_24_hours': 0,
            'categorized': 0,
            'newsletter_ready': 0,
            'already_featured': 0
        }
    
    articles = all_articles.data
    now = datetime.now()
    
    return {
        'total_articles': len(articles),
        'last_7_days': len([a for a in articles if a.get('discovered_at') and 
                           datetime.fromisoformat(a['discovered_at'].replace('Z', '+00:00')) >= now - timedelta(days=7)]),
        'last_24_hours': len([a for a in articles if a.get('discovered_at') and 
                            datetime.fromisoformat(a['discovered_at'].replace('Z', '+00:00')) >= now - timedelta(hours=24)]),
        'categorized': len([a for a in articles if a.get('category')]),
        'newsletter_ready': len([a for a in articles if a.get('relevance_score', 0) >= 7]),
        'already_featured': len([a for a in articles if a.get('featured_in_newsletter')])
    }

def get_source_performance(supabase):
    """Get RSS source performance"""
    # Get all sources
    sources = supabase.table('news_sources').select('*').execute()
    
    # Get all articles
    articles = supabase.table('news_articles').select('source_name, relevance_score').execute()
    
    source_stats = []
    
    for source in sources.data:
        source_articles = [a for a in articles.data if a['source_name'] == source['name']]
        high_quality = [a for a in source_articles if a.get('relevance_score', 0) >= 7]
        scores = [a['relevance_score'] for a in source_articles if a.get('relevance_score')]
        
        source_stats.append({
            'name': source['name'],
            'articles_found': len(source_articles),
            'high_quality': len(high_quality),
            'avg_relevance': round(sum(scores) / len(scores), 1) if scores else 0,
            'last_checked': source.get('last_checked'),
            'active': source.get('active', True)
        })
    
    return sorted(source_stats, key=lambda x: x['articles_found'], reverse=True)[:10]

def get_newsletter_pipeline(supabase):
    """Get articles ready for newsletter"""
    # Get high-scoring unfeatured articles
    pipeline_articles = supabase.table('news_articles').select('category, relevance_score').gte('relevance_score', 7).eq('featured_in_newsletter', False).not_.is_('category', None).execute()
    
    if not pipeline_articles.data:
        return []
    
    # Group by category
    categories = {}
    for article in pipeline_articles.data:
        cat = article['category']
        if cat not in categories:
            categories[cat] = {'articles': [], 'count': 0}
        categories[cat]['articles'].append(article['relevance_score'])
        categories[cat]['count'] += 1
    
    # Calculate averages and format
    result = []
    for cat, data in categories.items():
        avg_score = round(sum(data['articles']) / len(data['articles']), 1)
        result.append({
            'category': cat,
            'available_articles': data['count'],
            'avg_score': avg_score
        })
    
    return sorted(result, key=lambda x: x['available_articles'], reverse=True)

def format_results(health_data, source_data, pipeline_data):
    """Format the query results into a readable report"""
    
    report = f"""
3.5 Percent Weekly - System Health Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

=== SYSTEM HEALTH ===
"""
    
    if health_data:
        h = health_data[0]
        report += f"""
Total Articles: {h['total_articles']}
Last 7 Days: {h['last_7_days']}
Last 24 Hours: {h['last_24_hours']}
Categorized: {h['categorized']}
Newsletter Ready (7+): {h['newsletter_ready']}
Already Featured: {h['already_featured']}
"""
    
    report += "\n=== TOP RSS SOURCES ===\n"
    for source in source_data[:5]:
        status = "✅" if source['active'] else "❌"
        report += f"""
{status} {source['name']}
   Articles Found: {source['articles_found']}
   High Quality: {source['high_quality']}
   Avg Relevance: {source['avg_relevance']}
   Last Checked: {source['last_checked']}
"""
    
    report += "\n=== NEWSLETTER PIPELINE ===\n"
    if pipeline_data:
        for category in pipeline_data:
            report += f"{category['category']}: {category['available_articles']} articles (avg score: {category['avg_score']})\n"
    else:
        report += "No high-quality articles ready for newsletter.\n"
    
    return report

def send_email_report(report, recipient_email):
    """Send the report via email"""
    
    # Email configuration from environment variables
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('EMAIL_PASSWORD')
    
    if not all([sender_email, sender_password, recipient_email]):
        print("Missing email configuration. Report not sent.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"3.5% Weekly System Report - {datetime.now().strftime('%Y-%m-%d')}"
        
        # Add body
        msg.attach(MIMEText(report, 'plain'))
        
        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        server.quit()
        
        print("Report email sent successfully!")
        return True
        
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def main():
    """Main monitoring function"""
    print("Starting 3.5% Weekly system monitoring...")
    
    # Get configuration from environment
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    recipient_email = os.getenv('REPORT_EMAIL')
    
    if not all([supabase_url, supabase_key]):
        print("Missing Supabase configuration!")
        return
    
    try:
        # Connect to Supabase
        supabase = create_client(supabase_url, supabase_key)
        print("Connected to Supabase successfully")
        
        # Run queries
        print("Running health check...")
        health_data = get_system_health(supabase)
        
        print("Checking source performance...")
        source_data = get_source_performance(supabase)
        
        print("Checking newsletter pipeline...")
        pipeline_data = get_newsletter_pipeline(supabase)
        
        # Format report
        report = format_results([health_data], source_data, pipeline_data)
        
        # Print to console (for GitHub Actions logs)
        print("\n" + "="*50)
        print(report)
        print("="*50)
        
        # Send email if configured
        if recipient_email:
            send_email_report(report, recipient_email)
        else:
            print("No recipient email configured - report not sent")
            
    except Exception as e:
        print(f"Error running monitoring: {e}")

if __name__ == "__main__":
    main()