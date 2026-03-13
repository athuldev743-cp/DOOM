import os
import re
from typing import List, Optional, Tuple

import requests

from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"


def normalize_company_name(company: str) -> str:
    """Normalize company string for rough domain guessing."""
    if not company:
        return ""
    cleaned = company.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def guess_company_domain(company: str) -> str:
    """Very rough domain guess. Not guaranteed to be correct."""
    base = normalize_company_name(company)
    return f"{base}.com" if base else ""


def extract_emails(text: str) -> List[str]:
    """Extract unique emails from text while preserving order."""
    if not text:
        return []
    found = re.findall(EMAIL_REGEX, text)
    return list(dict.fromkeys(found))


def extract_verified_emails_from_result(email_result: str) -> List[str]:
    """Extract only emails from lines marked as verified."""
    if not email_result:
        return []

    verified_lines = [
        line for line in email_result.splitlines()
        if "✓ verified" in line.lower() or "verified" in line.lower()
    ]
    return extract_emails("\n".join(verified_lines))


def get_resume_for_role(role: str) -> Tuple[str, str]:
    p = ProfileManager()
    role_lower = (role or "").lower()

    if any(word in role_lower for word in ["ai", "machine learning", "ml", "data", "llm", "nlp"]):
        path = p.get("resume_ai") or "data/resumes/ai_resume.pdf"
        label = "AI Engineer"
    elif any(word in role_lower for word in ["fullstack", "full stack", "full-stack", "frontend", "react"]):
        path = p.get("resume_fullstack") or "data/resumes/fullstack_resume.pdf"
        label = "Full Stack"
    else:
        path = p.get("resume_backend") or "data/resumes/backend_resume.pdf"
        label = "Backend"

    return path, label


class FindHREmailTool(BaseTool):
    name = "find_hr_email"
    description = "Find HR or recruiter email for a company"

    HR_KEYWORDS = ["hr", "recruit", "career", "job", "talent", "hire", "people"]

    def _get_snov_token(self, client_id: str, client_secret: str) -> Optional[str]:
        response = requests.post(
            "https://api.snov.io/v1/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")

    def _fetch_snov_emails(self, token: str, domain: str) -> List[dict]:
        response = requests.get(
            "https://api.snov.io/v2/domain-emails-with-info",
            params={
                "access_token": token,
                "domain": domain,
                "type": "all",
                "limit": 10,
                "lastId": 0,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        emails = data.get("data", [])
        return emails if isinstance(emails, list) else []

    def _rank_emails(self, emails: List[dict]) -> Tuple[List[dict], List[dict]]:
        """Return (verified, unverified), HR-first preference."""
        normalized = []
        for item in emails:
            email_value = item.get("email", "").strip()
            if not email_value:
                continue
            normalized.append(
                {
                    "email": email_value,
                    "status": str(item.get("status", "")).strip().lower(),
                }
            )

        hr_emails = [
            e for e in normalized
            if any(keyword in e["email"].lower() for keyword in self.HR_KEYWORDS)
        ]

        pool = hr_emails if hr_emails else normalized
        verified = [e for e in pool if e.get("status") == "verified"]
        unverified = [e for e in pool if e.get("status") != "verified"]

        return verified, unverified

    def _format_email_result(self, company: str, verified: List[dict], unverified: List[dict]) -> str:
        result = f"Emails for {company}:\n"

        if verified:
            result += "✅ VERIFIED (safe to send):\n"
            for e in verified[:3]:
                result += f"• {e['email']} (✓ verified)\n"

        if unverified:
            result += "⚠️ UNVERIFIED (may bounce):\n"
            for e in unverified[:3]:
                status = e.get("status") or "unverified"
                result += f"• {e['email']} ({status})\n"

        return result.strip()

    def _fallback_ddg_search(self, company: str) -> List[str]:
        from ddgs import DDGS

        results: List[str] = []

        with DDGS() as ddgs:
            for item in ddgs.text(
                f"{company} HR recruiter email careers India",
                max_results=5,
            ):
                body = f"{item.get('title', '')} {item.get('body', '')}"
                found = extract_emails(body)
                for email in found:
                    if any(keyword in email.lower() for keyword in self.HR_KEYWORDS):
                        results.append(email)

        return list(dict.fromkeys(results))

    def run(self, company: str = "") -> str:
        try:
            company = (company or "").strip()
            if not company:
                return "Find email error: company name is required."

            client_id = os.getenv("SNOV_CLIENT_ID")
            client_secret = os.getenv("SNOV_CLIENT_SECRET")

            if client_id and client_secret:
                try:
                    token = self._get_snov_token(client_id, client_secret)
                    if token:
                        domain = guess_company_domain(company)
                        if domain:
                            emails = self._fetch_snov_emails(token, domain)
                            if emails:
                                verified, unverified = self._rank_emails(emails)
                                if verified or unverified:
                                    return self._format_email_result(company, verified, unverified)
                except requests.RequestException:
                    pass
                except ValueError:
                    pass

            try:
                fallback_emails = self._fallback_ddg_search(company)
                if fallback_emails:
                    result = f"Emails for {company}:\n"
                    result += "⚠️ UNVERIFIED (web extracted):\n"
                    result += "\n".join(f"• {email}" for email in fallback_emails[:3])
                    return result
            except Exception:
                pass

            domain = guess_company_domain(company)
            if domain:
                return (
                    f"⚠️ Could not verify emails for {company}.\n"
                    f"Possible guesses:\n"
                    f"• hr@{domain}\n"
                    f"• careers@{domain}\n"
                    f"• recruit@{domain}"
                )

            return f"⚠️ Could not find or guess HR email for {company}."

        except Exception as e:
            return f"Find email error: {str(e)}"


class AutoApplyTool(BaseTool):
    name = "auto_apply"
    description = "Auto-apply to a job with correct resume attached"

    REQUIRE_VERIFIED_EMAIL = False

    def _pick_best_email(self, email_result: str):
    # Try verified first
     verified_emails = extract_verified_emails_from_result(email_result)
     if verified_emails:
        return verified_emails[0]
    # Always fall back to any email — never block
     all_emails = extract_emails(email_result)
     return all_emails[0] if all_emails else None

    def run(self, company: str = "", role: str = "") -> str:
        try:
            company = (company or "").strip()
            role = (role or "").strip()

            if not company:
                return "Auto apply error: company name is required."
            if not role:
                return "Auto apply error: role is required."

            p = ProfileManager()

            # Step 1 — Find HR email
            print(f"[AutoApply] Finding HR email for {company}...")
            email_finder = FindHREmailTool()
            email_result = email_finder.run(company)
            print(f"[AutoApply] Result: {email_result}")

            hr_email = self._pick_best_email(email_result)

            if not hr_email:
                if self.REQUIRE_VERIFIED_EMAIL:
                    return (
                        f"❌ No verified HR email found for {company}.\n"
                        f"Run: 'find hr email for {company}' to inspect options.\n"
                        f"Or manually use: 'send resume email to [email] for {role}'."
                    )
                return (
                    f"❌ Could not find any HR email for {company}.\n"
                    f"Run: 'find hr email for {company}' to inspect options."
                )

            print(f"[AutoApply] Using: {hr_email}")

            # Step 2 — Pick correct resume
            resume_path, resume_label = get_resume_for_role(role)
            print(f"[AutoApply] Resume: {resume_label} — {resume_path}")

            # Optional local sanity check only
            if not os.path.exists(resume_path):
                return (
                    f"Auto apply error: resume file not found.\n"
                    f"Expected: {resume_path}\n"
                    f"Role detected: {resume_label}"
                )

            # Step 3 — Write cover letter
            from src.tools.jobs_tool import CoverLetterTool, TrackApplicationTool
            cover_letter = CoverLetterTool().run(company=company, role=role)

            # Step 4 — Send email with resume
            name = p.get("name") or "Athul Dev"
            subject = f"Application for {role} — {name}"

            from src.tools.email_tool import SendEmailWithResumeTool
            send_result = SendEmailWithResumeTool().run(
                to=hr_email,
                subject=subject,
                body=cover_letter,
                role=role,
            )

            # Step 5 — Track application
            TrackApplicationTool().run(company=company, role=role, status="applied")

            return (
                f"✅ Applied to {role} at {company}.\n"
                f"📧 Sent to: {hr_email}\n"
                f"📄 Resume: {resume_label}\n"
                f"📋 Application tracked.\n"
                f"📨 {send_result}"
            )

        except Exception as e:
            return f"Auto apply error: {str(e)}"
        

import os
import re
import time
from urllib.parse import urlparse
from typing import List, Tuple

from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"


def normalize_company_name(company: str) -> str:
    if not company:
        return ""
    cleaned = company.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def guess_company_domain(company: str) -> str:
    base = normalize_company_name(company)
    return f"{base}.com" if base else ""


def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    found = re.findall(EMAIL_REGEX, text)
    return list(dict.fromkeys(found))


def extract_verified_emails_from_result(email_result: str) -> List[str]:
    if not email_result:
        return []
    verified_lines = [
        line for line in email_result.splitlines()
        if "✓ verified" in line.lower() or "verified" in line.lower()
    ]
    return extract_emails("\n".join(verified_lines))


def get_resume_for_role(role: str) -> Tuple[str, str]:
    p = ProfileManager()
    role_lower = (role or "").lower()

    if any(word in role_lower for word in ["ai", "machine learning", "ml", "data", "llm", "nlp"]):
        path = p.get("resume_ai") or "data/resumes/ai_resume.pdf"
        label = "AI Engineer"
    elif any(word in role_lower for word in ["fullstack", "full stack", "full-stack", "frontend", "react"]):
        path = p.get("resume_fullstack") or "data/resumes/fullstack_resume.pdf"
        label = "Full Stack"
    else:
        path = p.get("resume_backend") or "data/resumes/backend_resume.pdf"
        label = "Backend"

    return path, label


class FindHREmailTool(BaseTool):
    name = "find_hr_email"
    description = "Find HR or recruiter email for a company"

    HR_KEYWORDS = ["hr", "recruit", "career", "job", "talent", "hire", "people"]

    def _get_snov_token(self, client_id: str, client_secret: str):
        import requests
        response = requests.post(
            "https://api.snov.io/v1/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("access_token")

    def _fetch_snov_emails(self, token: str, domain: str) -> List[dict]:
        import requests
        response = requests.get(
            "https://api.snov.io/v2/domain-emails-with-info",
            params={
                "access_token": token,
                "domain": domain,
                "type": "all",
                "limit": 10,
                "lastId": 0,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        emails = data.get("data", [])
        return emails if isinstance(emails, list) else []

    def _rank_emails(self, emails: List[dict]) -> Tuple[List[dict], List[dict]]:
        normalized = []
        for item in emails:
            email_value = item.get("email", "").strip()
            if not email_value:
                continue
            normalized.append({
                "email": email_value,
                "status": str(item.get("status", "")).strip().lower(),
            })

        hr_emails = [
            e for e in normalized
            if any(keyword in e["email"].lower() for keyword in self.HR_KEYWORDS)
        ]

        pool = hr_emails if hr_emails else normalized
        verified = [e for e in pool if e.get("status") == "verified"]
        unverified = [e for e in pool if e.get("status") != "verified"]
        return verified, unverified

    def _format_email_result(self, company: str, verified: List[dict], unverified: List[dict]) -> str:
        result = f"Emails for {company}:\n"
        if verified:
            result += "✅ VERIFIED (safe to send):\n"
            for e in verified[:3]:
                result += f"• {e['email']} (✓ verified)\n"
        if unverified:
            result += "⚠️ UNVERIFIED (may bounce):\n"
            for e in unverified[:3]:
                status = e.get("status") or "unverified"
                result += f"• {e['email']} ({status})\n"
        return result.strip()

    def _fallback_ddg_search(self, company: str) -> List[str]:
        from ddgs import DDGS
        results: List[str] = []
        with DDGS() as ddgs:
            for item in ddgs.text(
                f"{company} HR recruiter email careers India",
                max_results=5,
            ):
                body = f"{item.get('title', '')} {item.get('body', '')}"
                found = extract_emails(body)
                for email in found:
                    if any(keyword in email.lower() for keyword in self.HR_KEYWORDS):
                        results.append(email)
        return list(dict.fromkeys(results))

    def run(self, company: str = "") -> str:
        import requests
        try:
            company = (company or "").strip()
            if not company:
                return "Find email error: company name is required."

            client_id = os.getenv("SNOV_CLIENT_ID")
            client_secret = os.getenv("SNOV_CLIENT_SECRET")

            if client_id and client_secret:
                try:
                    token = self._get_snov_token(client_id, client_secret)
                    if token:
                        domain = guess_company_domain(company)
                        if domain:
                            emails = self._fetch_snov_emails(token, domain)
                            if emails:
                                verified, unverified = self._rank_emails(emails)
                                if verified or unverified:
                                    return self._format_email_result(company, verified, unverified)
                except (requests.RequestException, ValueError):
                    pass

            try:
                fallback_emails = self._fallback_ddg_search(company)
                if fallback_emails:
                    result = f"Emails for {company}:\n"
                    result += "⚠️ UNVERIFIED (web extracted):\n"
                    result += "\n".join(f"• {email}" for email in fallback_emails[:3])
                    return result
            except Exception:
                pass

            domain = guess_company_domain(company)
            if domain:
                return (
                    f"⚠️ Could not verify emails for {company}.\n"
                    f"Possible guesses:\n"
                    f"• hr@{domain}\n"
                    f"• careers@{domain}\n"
                    f"• recruit@{domain}"
                )

            return f"⚠️ Could not find or guess HR email for {company}."

        except Exception as e:
            return f"Find email error: {str(e)}"


class AutoApplyTool(BaseTool):
    name = "auto_apply"
    description = "Auto-apply to a job with correct resume attached"

    REQUIRE_VERIFIED_EMAIL = False

    def _pick_best_email(self, email_result: str):
        verified_emails = extract_verified_emails_from_result(email_result)
        if verified_emails:
            return verified_emails[0]
        if self.REQUIRE_VERIFIED_EMAIL:
            return None
        all_emails = extract_emails(email_result)
        return all_emails[0] if all_emails else None

    def run(self, company: str = "", role: str = "") -> str:
        try:
            company = (company or "").strip()
            role = (role or "").strip()

            if not company:
                return "Auto apply error: company name is required."
            if not role:
                return "Auto apply error: role is required."

            p = ProfileManager()

            print(f"[AutoApply] Finding HR email for {company}...")
            email_finder = FindHREmailTool()
            email_result = email_finder.run(company)
            print(f"[AutoApply] Result: {email_result}")

            hr_email = self._pick_best_email(email_result)

            if not hr_email:
                return (
                    f"❌ No verified HR email found for {company}.\n"
                    f"Try: 'find hr email for {company}' to inspect options.\n"
                    f"Or: 'send resume email to [email] for {role} at {company}'"
                )

            print(f"[AutoApply] Using: {hr_email}")

            resume_path, resume_label = get_resume_for_role(role)
            print(f"[AutoApply] Resume: {resume_label} — {resume_path}")

            if not os.path.exists(resume_path):
                return (
                    f"Auto apply error: resume file not found.\n"
                    f"Expected: {resume_path}\n"
                    f"Role detected: {resume_label}"
                )

            from src.tools.jobs_tool import CoverLetterTool, TrackApplicationTool
            cover_letter = CoverLetterTool().run(company=company, role=role)

            name = p.get("name") or "Athul Dev"
            subject = f"Application for {role} — {name}"

            from src.tools.email_tool import SendEmailWithResumeTool
            send_result = SendEmailWithResumeTool().run(
                to=hr_email,
                subject=subject,
                body=cover_letter,
                role=role,
            )

            TrackApplicationTool().run(company=company, role=role, status="applied")

            return (
                f"✅ Applied to {role} at {company}.\n"
                f"📧 Sent to: {hr_email}\n"
                f"📄 Resume: {resume_label}\n"
                f"📋 Application tracked.\n"
                f"📨 {send_result}"
            )

        except Exception as e:
            return f"Auto apply error: {str(e)}"


class BulkApplyTool(BaseTool):
    name = "bulk_apply"
    description = "Find good job matches and apply only to relevant ones"

    # Real companies known to hire developers in Kochi/Kerala/Remote India
    KNOWN_COMPANIES = {
        "Backend Developer": [
            "Freshworks", "Zoho", "IBS Software", "UST Global",
            "QBurst", "Experion Technologies", "Chargebee",
            "Kissflow", "Speridian Technologies", "Envestnet",
            "Tata Consultancy Services", "Infosys", "Wipro",
        ],
        "Full Stack Developer": [
            "Freshworks", "Zoho", "Razorpay", "QBurst",
            "Experion Technologies", "BrowserStack", "Chargebee",
            "UST Global", "IBS Software", "Kissflow",
            "Postman", "Speridian Technologies",
        ],
        "AI Engineer": [
            "Freshworks", "Zoho", "Sarvam AI", "Mad Street Den",
            "Krutrim", "Tata Consultancy Services", "Infosys",
            "UST Global", "QBurst", "Experion Technologies",
        ],
    }

    def _infer_role(self, query: str) -> str:
        query_lower = (query or "").lower()
        if "ai" in query_lower or "ml" in query_lower:
            return "AI Engineer"
        if "fullstack" in query_lower or "full stack" in query_lower:
            return "Full Stack Developer"
        return "Backend Developer"

    def _search_jobs(self, query: str, location: str) -> List[dict]:
        """Search for jobs using DDG."""
        from ddgs import DDGS
        raw_jobs = []
        seen_urls = set()

        searches = [
            f"{query} jobs {location} 2026 hiring",
            f"site:linkedin.com/jobs/view {query} {location}",
            f"site:naukri.com {query} {location} apply",
        ]

        with DDGS() as ddgs:
            for search in searches:
                try:
                    for r in ddgs.text(search, max_results=5):
                        url = r.get("href", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            raw_jobs.append({
                                "title": r.get("title", ""),
                                "body": r.get("body", ""),
                                "url": url,
                            })
                except Exception:
                    continue

        return raw_jobs

    def _score_job(self, job: dict, role: str, skill_list: List[str]) -> int:
        """Score a job listing for relevance."""
        title_lower = job["title"].lower()
        body_lower = job["body"].lower()
        combined = title_lower + " " + body_lower
        score = 0

        role_keywords = {
            "Backend Developer": ["backend", "python", "fastapi", "django", "api", "flask", "node"],
            "Full Stack Developer": ["fullstack", "full stack", "react", "frontend", "vue", "angular"],
            "AI Engineer": ["ai", "machine learning", "llm", "nlp", "deep learning", "ml engineer"],
        }

        if any(w in title_lower for w in ["developer", "engineer", "programmer", "software"]):
            score += 30

        for kw in role_keywords.get(role, []):
            if kw in title_lower:
                score += 20
            elif kw in body_lower:
                score += 10

        for skill in skill_list:
            if len(skill) > 2 and skill in combined:
                score += 8

        if any(w in combined for w in ["kochi", "kerala", "remote", "wfh", "work from home"]):
            score += 20

        if any(w in title_lower for w in ["senior", "lead", "manager", "director", "head", "principal"]):
            score -= 15

        if any(w in title_lower for w in ["sales", "marketing", "accountant", "finance"]):
            score -= 50

        return score

    def _find_companies_from_jobs(self, scored_jobs: List[dict]) -> List[str]:
        """Try to extract real company names from LinkedIn direct job pages only."""
        companies = []

        for job in scored_jobs[:10]:
            url = job.get("url", "")
            title = job.get("title", "")

            # Only extract from LinkedIn direct job view pages
            if "linkedin.com/jobs/view" not in url:
                continue

            # Pattern: "Job Title at Company Name"
            match = re.search(
                r"\bat\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s+in\s|\s*[-|–|·]|$)",
                title
            )
            if match:
                candidate = match.group(1).strip().rstrip(".,- ")
                # Validate
                skip = {
                    "backend", "developer", "engineer", "software", "jobs",
                    "job", "hiring", "fresher", "kochi", "kerala", "india",
                    "remote", "python", "react", "fullstack", "full stack"
                }
                words = candidate.lower().split()
                if (2 < len(candidate) < 40 and
                        not any(w in skip for w in words)):
                    if candidate not in companies:
                        companies.append(candidate)
                        print(f"[BulkApply] Found company from LinkedIn: {candidate}")

        return companies

    def run(self, query: str = "") -> str:
        try:
            p = ProfileManager()
            location = p.get("location") or "Kochi Kerala"
            role = self._infer_role(query)
            skills = (p.get("skills") or "").lower()
            skill_list = [s.strip() for s in skills.split(",") if s.strip()]

            print(f"[BulkApply] Searching {role} jobs...")

            # Step 1 — Search jobs
            raw_jobs = self._search_jobs(query or role, location)
            print(f"[BulkApply] Raw jobs found: {len(raw_jobs)}")

            if not raw_jobs:
                return "No jobs found. Check internet connection."

            # Step 2 — Score jobs
            scored = []
            for job in raw_jobs:
                score = self._score_job(job, role, skill_list)
                if score >= 25:
                    job["score"] = score
                    scored.append(job)

            scored.sort(key=lambda x: x["score"], reverse=True)
            print(f"[BulkApply] Scored jobs: {len(scored)}")

            # Step 3 — Build report of found jobs
            report = f"🎯 Found {len(scored) if scored else len(raw_jobs)} jobs for {role}:\n\n"
            display_jobs = scored[:6] if scored else raw_jobs[:6]
            for i, job in enumerate(display_jobs, 1):
                report += f"{i}. {job['title']}\n"
                if "score" in job:
                    report += f"   📊 Match: {job['score']}%\n"
                report += f"   🔗 {job['url'][:80]}\n\n"

            # Step 4 — Get companies to apply to
            # First try extracting from LinkedIn direct pages
            companies = self._find_companies_from_jobs(scored if scored else raw_jobs)

            # Always use known companies as primary/fallback
            known = self.KNOWN_COMPANIES.get(role, ["Freshworks", "Zoho", "Chargebee"])

            # Mix extracted + known, deduplicated
            all_companies = companies + [c for c in known if c not in companies]
            apply_to = all_companies[:3]

            if companies:
                report += f"📌 Found companies from job listings: {', '.join(companies)}\n"
            report += f"📤 Applying to: {', '.join(apply_to)}\n\n"

            print(f"[BulkApply] Applying to: {apply_to}")

            # Step 5 — Apply with delay
            auto_apply = AutoApplyTool()
            applied = 0
            skipped = 0

            for company in apply_to:
                print(f"[BulkApply] Applying to {company}...")
                result = auto_apply.run(company=company, role=role)

                if "No verified" in result or "❌" in result:
                    report += f"⏭️ {company}: Skipped — no verified HR email\n"
                    skipped += 1
                elif "✅" in result:
                    report += f"✅ {company}: Application sent!\n"
                    applied += 1
                else:
                    report += f"⚠️ {company}: {result[:80]}\n"
                    skipped += 1

                time.sleep(3)

            report += f"\n📊 Summary: {applied} sent, {skipped} skipped"
            return report

        except Exception as e:
            return f"Bulk apply error: {str(e)}"
