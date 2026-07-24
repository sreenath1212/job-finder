import sys
from db import get_connection

def safe_print(text):
    """Prints text safely, replacing non-encodable Unicode characters on Windows console."""
    try:
        # Get active stdout encoding
        encoding = sys.stdout.encoding or 'utf-8'
        print(text.encode(encoding, errors='replace').decode(encoding))
    except Exception:
        # Fallback to ascii representation
        print(text.encode('ascii', errors='replace').decode('ascii'))

def show_stored_data():
    safe_print("=" * 70)
    safe_print("            STORED JOBS & ENRICHED HR CONTACTS IN DATABASE             ")
    safe_print("=" * 70)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Query jobs joined with analysis and contacts
        cursor.execute(
            """
            SELECT 
                j.title, 
                j.company, 
                j.location, 
                j.salary,
                a.relevancy_score, 
                a.fit_summary,
                c.name, 
                c.email, 
                c.title,
                c.source
            FROM jobs j
            LEFT JOIN job_analysis a ON j.id = a.job_id
            LEFT JOIN contacts c ON j.id = c.job_id
            ORDER BY a.relevancy_score DESC NULLS LAST, j.company;
            """
        )
        rows = cursor.fetchall()
        
        if not rows:
            safe_print("No jobs found in the database.")
            return
            
        current_job = None
        for row in rows:
            title, company, location, salary, score, summary, contact_name, contact_email, contact_title, contact_source = row
            job_key = (title, company)
            
            # Print job header if it's a new job listing
            if job_key != current_job:
                current_job = job_key
                safe_print(f"\n[JOB] {title} at {company} ({location})")
                safe_print(f"   Salary: {salary} | Platform: PostgreSQL")
                safe_print(f"   AI Match Score: {score}%")
                safe_print(f"   AI Fit Summary: {summary}")
                safe_print("   HR Contacts:")
                
            # Print contact info if available
            if contact_email:
                name_str = contact_name if contact_name else "Unknown Name"
                role_str = contact_title if contact_title else "Representative"
                safe_print(f"     - HR Contact: {name_str} ({contact_email}) - {role_str} [Source: {contact_source}]")
            else:
                safe_print("     (No contacts found)")
                
    except Exception as e:
        safe_print(f"Error reading database: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    show_stored_data()
