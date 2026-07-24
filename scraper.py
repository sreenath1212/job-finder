import os
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Global per-platform progress tracker (thread-safe via lock)
# ---------------------------------------------------------------------------
_progress_lock = threading.Lock()
scrape_progress = {}  # { "LinkedIn": {"status": "running"|"done"|"failed"|"idle", "count": 0, "error": ""} }

def _reset_progress(platforms):
    """Reset progress tracker for a new pipeline run."""
    with _progress_lock:
        for p in platforms:
            scrape_progress[p] = {"status": "running", "count": 0, "error": ""}

def _update_progress(platform, status, count=0, error=""):
    with _progress_lock:
        scrape_progress[platform] = {"status": status, "count": count, "error": error}

def get_scrape_progress():
    """Return a snapshot of current scraping progress (safe copy)."""
    with _progress_lock:
        return dict(scrape_progress)


# ---------------------------------------------------------------------------
# Apify Actor configs per platform
# ---------------------------------------------------------------------------
ACTOR_CONFIGS = {
    "linkedin": {
        "actor_id": "curious_coder/linkedin-jobs-search-scraper",
        "build_input": lambda keywords, location, limit: {
            "queries": f"{keywords} {location}",
            "maxResults": limit,
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        },
    },
    "indeed": {
        "actor_id": "misceres/indeed-scraper",
        "build_input": lambda keywords, location, limit: {
            "position": keywords,
            "location": location,
            "maxResults": limit,
            "proxyConfiguration": {"useApifyProxy": True},
        },
    },
    "naukri": {
        "actor_id": "parsebird/naukri-jobs-scraper",
        "build_input": lambda keywords, location, limit: {
            "searchQuery": keywords,
            "location": location,
            "maxResults": limit,
            "proxyConfiguration": {"useApifyProxy": True},
        },
    },
    "glassdoor": {
        "actor_id": "bebity/glassdoor-jobs-scraper",
        "build_input": lambda keywords, location, limit: {
            "keyword": keywords,
            "location": location,
            "maxResults": limit,
            "proxyConfiguration": {"useApifyProxy": True},
        },
    },
    "google jobs": {
        "actor_id": "orgupdate/google-jobs-scraper",
        "build_input": lambda keywords, location, limit: {
            "query": f"{keywords} {location}",
            "location": location,
            "maxResults": limit,
            "proxyConfiguration": {"useApifyProxy": True},
        },
    },
}


# ---------------------------------------------------------------------------
# Field mapping: raw Apify item → our standard job schema
# ---------------------------------------------------------------------------
def _map_item(item, platform_lower, platform_display, location, experience_level, job_type):
    """Map a raw Apify dataset item to our internal job dict."""
    title = company = loc = url = description = ""
    salary = "Not specified"
    posted_date_val = None

    if platform_lower == "linkedin":
        title       = item.get("title") or item.get("jobTitle") or ""
        company     = item.get("companyName") or item.get("company") or ""
        loc         = item.get("location") or location
        url         = item.get("jobUrl") or item.get("url") or ""
        description = item.get("description") or item.get("jobDescription") or ""
        salary      = item.get("salaryText") or item.get("salary") or "Not specified"
        posted_date_val = item.get("postedTime") or item.get("postedDate")

    elif platform_lower == "indeed":
        title       = item.get("position") or item.get("title") or ""
        company     = item.get("company") or item.get("companyName") or ""
        loc         = item.get("location") or location
        url         = item.get("url") or item.get("jobUrl") or ""
        description = item.get("description") or item.get("jobDescription") or ""
        salary      = item.get("salary") or item.get("salaryText") or "Not specified"
        posted_date_val = item.get("postedAt") or item.get("date")

    elif platform_lower == "naukri":
        title       = item.get("title") or item.get("jobTitle") or ""
        company     = item.get("company") or item.get("companyName") or ""
        loc         = item.get("location") or location
        url         = item.get("url") or item.get("jobUrl") or ""
        description = item.get("description") or item.get("jobDescription") or ""
        salary      = item.get("salary") or item.get("salaryText") or "Not specified"
        posted_date_val = item.get("postedDate") or item.get("date")

    elif platform_lower == "glassdoor":
        title       = item.get("jobTitle") or item.get("title") or ""
        company     = item.get("employerName") or item.get("company") or ""
        loc         = item.get("location") or location
        url         = item.get("jobLink") or item.get("url") or ""
        description = item.get("description") or item.get("jobDescription") or ""
        salary      = item.get("salary") or item.get("payPeriod") or "Not specified"
        posted_date_val = item.get("ageInDays") and (
            datetime.datetime.now() - datetime.timedelta(days=int(item.get("ageInDays", 0)))
        )

    elif platform_lower == "google jobs":
        title       = item.get("title") or item.get("jobTitle") or ""
        company     = item.get("companyName") or item.get("company") or ""
        loc         = item.get("location") or location
        url         = item.get("applyLink") or item.get("url") or item.get("shareLink") or ""
        description = item.get("description") or item.get("jobDescription") or ""
        salary      = item.get("salary") or item.get("salaryText") or "Not specified"
        posted_date_val = item.get("postedAt") or item.get("date")

    # Parse date safely
    final_posted_date = datetime.datetime.now()
    if posted_date_val:
        if isinstance(posted_date_val, datetime.datetime):
            final_posted_date = posted_date_val
        else:
            try:
                final_posted_date = datetime.datetime.fromisoformat(
                    str(posted_date_val).replace("Z", "+00:00")
                )
            except Exception:
                pass

    # Skip items with no URL (not a real job listing)
    if not url:
        return None

    return {
        "title":            title.strip() or "Software Engineer",
        "company":          company.strip() or "Unknown Company",
        "location":         loc.strip() if isinstance(loc, str) else location,
        "experience_level": experience_level or "Not specified",
        "job_type":         job_type or "Full-time",
        "salary":           salary.strip() if isinstance(salary, str) else "Not specified",
        "platform":         platform_display,
        "url":              url.strip(),
        "description":      description.strip(),
        "posted_date":      final_posted_date,
        "apply_last_date":  None,
    }


# ---------------------------------------------------------------------------
# Single-platform Apify fetch (runs in its own thread)
# ---------------------------------------------------------------------------
def _fetch_platform(keywords, location, platform_display, experience_level, job_type, limit, token):
    """
    Fetch jobs for one platform via Apify.
    Updates scrape_progress and returns a list of job dicts.
    """
    platform_lower = platform_display.lower()
    config = ACTOR_CONFIGS.get(platform_lower)

    if not config:
        _update_progress(platform_display, "failed", error=f"No Apify actor configured for '{platform_display}'")
        print(f"[{platform_display}] No actor config found. Skipping.")
        return []

    client = ApifyClient(token)
    actor_id = config["actor_id"]
    run_input = config["build_input"](keywords, location, limit)

    print(f"[{platform_display}] Starting Apify actor: {actor_id}")
    try:
        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=240)
        dataset_id = run.get("defaultDatasetId")
        print(f"[{platform_display}] Actor done. Fetching dataset {dataset_id}...")

        raw_items = list(client.dataset(dataset_id).iterate_items())
        print(f"[{platform_display}] Received {len(raw_items)} raw items.")

        jobs = []
        for item in raw_items:
            mapped = _map_item(item, platform_lower, platform_display, location, experience_level, job_type)
            if mapped:
                jobs.append(mapped)

        _update_progress(platform_display, "done", count=len(jobs))
        print(f"[{platform_display}] Mapped {len(jobs)} valid jobs.")
        return jobs

    except Exception as e:
        error_msg = str(e)
        _update_progress(platform_display, "failed", error=error_msg)
        print(f"[{platform_display}] ERROR: {error_msg}")
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def scrape_jobs(keywords, location, experience_level=None, job_type=None, platforms=None, time_period=None, limit=15):
    """
    Scrape job listings from all requested platforms IN PARALLEL using Apify.
    
    Args:
        keywords: Job title / search keywords
        location: Target location string
        experience_level: Experience level string
        job_type: Job type string
        platforms: List of platform name strings (e.g. ["LinkedIn", "Naukri"])
        time_period: Unused (kept for API compatibility)
        limit: Max results per platform (default 15)
    
    Returns:
        Flat list of job dicts from all platforms combined.
    """
    if not platforms:
        platforms = ["LinkedIn"]

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("ERROR: APIFY_API_TOKEN is not set in .env. Cannot scrape jobs.")
        return []

    # Reset progress for this run
    _reset_progress(platforms)

    all_jobs = []
    workers = min(len(platforms), 5)

    print(f"\n{'='*60}")
    print(f" Launching parallel scrape: {', '.join(platforms)}")
    print(f" Keywords: '{keywords}' | Location: '{location}' | Limit per platform: {limit}")
    print(f"{'='*60}\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_platform = {
            executor.submit(
                _fetch_platform,
                keywords, location, platform, experience_level, job_type, limit, token
            ): platform
            for platform in platforms
        }

        for future in as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
                print(f"[DONE] {platform}: {len(jobs)} jobs collected.")
            except Exception as exc:
                print(f"[FAIL] {platform}: Unhandled exception: {exc}")
                _update_progress(platform, "failed", error=str(exc))

    print(f"\n{'='*60}")
    print(f" Total jobs collected across all platforms: {len(all_jobs)}")
    print(f"{'='*60}\n")

    return all_jobs


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing parallel scraper...")
    jobs = scrape_jobs(
        keywords="Python Developer",
        location="Remote",
        experience_level="Entry Level",
        job_type="Full-time",
        platforms=["LinkedIn", "Indeed", "Naukri", "Glassdoor", "Google Jobs"],
        limit=5
    )
    for i, j in enumerate(jobs[:5]):
        print(f"\nJob {i+1}: [{j['platform']}] {j['title']} @ {j['company']}")
        print(f"  URL: {j['url']}")
        print(f"  Salary: {j['salary']}")
