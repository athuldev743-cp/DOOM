# DOOM Job Search and Application Workflow

## Intended workflow
The job-search automation concept is human-reviewed:
1. Discover jobs.
2. Rank and score job descriptions against the user's target profile.
3. Present a shortlist for review.
4. Prepare a tailored CV and cover letter for an approved job.
5. Prepare an email where appropriate.
6. Let the user complete submission on LinkedIn, Wellfound, Indeed, or an employer portal.
7. Track the application status after the user confirms submission.
8. Keep generated application documents organized.

The system should not silently submit applications or send emails without explicit approval.

## Related tools
The inspected MCP registry includes `job_search`, `score_jd`, `cover_letter`, `track_application`, `list_applications`, and `find_hr_email`, along with email and lead tools.

## Job sources and OAuth
LinkedIn OAuth is not required for public job discovery. Public search sources may include job listings that identify LinkedIn as their source, without requiring LinkedIn account OAuth. Do not remove LinkedIn source metadata merely because LinkedIn OAuth was removed.

## Data and evaluation
Useful measures include:
- Relevant jobs among the top 5 or top 20.
- Job-description scoring agreement with a human-reviewed set.
- CV/cover-letter generation completeness.
- Application state consistency.
- Duplicate job detection.
- Human approval and submission confirmation rates.

Do not claim automated application submission unless that capability is implemented, tested, and intentionally enabled.
