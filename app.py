import argparse
import sys
from datetime import datetime
from db import run_migrations, get_connection
from scraper import scrape_jobs
from hunter_enrichment import lookup_hr_contacts


def save_job_to_db(cursor, job):
    """
    Saves a job listing to the database, preventing duplicate URL entries.
    Returns the job ID (existing or newly created) and a boolean indicating if it was new.
    """
    cursor.execute("SELECT id FROM jobs WHERE url = %s;", (job["url"],))
    existing = cursor.fetchone()

    if existing:
        return existing[0], False

    cursor.execute(
        """
        INSERT INTO jobs (title, company, location, experience_level, job_type, salary, platform, url, description, status, posted_date, apply_last_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            job["title"],
            job["company"],
            job["location"],
            job["experience_level"],
            job["job_type"],
            job["salary"],
            job["platform"],
            job["url"],
            job["description"],
            "New",
            job["posted_date"],
            job.get("apply_last_date"),
        ),
    )
    job_id = cursor.fetchone()[0]
    return job_id, True


def save_contact_to_db(cursor, contact):
    """Save an HR contact, skipping duplicates (same email + job)."""
    cursor.execute(
        "SELECT id FROM contacts WHERE email = %s AND (job_id = %s OR company = %s);",
        (contact["email"], contact["job_id"], contact["company"]),
    )
    if cursor.fetchone():
        return
    cursor.execute(
        """
        INSERT INTO contacts (job_id, company, name, email, title, source, verified)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """,
        (
            contact["job_id"],
            contact["company"],
            contact["name"],
            contact["email"],
            contact["title"],
            contact["source"],
            contact["verified"],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description="Job Finder Pipeline - Scrape & Save")
    parser.add_argument("--role",      type=str, default="Python Developer",    help="Search job title / keywords")
    parser.add_argument("--location",  type=str, default="Remote",              help="Job location")
    parser.add_argument("--exp",       type=str, default="Entry Level",         help="Experience level")
    parser.add_argument("--type",      type=str, default="Full-time",           help="Job type")
    parser.add_argument("--platforms", type=str, default="LinkedIn",            help="Comma-separated platforms")
    parser.add_argument("--limit",     type=int, default=15,                    help="Max results per platform")

    args = parser.parse_args()

    print("=" * 60)
    print("         JOB FINDER PIPELINE - CLI RUNNER")
    print("=" * 60)

    # 1. Database setup
    print("\n[Step 1] Checking database...")
    try:
        run_migrations()
    except Exception as e:
        print(f"Database setup failed: {e}")
        sys.exit(1)

    # 2. Scrape jobs in parallel
    print("\n[Step 2] Scraping job listings (parallel)...")
    platform_list = [p.strip() for p in args.platforms.split(",")]
    raw_jobs = scrape_jobs(
        keywords=args.role,
        location=args.location,
        experience_level=args.exp,
        job_type=args.type,
        platforms=platform_list,
        limit=args.limit,
    )

    if not raw_jobs:
        print("No jobs found. Check your Apify token and actor configs.")
        return

    # 3. Save to database
    print(f"\n[Step 3] Saving {len(raw_jobs)} jobs to database...")
    conn = get_connection()
    cursor = conn.cursor()
    new_count = 0

    try:
        for idx, job in enumerate(raw_jobs):
            job_id, is_new = save_job_to_db(cursor, job)
            if is_new:
                new_count += 1
                cursor.execute("UPDATE jobs SET status = 'New' WHERE id = %s;", (job_id,))
            conn.commit()
            print(f"  [{idx+1}/{len(raw_jobs)}] {'NEW' if is_new else 'EXISTS'}: {job['title']} @ {job['company']} ({job['platform']})")

        print(f"\n{'='*60}")
        print(f"  Total scraped : {len(raw_jobs)}")
        print(f"  New saved     : {new_count}")
        print(f"  Duplicates    : {len(raw_jobs) - new_count}")
        print(f"{'='*60}")

    except Exception as e:
        conn.rollback()
        print(f"Pipeline error: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
