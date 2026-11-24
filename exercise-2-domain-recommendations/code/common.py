"""Shared helpers for the domain recommendation pipeline (Exercise 2)."""
import re

IPV4 = re.compile(r"\d{1,3}(\.\d{1,3}){3}")
# No public suffix list is available offline in the build environment, so a small set of common
# second-level labels is used for country domains (example.co.uk). A production run should use the real list.
SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "or", "ne", "go"}

def is_ip(host: str) -> bool:
    return bool(IPV4.fullmatch(host))

def registrable(host: str) -> str:
    """'a.b.example.co.uk' -> 'example.co.uk'; 'www.google.com' -> 'google.com'."""
    p = host.split(".")
    if len(p) >= 3 and p[-2] in SECOND_LEVEL and len(p[-1]) == 2:
        return ".".join(p[-3:])
    return ".".join(p[-2:])
