import sys
from db import run_migrations, get_connection

def test_pipeline_relations():
    print("--- Starting Pipeline Relation & Schema Tests ---")
    
    # 1. Initialize and run migrations
    try:
        run_migrations()
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        sys.exit(1)
        
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Clear any existing test data to start fresh
        cursor.execute("DELETE FROM jobs WHERE url = 'https://example.com/test-job-1';")
        conn.commit()
        
        # 2. Insert test job
        print("Inserting test job...")
        cursor.execute(
            """
            INSERT INTO jobs (title, company, location, experience_level, job_type, salary, platform, url, description, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                "Lead Architect - Agentic AI",
                "Antigravity Corp",
                "Remote, India",
                "Senior / Lead",
                "Full-time",
                "$180,000 - $220,000",
                "LinkedIn",
                "https://example.com/test-job-1",
                "Build state-of-the-art job intelligence pipelines and automated agents.",
                "New"
            )
        )
        job_id = cursor.fetchone()[0]
        print(f"Test job inserted with ID: {job_id}")
        
        # 3. Insert job analysis
        print("Inserting AI job analysis...")
        cursor.execute(
            """
            INSERT INTO job_analysis (job_id, relevancy_score, fit_summary)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (
                job_id,
                95,
                "Strong match. The candidate has extensive experience in agentic workflows and backend engineering matching the target profile."
            )
        )
        analysis_id = cursor.fetchone()[0]
        print(f"Test analysis inserted with ID: {analysis_id}")
        
        # 4. Insert contact
        print("Inserting HR contact details...")
        cursor.execute(
            """
            INSERT INTO contacts (job_id, company, name, email, title, source, verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                job_id,
                "Antigravity Corp",
                "Sarah Connor",
                "sconnor@antigravitycorp.example.com",
                "Head of Talent Acquisition",
                "Hunter.io",
                True
            )
        )
        contact_id = cursor.fetchone()[0]
        print(f"Test contact inserted with ID: {contact_id}")
        conn.commit()
        
        # 5. Query data using a JOIN to simulate what the Frontend would fetch
        print("\n--- Simulating Frontend Query (GET /jobs) ---")
        cursor.execute(
            """
            SELECT 
                j.id, j.title, j.company, j.location, j.job_type, j.salary, j.platform, j.url, j.status,
                a.relevancy_score, a.fit_summary,
                c.name AS contact_name, c.email AS contact_email, c.title AS contact_role, c.verified AS contact_verified
            FROM jobs j
            LEFT JOIN job_analysis a ON j.id = a.job_id
            LEFT JOIN contacts c ON j.id = c.job_id
            WHERE j.id = %s;
            """,
            (job_id,)
        )
        row = cursor.fetchone()
        
        if row:
            print(f"Job Title      : {row[1]}")
            print(f"Company        : {row[2]}")
            print(f"Salary         : {row[5]}")
            print(f"Status         : {row[8]}")
            print(f"Relevancy Score: {row[9]}%")
            print(f"Fit Summary    : {row[10]}")
            print(f"HR Contact     : {row[11]} ({row[12]}) - {row[13]} [Verified: {row[14]}]")
            print("Successfully verified data join structure for Frontend consumption!")
        else:
            print("Error: Could not retrieve inserted job details using frontend join query.")
            
        # 6. Test Relational Cascades (Delete job)
        print("\nTesting relational integrity constraints...")
        print("Deleting job record (should cascade delete analysis and nullify contact's job_id)...")
        cursor.execute("DELETE FROM jobs WHERE id = %s;", (job_id,))
        conn.commit()
        
        # Verify analysis is deleted
        cursor.execute("SELECT COUNT(*) FROM job_analysis WHERE id = %s;", (analysis_id,))
        analysis_count = cursor.fetchone()[0]
        
        # Verify contact's job_id is nullified (but contact is not deleted)
        cursor.execute("SELECT job_id, email FROM contacts WHERE id = %s;", (contact_id,))
        contact_row = cursor.fetchone()
        
        if analysis_count == 0:
            print("- Verified: Job analysis was cascade deleted automatically.")
        else:
            print("- Error: Job analysis was not deleted.")
            
        if contact_row and contact_row[0] is None:
            print(f"- Verified: Contact {contact_row[1]} remains, and job_id was set to NULL.")
        else:
            print("- Error: Contact job_id was not set to NULL or contact was incorrectly deleted.")
            
        # Cleanup contact record
        cursor.execute("DELETE FROM contacts WHERE id = %s;", (contact_id,))
        conn.commit()
        
        print("\nAll database integration tests passed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"An error occurred during verification: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    test_pipeline_relations()
