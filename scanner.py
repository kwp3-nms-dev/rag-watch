"""
Security scanner: ClamAV + prompt injection + obfuscation detection.
Returns a ScanResult for every file before ingestion.
"""
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from config import CLAMAV_ENABLED, CLAMSCAN_BIN


@dataclass
class ScanResult:
    clean: bool
    reasons: List[str] = field(default_factory=list)

    def flag(self, reason: str) -> None:
        self.clean = False
        self.reasons.append(reason)


# ---------------------------------------------------------------------------
# ClamAV
# ---------------------------------------------------------------------------

def _scan_clamav(path: Path, result: ScanResult) -> None:
    if not CLAMAV_ENABLED:
        return
    try:
        proc = subprocess.run(
            [CLAMSCAN_BIN, "--no-summary", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 1:
            result.flag(f"ClamAV: {proc.stdout.strip()}")
        elif proc.returncode not in (0, 1):
            result.flag(f"ClamAV error (rc={proc.returncode}): {proc.stderr.strip()}")
    except FileNotFoundError:
        result.flag("ClamAV not found — skipped (install clamav)")
    except subprocess.TimeoutExpired:
        result.flag("ClamAV scan timed out")


# ---------------------------------------------------------------------------
# Prompt injection patterns
# ---------------------------------------------------------------------------

INJECTION_PATTERNS = [
    # Instruction override
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"disregard\s+(all\s+)?previous\s+instructions?",
    r"forget\s+(all\s+)?previous\s+instructions?",
    r"new\s+instructions?(\s*:|\s+follow)",
    r"you\s+are\s+now\s+(a\s+)?(\w+\s+)?(assistant|ai|bot|model|gpt|claude)",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(\w+\s+)?(assistant|ai|bot)",
    r"(system|user|assistant)\s*:\s*\[?(ignore|override|bypass|jailbreak)",
    # Role/persona hijacking
    r"pretend\s+(you\s+are|to\s+be)\s+",
    r"roleplay\s+as\s+",
    r"simulate\s+(being\s+)?(a\s+)?",
    r"you\s+have\s+no\s+(restrictions?|limits?|rules?|guidelines?)",
    r"(bypass|override|disable)\s+(your\s+)?(safety|filter|restriction|guideline)",
    # Data exfiltration
    r"(print|output|reveal|show|expose|leak)\s+(all\s+)?(system\s+)?(prompt|instruction|context|config)",
    r"(what\s+(are|is)\s+your\s+(instructions?|system\s+prompt))",
    # Jailbreak markers
    r"\[/?INST\]",
    r"<\|?(system|user|assistant|im_start|im_end)\|?>",
    r"###\s*(instruction|system|prompt|human|assistant)",
    r"```\s*(system|prompt|instructions?)",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS]


def _scan_prompt_injection(text: str, result: ScanResult) -> None:
    for pattern in _COMPILED_PATTERNS:
        m = pattern.search(text)
        if m:
            snippet = text[max(0, m.start()-30):m.end()+30].replace("\n", " ")
            result.flag(f"Prompt injection pattern: '{snippet.strip()}'")
            return  # one finding is enough to flag


# ---------------------------------------------------------------------------
# Obfuscation detection
# ---------------------------------------------------------------------------

# Zero-width and invisible Unicode characters
_INVISIBLE_CHARS = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff\u00ad]"
)

# Suspiciously long base64-looking strings (40+ chars of base64 alphabet)
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

# Excessive non-ASCII ratio (>40% non-ASCII in a chunk suggests obfuscation)
def _non_ascii_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if ord(c) > 127) / len(text)

# Unicode homoglyph: mix of Latin + Cyrillic/Greek lookalikes in same word
_HOMOGLYPH_SCRIPTS = re.compile(
    r"[a-zA-Z]+[а-яА-ЯёЁ\u0370-\u03ff]+|[а-яА-ЯёЁ\u0370-\u03ff]+[a-zA-Z]+"
)


def _scan_obfuscation(text: str, result: ScanResult) -> None:
    # Invisible characters
    if _INVISIBLE_CHARS.search(text):
        result.flag("Obfuscation: invisible/zero-width Unicode characters detected")
        return

    # Homoglyphs
    if _HOMOGLYPH_SCRIPTS.search(text):
        result.flag("Obfuscation: mixed-script homoglyph characters detected")
        return

    # High non-ASCII ratio
    ratio = _non_ascii_ratio(text)
    if ratio > 0.40:
        result.flag(f"Obfuscation: high non-ASCII character ratio ({ratio:.0%})")
        return

    # Large base64 blobs
    blobs = _BASE64_BLOB.findall(text)
    if len(blobs) >= 3:
        result.flag(f"Obfuscation: {len(blobs)} large base64-like blobs detected")
        return


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(path: Path, text: str) -> ScanResult:
    """Run all security checks on a file. Returns ScanResult."""
    result = ScanResult(clean=True)
    _scan_clamav(path, result)
    _scan_prompt_injection(text, result)
    _scan_obfuscation(text, result)
    return result
