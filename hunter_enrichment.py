import os
import requests
from dotenv import load_dotenv

load_dotenv()

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")

if not HUNTER_API_KEY:
    print("Warning: HUNTER_API_KEY not set. Hunter.io will run in mock mode.")


def lookup_hr_contacts(company_name, job_id=None):
    """
    Search for HR/recruiting contacts at a company using Hunter.io domain search.
    Falls back to realistic mock contacts if API key is missing or call fails.
    Returns: list of contact dicts with keys: job_id, company, name, email, title, source, verified
    """
    if not HUNTER_API_KEY:
        return _mock_contacts(company_name, job_id)

    contacts = []
    try:
        print(f"[Hunter.io] Looking up contacts for: {company_name}")
        response = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"company": company_name, "api_key": HUNTER_API_KEY},
            timeout=10,
        )

        if response.status_code == 200:
            emails = response.json().get("data", {}).get("emails", [])
            for entry in emails:
                email      = entry.get("value", "")
                first      = entry.get("first_name", "")
                last       = entry.get("last_name", "")
                name       = f"{first} {last}".strip() or None
                title      = entry.get("position") or "Representative"
                confidence = entry.get("confidence", 0)
                verified   = confidence >= 80

                title_lower = title.lower()
                is_hr = any(kw in title_lower for kw in [
                    "hr", "recruiter", "talent", "people", "hiring",
                    "acquisition", "coordinator", "staffing"
                ])

                if is_hr or len(contacts) < 2:
                    contacts.append({
                        "job_id":   job_id,
                        "company":  company_name,
                        "name":     name,
                        "email":    email,
                        "title":    title,
                        "source":   "Hunter.io",
                        "verified": verified,
                    })

            print(f"[Hunter.io] Found {len(contacts)} contact(s) for '{company_name}'.")

        elif response.status_code == 429:
            print(f"[Hunter.io] Rate limit hit for '{company_name}'. Using mock.")
            return _mock_contacts(company_name, job_id)
        else:
            print(f"[Hunter.io] API error {response.status_code} for '{company_name}'. Using mock.")
            return _mock_contacts(company_name, job_id)

    except Exception as e:
        print(f"[Hunter.io] Exception for '{company_name}': {e}. Using mock.")
        return _mock_contacts(company_name, job_id)

    return contacts


def _mock_contacts(company_name, job_id=None):
    """Generate realistic mock HR contacts when Hunter.io is unavailable."""
    domain = (
        company_name.lower()
        .replace(" ", "")
        .replace("-", "")
        .replace(".", "")
        + ".com"
    )
    return [
        {
            "job_id":   job_id,
            "company":  company_name,
            "name":     "HR Team",
            "email":    f"careers@{domain}",
            "title":    "Talent Acquisition",
            "source":   "Hunter.io (Mock)",
            "verified": False,
        },
        {
            "job_id":   job_id,
            "company":  company_name,
            "name":     "Recruiter",
            "email":    f"recruit@{domain}",
            "title":    "Technical Recruiter",
            "source":   "Hunter.io (Mock)",
            "verified": False,
        },
    ]


if __name__ == "__main__":
    contacts = lookup_hr_contacts("Google")
    for c in contacts:
        print(f"  {c['name']} | {c['email']} | {c['title']} | Verified: {c['verified']}")
