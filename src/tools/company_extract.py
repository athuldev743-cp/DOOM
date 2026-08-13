import re

def extract_company(title: str, platform: str) -> str:
    title = title or ""

    if platform == "linkedin":
        m = re.match(r'^(.*?)\s+hiring\s+', title, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ""

    

    if platform == "wellfound":
        m = re.search(r'\bat\s+(.+)$', title, re.IGNORECASE)
        if m:
            return re.split(r'\s*[\|\-•]\s*', m.group(1))[0].strip()

    # Naukri (and Wellfound-without-"at"): company is typically the LAST
    # ' - '-separated segment, often followed by ", Location, years..."
    parts = [p.strip() for p in title.split(' - ') if p.strip()]
    if len(parts) >= 2:
        last = parts[-1]
        # Cut at the first comma — drops trailing location/experience text
        company = last.split(',')[0].strip()
        # Guard against a segment that's actually just years/experience text
        if company and not re.match(r'^\d', company) and 'year' not in company.lower():
            return company
    return ""