"""
PII (Personally Identifiable Information) detector for LLM output streams.

Detects Chinese PII patterns in text and provides masking/blocking.
Covers: ID numbers, phone numbers, bank accounts, addresses, names.

Design: streaming-friendly — processes text chunks incrementally.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class PiiSeverity(str, Enum):
    LOW = "low"        # e.g., city name
    MEDIUM = "medium"  # e.g., partial account number
    HIGH = "high"      # e.g., full ID number
    CRITICAL = "critical"  # e.g., ID number + name + bank account together


@dataclass
class PiiMatch:
    """A single PII detection match."""
    type: str           # "id_card", "phone", "bank_card", "address"
    value: str          # The original matched text
    masked: str         # The masked version
    start: int = 0      # Position in text
    end: int = 0
    severity: PiiSeverity = PiiSeverity.HIGH


# ── Pattern Definitions ──

# Chinese ID card (18 digits — 6 area + 8 birth + 3 sequence + 1 checksum)
_ID_CARD_RE = _re.compile(
    r"(?<!\d)"  # Not preceded by digit
    r"[1-9]\d{5}"  # Area code (6 digits)
    r"(?:19|20)\d{2}"  # Year
    r"(?:0[1-9]|1[0-2])"  # Month
    r"(?:0[1-9]|[12]\d|3[01])"  # Day
    r"\d{3}"  # Sequence
    r"[\dXx]"  # Checksum
    r"(?!\d)",  # Not followed by digit
)

# Chinese mobile phone (1xx-xxxx-xxxx)
_PHONE_RE = _re.compile(
    r"(?<!\d)"
    r"1[3-9]\d{9}"
    r"(?!\d)",
)

# Chinese landline (0xx-xxxxxxxx or 0xxx-xxxxxxxx)
_LANDLINE_RE = _re.compile(
    r"(?<!\d)"
    r"0\d{2,3}-\d{7,8}"
    r"(?!\d)",
)

# Bank card (16-19 digits, can be grouped like 6222 xxxx xxxx xxxx)
_BANK_CARD_RE = _re.compile(
    r"(?<!\d)"
    r"(?:62|60|58|52|53|54|55|42|43|44|45|46|47|48|49|40|41)\d{14,17}"
    r"(?!\d)",
)

# Bank card grouped format: "6222 1234 5678 9012"
_BANK_CARD_GROUPED_RE = _re.compile(
    r"\d{4}[ ]\d{4}[ ]\d{4}[ ]\d{4,7}",
)

# Chinese province list (simplified for regex)
_PROVINCES = (
    r"北京|天津|上海|重庆|"
    r"河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|"
    r"湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|台湾|"
    r"内蒙古|广西|西藏|宁夏|新疆"
)

# Detailed Chinese address pattern
_ADDRESS_RE = _re.compile(
    r"(?:" + _PROVINCES + r")"
    r"省?市?"
    r"[^\s,，。；;]{0,20}?"
    r"(?:路|街|道|巷|弄|号|楼|栋|单元|室|层|座|幢|苑|园|区|村|镇|乡|庄|营|屯|旗|苏木)",
)

# Chinese name pattern (2-4 Chinese characters)
_NAME_RE = _re.compile(
    r"(?:洪|王|李|张|刘|陈|杨|赵|黄|周|吴|徐|孙|胡|朱|高|林|何|郭|马|罗|梁|宋|郑|谢|韩|唐|冯|于|董|萧|程|曹|袁|邓|许|傅|沈|曾|彭|吕|苏|卢|蒋|蔡|贾|丁|魏|薛|叶|阎|余|潘|杜|戴|夏|钟|汪|田|任|姜|范|方|石|姚|谭|廖|邹|熊|金|陆|郝|孔|白|崔|康|毛|邱|秦|江|史|顾|侯|邵|孟|龙|万|段|雷|钱|汤|尹|黎|易|常|武|乔|贺|赖|龚|文)"
    r"[一-鿿]{1,3}"
    r"(?![一-鿿])",
)


def mask_id_card(value: str) -> str:
    """Mask: 310101199001011234 → 310***********1234"""
    return value[:3] + "*" * 11 + value[-4:]


def mask_phone(value: str) -> str:
    """Mask: 13812345678 → 138****5678"""
    return value[:3] + "*" * 4 + value[-4:]


def mask_bank_card(value: str) -> str:
    """Mask: 6222123456789012 → 6222****9012"""
    clean = value.replace(" ", "")
    return clean[:4] + "*" * (len(clean) - 8) + clean[-4:]


def mask_address(value: str) -> str:
    """Mask: 上海市浦东新区陆家嘴环路1000号 → 上海市浦东新区****"""
    if len(value) <= 6:
        return value
    return value[:6] + "*" * min(len(value) - 6, 8)


# Pattern → mask function mapping
_PII_RULES: list[tuple[_re.Pattern, str, PiiSeverity, Callable[[str], str]]] = [
    (_ID_CARD_RE, "id_card", PiiSeverity.HIGH, mask_id_card),
    (_PHONE_RE, "phone", PiiSeverity.HIGH, mask_phone),
    (_BANK_CARD_RE, "bank_card", PiiSeverity.CRITICAL, mask_bank_card),
    (_BANK_CARD_GROUPED_RE, "bank_card_grouped", PiiSeverity.CRITICAL, mask_bank_card),
    (_LANDLINE_RE, "landline", PiiSeverity.MEDIUM, lambda v: v[:4] + "*" * (len(v) - 4)),
    (_ADDRESS_RE, "address", PiiSeverity.HIGH, mask_address),
]


@dataclass
class PiiScanResult:
    """Result of scanning text for PII."""
    has_pii: bool = False
    matches: list[PiiMatch] = field(default_factory=list)
    pii_types: set[str] = field(default_factory=set)
    severity: PiiSeverity = PiiSeverity.LOW
    masked_text: str = ""


def scan_text(text: str) -> PiiScanResult:
    """Scan text for PII patterns and return detection results."""
    if not text:
        return PiiScanResult()

    matches: list[PiiMatch] = []
    pii_types: set[str] = set()
    max_severity = PiiSeverity.LOW

    for pattern, pii_type, severity, mask_fn in _PII_RULES:
        for m in pattern.finditer(text):
            value = m.group()
            masked = mask_fn(value)
            matches.append(PiiMatch(
                type=pii_type,
                value=value,
                masked=masked,
                start=m.start(),
                end=m.end(),
                severity=severity,
            ))
            pii_types.add(pii_type)
            if severity == PiiSeverity.CRITICAL:
                max_severity = PiiSeverity.CRITICAL
            elif severity == PiiSeverity.HIGH and max_severity != PiiSeverity.CRITICAL:
                max_severity = PiiSeverity.HIGH
            elif severity == PiiSeverity.MEDIUM and max_severity == PiiSeverity.LOW:
                max_severity = PiiSeverity.MEDIUM

    # Sort by position for masking
    matches.sort(key=lambda m: m.start)

    return PiiScanResult(
        has_pii=len(matches) > 0,
        matches=matches,
        pii_types=pii_types,
        severity=max_severity,
        masked_text="",  # Set by mask_text if needed
    )


def mask_text(text: str) -> str:
    """Return text with all detected PII replaced by masked versions."""
    result = scan_text(text)
    if not result.has_pii:
        return text

    # Apply masks in reverse order to preserve positions
    masked = text
    for m in reversed(result.matches):
        masked = masked[:m.start] + m.masked + masked[m.end:]

    return masked


def should_block_output(text: str) -> bool:
    """
    Determine if output should be blocked entirely (never sent to user).
    Blocks when CRITICAL PII is detected (bank card + name/address together)
    or when >3 HIGH severity matches found.
    """
    result = scan_text(text)

    if result.severity == PiiSeverity.CRITICAL and len(result.matches) >= 3:
        return True

    high_count = sum(1 for m in result.matches if m.severity == PiiSeverity.HIGH)
    if high_count > 5:
        return True

    return False


# ── Streaming Accumulator ──

class PiiStreamAccumulator:
    """
    Accumulates streaming text chunks and scans for PII.
    Designed for SSE output — maintains a buffer to catch patterns
    that may span chunk boundaries.
    """

    def __init__(self, buffer_size: int = 50):
        self._buffer: str = ""
        self._buffer_size = buffer_size
        self._total_pii_count = 0
        self._blocked = False

    def feed(self, chunk: str) -> str:
        """
        Feed a new text chunk. Returns the chunk (possibly masked).
        Returns empty string if output should be blocked.
        """
        if self._blocked:
            return ""

        self._buffer += chunk

        # Scan buffer for PII
        result = scan_text(self._buffer)

        if result.has_pii:
            self._total_pii_count += len(result.matches)

            # Check if we should block
            if should_block_output(self._buffer):
                self._blocked = True
                return ""

            # Mask the buffer
            self._buffer = mask_text(self._buffer)

        # Trim buffer to recent content (keep trailing chars for cross-chunk patterns)
        if len(self._buffer) > self._buffer_size:
            output = self._buffer[:-self._buffer_size]
            self._buffer = self._buffer[-self._buffer_size:]
            return output

        return ""

    def flush(self) -> str:
        """Return remaining buffer content (masked)."""
        if self._blocked:
            return "[PII 已脱敏]"
        result = scan_text(self._buffer)
        if result.has_pii:
            return mask_text(self._buffer)
        return self._buffer

    @property
    def is_blocked(self) -> bool:
        return self._blocked

    @property
    def total_pii_found(self) -> int:
        return self._total_pii_count
