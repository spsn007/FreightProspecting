"""
FreightProspecting V1 — Strict Field and Time Validators
Enforces ISO-8601 time semantics, zero-placeholder discipline, and margin business logic.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Optional, Tuple


def get_utc_now_iso() -> str:
    """Return current UTC time in canonical ISO-8601 string format: YYYY-MM-DDTHH:MM:SSZ"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Disallowed placeholder text for timestamp / date fields
DISALLOWED_TIMESTAMP_PLACEHOLDERS = {
    "active", "current", "recent", "n/a", "unknown", "none", "null", "tbd", "pending"
}

# ISO-8601 regex pattern: YYYY-MM-DDTHH:MM:SS with optional fraction and timezone
ISO_8601_TIMESTAMP_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)

# Canonical Date regex pattern: YYYY-MM-DD
CANONICAL_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_timestamp(val: Optional[str], field_name: str = "timestamp") -> Optional[str]:
    """
    Validate that a timestamp string strictly complies with ISO-8601.
    Rejects dummy strings like 'Active', 'Current', 'N/A', etc.
    Returns normalized ISO-8601 string or None if val is None.
    """
    if val is None:
        return None

    if not isinstance(val, str):
        raise ValueError(f"Field '{field_name}' must be a string or None, got {type(val).__name__}")

    stripped = val.strip()
    if not stripped:
        return None

    if stripped.lower() in DISALLOWED_TIMESTAMP_PLACEHOLDERS:
        raise ValueError(
            f"Invalid timestamp placeholder '{val}' in field '{field_name}'. "
            f"Placeholders like 'Active', 'Current', 'N/A' are strictly prohibited. "
            f"Use a valid ISO-8601 string or NULL."
        )

    if not ISO_8601_TIMESTAMP_REGEX.match(stripped):
        raise ValueError(
            f"Field '{field_name}' value '{val}' is not a valid ISO-8601 timestamp string "
            f"(e.g. '2026-09-26T12:00:00Z')."
        )

    # Further verify semantic date validity (e.g. reject Feb 31)
    normalized = stripped.replace(" ", "T")
    # Strip trailing timezone for strptime parsing if needed
    clean_ts = normalized.rstrip("Z")
    if "+" in clean_ts:
        clean_ts = clean_ts.split("+")[0]
    elif clean_ts.count("-") > 2:
        # Has negative timezone offset
        parts = clean_ts.rsplit("-", 1)
        clean_ts = parts[0]

    # Parse to ensure valid calendar numbers
    try:
        if "." in clean_ts:
            datetime.strptime(clean_ts, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            datetime.strptime(clean_ts, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date/time in field '{field_name}': {val}") from exc

    return normalized


def normalize_to_utc_iso(
    val: Optional[str],
    field_name: str = "timestamp",
    default_timezone: Optional[str] = None,
) -> Optional[str]:
    """
    Validate and normalize a timestamp string into canonical UTC ISO-8601 format:
    YYYY-MM-DDTHH:MM:SSZ
    Rejects text placeholders or invalid timestamps.
    If naive (no timezone indicator), localizes using default_timezone (or UTC) before converting.
    """
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
        val_str = f"{val_str}T00:00:00Z"
    valid_iso = validate_iso_timestamp(val_str, field_name)
    if valid_iso is None:
        return None
    normalized = valid_iso.replace(" ", "T")
    if normalized.endswith("Z"):
        dt = datetime.fromisoformat(normalized[:-1] + "+00:00")
    else:
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        tz = resolve_timezone(default_timezone) if default_timezone else timezone.utc
        dt = dt.replace(tzinfo=tz)
        dt = dt.astimezone(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def convert_to_utc_iso(dt_str: Optional[str], user_timezone: Optional[str] = None) -> Optional[str]:
    """Helper to convert any date/time string with optional user_timezone to canonical UTC ISO string."""
    return normalize_to_utc_iso(dt_str, "timestamp", default_timezone=user_timezone)


def validate_date_string(val: Optional[str], field_name: str = "date") -> Optional[str]:
    """
    Validate that a date string strictly complies with YYYY-MM-DD.
    Rejects text placeholders. Returns YYYY-MM-DD string or None.
    """
    if val is None:
        return None

    if not isinstance(val, str):
        raise ValueError(f"Field '{field_name}' must be a string or None, got {type(val).__name__}")

    stripped = val.strip()
    if not stripped:
        return None

    if stripped.lower() in DISALLOWED_TIMESTAMP_PLACEHOLDERS:
        raise ValueError(
            f"Invalid date placeholder '{val}' in field '{field_name}'. "
            f"Use a valid YYYY-MM-DD date or NULL."
        )

    if not CANONICAL_DATE_REGEX.match(stripped):
        raise ValueError(f"Field '{field_name}' value '{val}' must match YYYY-MM-DD format.")

    try:
        datetime.strptime(stripped, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date in field '{field_name}': {val}") from exc

    return stripped


def calculate_gross_margin(
    shipper_target_rate: Optional[float | int],
    carrier_target_cost: Optional[float | int]
) -> Tuple[Optional[float], Optional[float]]:
    """
    Deterministic gross margin calculation.
    Gross Margin = Shipper Target Rate - Carrier Target Cost
    Margin % = (Gross Margin / Shipper Target Rate) * 100

    Rule: If either input is missing/None, Margin = UNKNOWN (None, None).
    Missing margin never becomes zero.
    """
    if shipper_target_rate is None or carrier_target_cost is None:
        return None, None

    try:
        s_rate = float(shipper_target_rate)
        c_cost = float(carrier_target_cost)
    except (ValueError, TypeError):
        return None, None

    if s_rate <= 0:
        return round(s_rate - c_cost, 2), None

    margin_dollars = round(s_rate - c_cost, 2)
    margin_percentage = round((margin_dollars / s_rate) * 100.0, 2)
    return margin_dollars, margin_percentage


def validate_and_calculate_load_margin(
    shipper_target_rate: Optional[float | int | Decimal | str],
    carrier_target_cost: Optional[float | int | Decimal | str]
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Validate rates and compute deterministic gross margin using Decimal arithmetic.
    Rules:
    - Rates must be non-negative (>= 0). Rejects negative numbers with ValueError.
    - If either rate is None/missing: Gross Margin and Margin % are UNKNOWN (None, None).
    - Gross Margin = Shipper Target Rate - Carrier Target Cost
    - If Shipper Target Rate == 0: Margin % is undefined (None).
    - If Shipper Target Rate > 0: Margin % = (Gross Margin / Shipper Target Rate) * 100
    - Missing data never defaults to 0.
    """
    s_dec = None
    if shipper_target_rate is not None:
        try:
            s_dec = Decimal(str(shipper_target_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception as exc:
            raise ValueError(f"Invalid monetary rate value for shipper: {shipper_target_rate}") from exc
        if s_dec < Decimal("0.00"):
            raise ValueError(f"Shipper target rate cannot be negative: {s_dec}")

    c_dec = None
    if carrier_target_cost is not None:
        try:
            c_dec = Decimal(str(carrier_target_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception as exc:
            raise ValueError(f"Invalid monetary rate value for carrier: {carrier_target_cost}") from exc
        if c_dec < Decimal("0.00"):
            raise ValueError(f"Carrier target cost cannot be negative: {c_dec}")

    if s_dec is None or c_dec is None:
        return None, None

    gross_margin = (s_dec - c_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if s_dec == Decimal("0.00"):
        return gross_margin, None

    margin_pct = ((gross_margin / s_dec) * Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return gross_margin, margin_pct


def sanitize_url(url: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize external URLs for clickable links.
    Only permits 'http://' and 'https://' schemes.
    Rejects 'javascript:', 'data:', 'file:', and control characters.
    Returns cleaned URL or None.
    """
    if not url or not isinstance(url, str):
        return None
    clean = url.strip()
    if not clean:
        return None
    lower = clean.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        if any(c in clean for c in ("\r", "\n", "\t", " ")):
            return None
        return clean
    return None


def normalize_phone_digits(raw: Optional[str]) -> str:
    """
    Normalizes a phone number string to canonical 10-digit national number.
    Strips non-digit characters and leading US/CA country code '1' for 11-digit numbers.
    Enables symmetric, robust phone comparison between contact numbers and claim notes.
    """
    if not raw or not isinstance(raw, str):
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def is_valid_phone_number(phone: Optional[str]) -> bool:
    """
    Validate that a phone number string represents a callable telephone route.
    Rejects dummy placeholders like 'x', 'unknown', 'none', 'test' or strings with < 10 digits.
    """
    if not phone or not isinstance(phone, str):
        return False
    stripped = phone.strip()
    if not stripped or stripped.lower() in DISALLOWED_TIMESTAMP_PLACEHOLDERS:
        return False
    digits = re.sub(r"\D", "", stripped)
    if len(digits) == 10:
        return digits[0] in "23456789"
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1] in "23456789"
    return len(digits) >= 10 and len(digits) <= 15


def is_valid_email(email: Optional[str]) -> bool:
    """
    Validate that an email string represents a usable email address.
    """
    if not email or not isinstance(email, str):
        return False
    stripped = email.strip()
    if not stripped or stripped.lower() in DISALLOWED_TIMESTAMP_PLACEHOLDERS:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", stripped))


def resolve_timezone(tz_name_or_offset: Optional[str] = None):
    """
    Resolve an IANA timezone name (e.g. 'Asia/Kolkata', 'America/New_York')
    or offset (e.g. '+05:30') into a tzinfo object.
    Defaults to the system local timezone if None or empty.
    """
    if not tz_name_or_offset or str(tz_name_or_offset).strip() == "":
        try:
            return datetime.now().astimezone().tzinfo or timezone.utc
        except Exception:
            return timezone.utc

    tz_str = str(tz_name_or_offset).strip()
    if tz_str.upper() in ("UTC", "Z"):
        return timezone.utc

    # 1. Try ZoneInfo (standard IANA names)
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_str)
    except Exception:
        pass

    # 2. Try offset format (+05:30, -04:00, etc.)
    m = re.match(r"^([+-])(\d{1,2}):?(\d{2})?$", tz_str)
    if m:
        sign, hours, mins = m.groups()
        total_minutes = int(hours) * 60 + (int(mins) if mins else 0)
        if sign == "-":
            total_minutes = -total_minutes
        from datetime import timedelta
        return timezone(timedelta(minutes=total_minutes))

    # 3. Known fallback aliases
    from datetime import timedelta
    KNOWN_ALIASES = {
        "IST": timezone(timedelta(hours=5, minutes=30)),
        "EDT": timezone(timedelta(hours=-4)),
        "EST": timezone(timedelta(hours=-5)),
        "CDT": timezone(timedelta(hours=-5)),
        "CST": timezone(timedelta(hours=-6)),
        "MDT": timezone(timedelta(hours=-6)),
        "MST": timezone(timedelta(hours=-7)),
        "PDT": timezone(timedelta(hours=-7)),
        "PST": timezone(timedelta(hours=-8)),
    }
    if tz_str.upper() in KNOWN_ALIASES:
        return KNOWN_ALIASES[tz_str.upper()]

    try:
        return datetime.now().astimezone().tzinfo or timezone.utc
    except Exception:
        return timezone.utc


