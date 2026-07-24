import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import google.generativeai as genai
import datetime

load_dotenv()

from db import get_connection, run_migrations
from scraper import scrape_jobs, get_scrape_progress
from app import save_job_to_db, save_contact_to_db
from hunter_enrichment import lookup_hr_contacts

app = FastAPI(title="Job Finder API")

@app.on_event("startup")
def startup_db_check():
    print("Startup: Running database migrations...")
    run_migrations()

# Serve static dashboard files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def get_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(index_path)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class StatusUpdatePayload(BaseModel):
    status: str

class PipelineRunPayload(BaseModel):
    role: str
    location: str
    experience_level: str
    job_type: str
    platforms: str          # comma-separated, e.g. "LinkedIn,Naukri,Glassdoor"
    limit: Optional[int] = 15

class QueryParseRequest(BaseModel):
    query_sentence: str

class ContactPayload(BaseModel):
    name: Optional[str] = None
    email: str
    title: Optional[str] = None
    source: Optional[str] = "Manual"
    verified: Optional[bool] = False

class JobCreatePayload(BaseModel):
    title: str
    company: str
    location: Optional[str] = "Remote"
    experience_level: Optional[str] = "Entry Level"
    job_type: Optional[str] = "Full-time"
    salary: Optional[str] = "Not specified"
    platform: Optional[str] = "Manual"
    url: str
    description: Optional[str] = ""
    company_email: Optional[str] = None
    posted_date: Optional[str] = None
    apply_last_date: Optional[str] = None

class JobUpdatePayload(BaseModel):
    title: str
    company: str
    location: str
    experience_level: str
    job_type: str
    salary: str
    platform: str
    url: str
    description: str
    status: str
    company_email: Optional[str] = None
    posted_date: Optional[str] = None
    apply_last_date: Optional[str] = None


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/jobs")
async def get_jobs_list():
    """Return all stored job listings ordered by scraped_at descending."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT
                j.id, j.title, j.company, j.location, j.experience_level,
                j.job_type, j.salary, j.platform, j.url, j.description,
                j.posted_date, j.apply_last_date, j.status, j.scraped_at,
                j.company_email
            FROM jobs j
            ORDER BY j.scraped_at DESC;
            """
        )
        jobs = cursor.fetchall()

        # Fetch all contacts and group by job_id
        cursor.execute(
            """
            SELECT job_id, name, email, title, source, verified
            FROM contacts
            WHERE job_id IS NOT NULL;
            """
        )
        contacts_rows = cursor.fetchall()
        contacts_by_job = {}
        for c in contacts_rows:
            jid = str(c["job_id"])
            contacts_by_job.setdefault(jid, []).append({
                "name":     c["name"],
                "email":    c["email"],
                "title":    c["title"],
                "source":   c["source"],
                "verified": c["verified"],
            })

        for job in jobs:
            job["contacts"] = contacts_by_job.get(str(job["id"]), [])

        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {e}")
    finally:
        cursor.close()
        conn.close()


@app.patch("/api/jobs/{job_id}/status")
async def update_job_status(job_id: str, payload: StatusUpdatePayload):
    """Update a job's application status."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE jobs SET status = %s WHERE id = %s RETURNING id;",
            (payload.status, job_id),
        )
        row = cursor.fetchone()
        conn.commit()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {"status": "ok", "message": f"Status updated to {payload.status}"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/pipeline/status")
async def get_pipeline_status():
    """
    Returns the current per-platform scraping progress.
    Frontend polls this endpoint during a scan to show live status cards.
    """
    return get_scrape_progress()


def run_pipeline_in_background(role: str, location: str, experience_level: str, job_type: str, platforms: str, limit: int = 15):
    """Scrape all platforms in parallel and save results to the database."""
    print(f"[Pipeline] role={role}, location={location}, platforms={platforms}, limit={limit}")

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    # Scrape (parallel internally)
    raw_jobs = scrape_jobs(
        keywords=role,
        location=location,
        experience_level=experience_level,
        job_type=job_type,
        platforms=platform_list,
        limit=limit,
    )

    if not raw_jobs:
        print("[Pipeline] No jobs returned from any platform.")
        return []

    # Save to database + Hunter.io HR enrichment
    conn = get_connection()
    cursor = conn.cursor()
    saved_job_ids = []
    # Track companies already looked up this run to avoid duplicate Hunter calls
    enriched_companies = set()
    # Cap Hunter lookups per run to preserve free-tier credits
    HUNTER_LIMIT_PER_RUN = 15

    try:
        for idx, job in enumerate(raw_jobs):
            print(f"[Pipeline] Saving {idx+1}/{len(raw_jobs)}: {job['title']} @ {job['company']} ({job['platform']})")
            job_id, is_new = save_job_to_db(cursor, job)
            saved_job_ids.append(str(job_id))
            if is_new:
                cursor.execute("UPDATE jobs SET status = 'New' WHERE id = %s;", (job_id,))
            conn.commit()

            # Hunter.io enrichment — run for every new job's company (deduplicated)
            company = job["company"]
            if (
                is_new
                and company
                and company not in enriched_companies
                and len(enriched_companies) < HUNTER_LIMIT_PER_RUN
            ):
                enriched_companies.add(company)
                # Check if we already have contacts for this company
                cursor.execute(
                    "SELECT COUNT(*) FROM contacts WHERE company = %s;",
                    (company,)
                )
                existing_count = cursor.fetchone()[0]
                if existing_count == 0:
                    print(f"[Pipeline] Looking up HR contacts for: {company}")
                    contacts = lookup_hr_contacts(company, job_id)
                    for contact in contacts:
                        save_contact_to_db(cursor, contact)
                    conn.commit()
                else:
                    print(f"[Pipeline] Contacts already exist for: {company} — skipping Hunter call")

        # Return full saved jobs with contacts for the frontend
        if saved_job_ids:
            dict_cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                dict_cursor.execute(
                    """
                    SELECT j.id, j.title, j.company, j.location, j.experience_level,
                           j.job_type, j.salary, j.platform, j.url, j.description,
                           j.posted_date, j.apply_last_date, j.status, j.scraped_at, j.company_email
                    FROM jobs j
                    WHERE j.id::text = ANY(%s)
                    ORDER BY j.scraped_at DESC;
                    """,
                    (saved_job_ids,),
                )
                jobs = dict_cursor.fetchall()

                # Fetch contacts for these jobs
                dict_cursor.execute(
                    """
                    SELECT job_id, name, email, title, source, verified
                    FROM contacts
                    WHERE job_id::text = ANY(%s);
                    """,
                    (saved_job_ids,),
                )
                contacts_rows = dict_cursor.fetchall()
                contacts_by_job = {}
                for c in contacts_rows:
                    jid = str(c["job_id"])
                    contacts_by_job.setdefault(jid, []).append({
                        "name":     c["name"],
                        "email":    c["email"],
                        "title":    c["title"],
                        "source":   c["source"],
                        "verified": c["verified"],
                    })

                for job in jobs:
                    job["contacts"] = contacts_by_job.get(str(job["id"]), [])

                return jobs
            finally:
                dict_cursor.close()

    except Exception as e:
        conn.rollback()
        print(f"[Pipeline] Save error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

    return []


@app.post("/api/pipeline/run")
async def trigger_pipeline_run(payload: PipelineRunPayload):
    """Trigger parallel scraping pipeline across selected platforms and save results."""
    try:
        jobs = run_pipeline_in_background(
            payload.role,
            payload.location,
            payload.experience_level,
            payload.job_type,
            payload.platforms,
            payload.limit or 15,
        )
        return {
            "status": "success",
            "message": f"Scraping completed. {len(jobs)} jobs found.",
            "jobs": jobs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@app.post("/api/pipeline/parse-query")
async def parse_query_endpoint(payload: QueryParseRequest):
    """Use Gemini to extract structured search parameters from a natural language sentence."""
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    fallback = {
        "role": "Python Developer",
        "location": "Remote",
        "experience_level": "Entry Level",
        "job_type": "Full-time",
        "platforms": "LinkedIn,Indeed",
    }

    if not api_key:
        return fallback

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        prompt = f"""
You are a recruitment assistant. Parse the following natural language job search request into structured JSON.

User Request:
"{payload.query_sentence}"

Extract:
1. "role": Job title or search keywords (e.g. "React Developer", "Data Analyst").
2. "location": Job location (e.g. "Remote", "Bangalore"). Default: "Remote".
3. "experience_level": One of: "Entry Level", "Mid Level", "Senior Level". Default: "Entry Level".
4. "job_type": One of: "Full-time", "Part-time", "Contract", "Internship". Default: "Full-time".
5. "platforms": Comma-separated list from: LinkedIn, Indeed, Naukri, Glassdoor, Google Jobs.
   Default to "LinkedIn,Indeed,Naukri" if not specified.

Return ONLY a raw JSON object with exactly these keys: role, location, experience_level, job_type, platforms.
"""
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        result = json.loads(response.text.strip())
        return {
            "role":             result.get("role", fallback["role"]),
            "location":         result.get("location", fallback["location"]),
            "experience_level": result.get("experience_level", fallback["experience_level"]),
            "job_type":         result.get("job_type", fallback["job_type"]),
            "platforms":        result.get("platforms", fallback["platforms"]),
        }
    except Exception as e:
        print(f"Gemini parse error: {e}")
        return fallback


@app.get("/crud")
async def get_crud_page():
    crud_path = os.path.join(static_dir, "crud.html")
    if not os.path.exists(crud_path):
        raise HTTPException(status_code=404, detail="CRUD page not found.")
    return FileResponse(crud_path)


@app.post("/api/jobs")
async def create_job_endpoint(payload: JobCreatePayload):
    """Manually insert a job listing."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM jobs WHERE url = %s;", (payload.url,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="A job with this URL already exists.")

        posted_val = payload.posted_date or datetime.datetime.now().isoformat()
        apply_val = payload.apply_last_date or None

        cursor.execute(
            """
            INSERT INTO jobs (title, company, location, experience_level, job_type, salary, platform, url, description, company_email, posted_date, apply_last_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'New')
            RETURNING id;
            """,
            (payload.title, payload.company, payload.location, payload.experience_level,
             payload.job_type, payload.salary, payload.platform, payload.url, payload.description,
             payload.company_email, posted_val, apply_val),
        )
        job_id = cursor.fetchone()[0]
        conn.commit()
        return {"status": "ok", "job_id": str(job_id)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/jobs/{job_id}")
async def update_job_endpoint(job_id: str, payload: JobUpdatePayload):
    """Update an existing job listing."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE jobs
            SET title = %s, company = %s, location = %s, experience_level = %s,
                job_type = %s, salary = %s, platform = %s, url = %s, description = %s,
                status = %s, company_email = %s, posted_date = %s, apply_last_date = %s
            WHERE id = %s RETURNING id;
            """,
            (payload.title, payload.company, payload.location, payload.experience_level,
             payload.job_type, payload.salary, payload.platform, payload.url, payload.description,
             payload.status, payload.company_email,
             payload.posted_date or None, payload.apply_last_date or None, job_id),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
        conn.commit()
        return {"status": "ok", "message": "Job updated."}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update job: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Delete a job listing."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM jobs WHERE id = %s RETURNING id;", (job_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
        conn.commit()
        return {"status": "ok", "message": "Job deleted."}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import uvicorn
    print("Starting Job Finder API on http://localhost:8050 ...")
    uvicorn.run(app, host="127.0.0.1", port=8050)
