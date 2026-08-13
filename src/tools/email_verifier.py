import smtplib
import socket
import dns.resolver
from typing import Optional


def domain_has_mx(domain: str) -> bool:
    """True if the domain has an MX (or fallback A) record — i.e. it can actually receive mail.
    This is the check that catches guessed/typo'd domains before you ever try to send to them."""
    if not domain:
        return False
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        return len(answers) > 0
    except Exception:
        pass
    try:
        dns.resolver.resolve(domain, "A", lifetime=5)
        return True
    except Exception:
        return False


def get_mx_host(domain: str) -> Optional[str]:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        best = min(answers, key=lambda r: r.preference)
        return str(best.exchange).rstrip(".")
    except Exception:
        return None


def smtp_probe(email: str, from_address: str = "verify@example.com") -> Optional[bool]:
    """
    Best-effort mailbox check WITHOUT sending mail: connect to the domain's
    mail server and ask if the address would be accepted (RCPT TO), then quit.

    Returns True (likely valid), False (server explicitly rejected it),
    or None (inconclusive — catch-all domain, greylisting, or the network
    blocked outbound port 25, which most cloud hosts do by default).

    NOTE: on Railway/Render/Hugging Face Spaces this will usually return
    None because outbound port 25 is blocked. Only reliable when run from
    a network that allows it (e.g. your local machine, most residential ISPs
    also block it though — test before relying on this).
    """
    try:
        domain = email.split("@")[-1]
    except IndexError:
        return False

    mx_host = get_mx_host(domain)
    if not mx_host:
        return False

    try:
        with smtplib.SMTP(timeout=8) as server:
            server.connect(mx_host, 25)
            server.helo("verifycheck.local")
            server.mail(from_address)
            code, _ = server.rcpt(email)
            server.quit()
            if code == 250:
                return True
            if code in (550, 551, 553, 501, 503):
                return False
            return None
    except (smtplib.SMTPException, socket.error, TimeoutError, OSError):
        return None