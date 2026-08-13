import os
import re
import json
import time
import requests
from typing import List, Tuple, Optional

from src.tools.base import BaseTool
from src.memory.profile import ProfileManager
from src.tools.email_tool import get_gmail_service
from src.tools.email_verifier import domain_has_mx


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


AI_ENGINEER_KEYWORDS = [
    "machine learning", "ml", "deep learning", "llm", "nlp", "ai engineer",
    "genai", "generative ai", "rag", "langchain", "transformer", "pytorch",
    "tensorflow", "prompt engineering", "computer vision", "data science",
    "embeddings", "vector database", "chroma",
]

BACKEND_AI_SYSTEMS_KEYWORDS = [
    "backend", "api", "microservice", "system design", "infrastructure",
    "fastapi", "django", "node", "database", "postgresql", "mongodb",
    "docker", "kubernetes", "distributed systems", "scalability",
    "devops", "backend engineer", "full stack",
]

RESUME_PROFILES = [
    {
        "label": "AI Engineer Resume",
        "path": "data/resumes/AI_Engineer.pdf",
        "keywords": AI_ENGINEER_KEYWORDS,
    },
    {
        "label": "Backend & AI Systems Engineer Resume",
        "path": "data/resumes/Backend___AI_Systems_Engineer.pdf",
        "keywords": BACKEND_AI_SYSTEMS_KEYWORDS,
    },
]

DEFAULT_RESUME_PROFILE = RESUME_PROFILES[0]  # used only if nothing else matches/exists


def get_resume_for_role(role: str, jd_text: str = "") -> Tuple[str, str]:
    p = ProfileManager()

    # Explicit manual override always wins, if set and present
    override_path = p.get("resume_path")
    if override_path and os.path.exists(override_path):
        return override_path, "Manual Override Resume"

    combined = f"{role or ''} {jd_text or ''}".lower()

    best_profile, best_score = None, -1
    for profile in RESUME_PROFILES:
        if not os.path.exists(profile["path"]):
            continue
        score = sum(1 for kw in profile["keywords"] if kw in combined)
        if score > best_score:
            best_score, best_profile = score, profile

    if best_profile and best_score > 0:
        return best_profile["path"], best_profile["label"]

    # No keyword signal — fall back to whichever profiled resume exists
    for profile in RESUME_PROFILES:
        if os.path.exists(profile["path"]):
            return profile["path"], profile["label"]

    # Nothing on disk at all
    return DEFAULT_RESUME_PROFILE["path"], DEFAULT_RESUME_PROFILE["label"] + " (missing on disk)"


class FindHREmailTool(BaseTool):
    name = "find_hr_email"
    description = "Find HR or recruiter email for a company, falling back to a real published contact email (checked against the company's own domain) before ever guessing"

    HR_KEYWORDS = ["hr", "recruit", "career", "job", "talent", "hire", "people"]

    CONTACT_PATH_CANDIDATES = ["/careers", "/jobs", "/contact", "/contact-us", "/about", ""]
    PRIORITY_PREFIXES = ("careers", "jobs", "recruiting", "recruitment", "talent", "hr")
    GENERIC_CONTACT_PREFIXES = ("contact", "info", "hello", "support", "admin", "office")
    AVOID_PREFIXES = (
        "sales", "billing", "accounts", "legal", "press", "media",
        "noreply", "no-reply", "notifications", "notification",
        "donotreply", "do-not-reply", "automated", "system", "bot",
    )
    # Third-party ATS/recruiting platform domains — an email here is the
    # vendor's, not the company's, even if scraped off the company's own
    # careers page (embedded widgets leak these constantly)
    ATS_VENDOR_DOMAINS = (
        "smartrecruiters.com", "greenhouse.io", "lever.co", "workday.com",
        "myworkdayjobs.com", "bamboohr.com", "icims.com", "jobvite.com",
        "taleo.net", "successfactors.com", "breezy.hr", "recruitee.com",
    )

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
        return response.json().get("access_token")

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
        time.sleep(2)
        with DDGS() as ddgs:
            for item in ddgs.text(f"{company} HR recruiter email careers India", max_results=5):
                body = f"{item.get('title', '')} {item.get('body', '')}"
                found = extract_emails(body)
                for email in found:
                    if any(keyword in email.lower() for keyword in self.HR_KEYWORDS):
                        # Same domain-relevance check used in _find_general_contact_email —
                        # without this, unrelated companies' HR emails slip through just
                        # because they happened to appear in a search result's text
                        if self._is_company_domain(email, company):
                            results.append(email)
        return list(dict.fromkeys(results))

    def _scrape_emails_from_url(self, url: str) -> List[str]:
        try:
            res = requests.get(url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if res.status_code != 200:
                return []
            return extract_emails(res.text)
        except Exception:
            return []

    def _is_company_domain(self, email: str, company: str) -> bool:
        """Rejects emails on unrelated third-party domains — ATS widgets
        embedded on a careers page frequently leak their own notification
        addresses, which have nothing to do with the actual company."""
        email_domain = email.split("@")[-1].lower()

        if any(vendor in email_domain for vendor in self.ATS_VENDOR_DOMAINS):
            return False

        company_normalized = normalize_company_name(company)
        if not company_normalized:
            return False
        return company_normalized in email_domain

    def _find_general_contact_email(self, company: str) -> Optional[str]:
        """Checks the company's careers/contact pages directly first — these
        exist specifically to publish the kind of address a job application
        should go to. Falls back to DDG-discovered site + same page checks
        only if the direct domain guess doesn't resolve at all. Filters out
        any email whose domain isn't actually the company's own."""
        all_found: List[str] = []

        guessed_domain = guess_company_domain(company)
        if guessed_domain and domain_has_mx(guessed_domain):
            for path in self.CONTACT_PATH_CANDIDATES:
                for scheme in ("https://", "http://"):
                    url = f"{scheme}{guessed_domain}{path}"
                    found = self._scrape_emails_from_url(url)
                    if found:
                        print(f"[GeneralContact] {url} -> {found[:5]}")
                        all_found.extend(found)
                    if len(all_found) >= 5:
                        break
                if len(all_found) >= 5:
                    break

        if not all_found:
            try:
                from ddgs import DDGS
                time.sleep(2)
                with DDGS() as ddgs:
                    results = list(ddgs.text(f"{company} official website careers contact", max_results=2))
                print(f"[GeneralContact] '{company}' DDG fallback -> {len(results)} results")

                for r in results:
                    base_url = r.get("href", "")
                    if not base_url:
                        continue
                    m = re.match(r'https?://([^/]+)', base_url)
                    if not m:
                        continue
                    found_domain = m.group(1)
                    for path in self.CONTACT_PATH_CANDIDATES:
                        url = f"https://{found_domain}{path}"
                        found = self._scrape_emails_from_url(url)
                        if found:
                            print(f"[GeneralContact] {url} -> {found[:5]}")
                            all_found.extend(found)
                    if all_found:
                        break
            except Exception as e:
                print(f"[GeneralContact] DDG fallback error for '{company}': {e}")

        if not all_found:
            return None

        all_found = list(dict.fromkeys(all_found))

        # Reject anything not actually on the company's own domain —
        # catches ATS-vendor notification addresses like SmartRecruiters
        all_found = [e for e in all_found if self._is_company_domain(e, company)]

        if not all_found:
            print(f"[GeneralContact] All candidates for '{company}' rejected as off-domain/ATS-vendor")
            return None

        for email in all_found:
            local_part = email.split("@")[0].lower()
            if any(kw in local_part for kw in self.PRIORITY_PREFIXES):
                return email

        for email in all_found:
            local_part = email.split("@")[0].lower()
            if local_part in self.GENERIC_CONTACT_PREFIXES:
                return email

        for email in all_found:
            local_part = email.split("@")[0].lower()
            if local_part not in self.AVOID_PREFIXES:
                return email

        return all_found[0]

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
                except (requests.RequestException, ValueError):
                    pass

            try:
                fallback_emails = self._fallback_ddg_search(company)
                if fallback_emails:
                    result = f"Emails for {company}:\n⚠️ UNVERIFIED (web extracted):\n"
                    result += "\n".join(f"• {email}" for email in fallback_emails[:3])
                    return result
            except Exception:
                pass

            general_email = self._find_general_contact_email(company)
            if general_email and domain_has_mx(general_email.split("@")[-1]):
                return f"Emails for {company}:\n⚠️ GENERAL CONTACT (not HR-specific, but real, on-domain, and found):\n• {general_email}"

            domain = guess_company_domain(company)
            if domain:
                base = domain.replace(".com", "")
                candidate_domains = [domain, f"{base}.in", f"{base}.co.in", f"{base}.org"]
                working_domain = next((d for d in candidate_domains if domain_has_mx(d)), None)

                if working_domain:
                    return (
                        f"⚠️ No directory match for {company}, but {working_domain} is a live mail domain.\n"
                        f"Best-guess addresses (unverified mailbox — may still bounce):\n"
                        f"• hr@{working_domain}\n• careers@{working_domain}\n• recruit@{working_domain}"
                    )

            return f"❌ Could not find or guess a working email domain for {company}. Try a more specific company name or check LinkedIn manually."

        except Exception as e:
            return f"Find email error: {str(e)}"


class AutoApplyTool(BaseTool):
    name = "auto_apply"
    description = "Auto-apply to a job by finding HR email, extracting stored JD context, generating a cover letter, and sending email with resume attached."

    REQUIRE_VERIFIED_EMAIL = False

    def _pick_best_email(self, email_result: str):
        verified_emails = extract_verified_emails_from_result(email_result)
        candidates = verified_emails if verified_emails else extract_emails(email_result)
        valid_candidates = [e for e in candidates if domain_has_mx(e.split("@")[-1])]
        if valid_candidates:
            return valid_candidates[0]
        return None

    def run(self, company: str = "", role: str = "", job_index: int = None, track: bool = True, jd: str = "") -> str:
        try:
            company = (company or "").strip()
            role = (role or "").strip()
            p = ProfileManager()

            jd_text = jd
            if not jd_text:
                latest_jobs_json = p.get("latest_job_search")
                if latest_jobs_json:
                    try:
                        jobs_list = json.loads(latest_jobs_json)
                        if isinstance(jobs_list, list) and len(jobs_list) > 0:
                            if job_index is not None and 1 <= job_index <= len(jobs_list):
                                target_job = jobs_list[job_index - 1]
                                company = company or target_job.get("company", "Hiring Company")
                                role = role or target_job.get("title", "Developer")
                                jd_text = target_job.get("description", "")
                            else:
                                for j in jobs_list:
                                    c_name = j.get("company", "").lower()
                                    t_name = j.get("title", "").lower()
                                    if (company and company.lower() in c_name) or (company and company.lower() in t_name):
                                        jd_text = j.get("description", "")
                                        role = role or j.get("title")
                                        break
                                if not jd_text:
                                    jd_text = jobs_list[0].get("description", "")
                    except Exception as parse_err:
                        print(f"[AutoApply] Memory parse error: {parse_err}")

            if not company:
                return "Auto apply error: company name or valid job selection is required."
            if not role:
                role = "Full Stack AI Developer"

            print(f"[AutoApply] Locating HR contact for {company}...")
            email_result = FindHREmailTool().run(company)
            hr_email = self._pick_best_email(email_result)

            if not hr_email:
                return f"❌ No email with a valid, existing domain found for {company} — skipping to avoid a guaranteed bounce. Raw lookup result:\n{email_result}"

            print(f"[AutoApply] Target HR Email: {hr_email}")

            resume_path, resume_label = get_resume_for_role(role, jd_text)
            if not os.path.exists(resume_path):
                    return f"Auto apply error: master resume file not found at path: {resume_path}"

            from src.tools.jobs_tool import CoverLetterTool, TrackApplicationTool
            cover_letter = CoverLetterTool().run(company=company, role=role, jd=jd_text)

            name = p.get("name") or "Athul Dev"
            subject = f"Application for {role} — {name}"

            from src.tools.email_tool import SendEmailWithResumeTool
            send_result = SendEmailWithResumeTool().run(
                to=hr_email,
                subject=subject,
                body=cover_letter,
                role=role,
            )

            send_failed = "❌" in send_result or "error" in send_result.lower()
            if track:
                TrackApplicationTool().run(
                    company=company, role=role,
                    status=("failed" if send_failed else "applied")
                )

            if send_failed:
                return (
                    f"❌ Application to {company} failed during dispatch.\n"
                    f"👤 Position: {role}\n"
                    f"📧 Attempted: {hr_email}\n"
                    f"📨 Result: {send_result}"
                )

            return (
                f"✅ Application successfully dispatched to {company}.\n"
                f"👤 Position: {role}\n"
                f"📧 Sent to: {hr_email}\n"
                f"📄 Resume: {resume_label} ({resume_path})\n"
                f"📋 Status: Application tracked in database.\n"
                f"📨 Dispatch Result: {send_result}"
            )

        except Exception as e:
            return f"Auto apply error: {str(e)}"


class BulkApplyTool(BaseTool):
    name = "bulk_apply"
    description = "Apply to all jobs found in the recent search results"

    def run(self, query: str = "") -> str:
        try:
            p = ProfileManager()
            latest_jobs = p.get("latest_job_search")

            if not latest_jobs:
                return "No recent job search found. Please search for jobs first."

            jobs = json.loads(latest_jobs)
            auto_apply = AutoApplyTool()
            report = f"🎯 Starting bulk apply for {len(jobs)} jobs:\n\n"
            applied, skipped = 0, 0

            for idx, job in enumerate(jobs[:5], 1):
                company = job.get("company", "Hiring Company")
                role = job.get("title", "Developer")

                result = auto_apply.run(company=company, role=role, job_index=idx)
                if "❌" in result or "error" in result.lower():
                    report += f"⏭️ Job #{idx} ({company}): Skipped — {result}\n"
                    skipped += 1
                else:
                    report += f"✅ Job #{idx} ({company}): Application dispatched!\n"
                    applied += 1

            report += f"\n📊 Summary: {applied} sent, {skipped} skipped"
            return report

        except Exception as e:
            return f"Bulk apply error: {str(e)}"