"""
PDF bank statement parser. Extracts text from PDF and uses AI to
structure it into account data suitable for the asset dashboard.

Flow: PDF file → pdfplumber extract text → AI parse → structured Asset dict
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber


@dataclass
class ParsedStatement:
    """Structured output from parsing a bank statement."""
    institution: str = ""
    account_name: str = ""
    account_number_masked: str = ""
    currency: str = "CNY"
    statement_date: str = ""
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    net_flow: float = 0.0
    transactions: list[dict] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0


def extract_text_from_pdf(file_path: Path | str) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    text_parts: list[str] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n---PAGE BREAK---\n".join(text_parts)


def parse_with_rules(text: str, filename: str = "") -> ParsedStatement:
    """
    Rule-based parser for common Chinese bank statement formats.
    Extracts balances, institution name, and currency from raw text.

    This is the fast path — no AI call needed for well-formatted statements.
    """
    result = ParsedStatement(raw_text=text[:2000])

    # Detect institution
    institutions = {
        "招商银行": ("China Merchants Bank", "CMB"),
        "工商银行": ("ICBC", "ICBC"),
        "建设银行": ("CCB", "CCB"),
        "中国银行": ("Bank of China", "BOC"),
        "农业银行": ("ABC", "ABC"),
        "交通银行": ("Bank of Communications", "BoCom"),
        "汇丰": ("HSBC", "HSBC"),
        "HSBC": ("HSBC", "HSBC"),
        "花旗": ("Citibank", "Citi"),
        "渣打": ("Standard Chartered", "SCB"),
        "友邦": ("AIA", "AIA"),
        "AIA": ("AIA", "AIA"),
        "中信": ("CITIC", "CITIC"),
        "平安": ("Ping An", "PingAn"),
    }

    for keyword, (full_name, short) in institutions.items():
        if keyword.lower() in text.lower():
            result.institution = full_name
            result.account_name = f"{short} 账户"
            break

    # Detect file type from filename
    if "CMB" in filename or "招商" in filename:
        result.institution = "China Merchants Bank"
        result.account_name = "CMB Private Banking"
    elif "HSBC" in filename:
        result.institution = "HSBC"
        result.account_name = "HSBC Premier"
        result.currency = "USD" if "USD" in text or "美元" in text else "HKD"

    # Extract balances with regex
    # Pattern: "余额" or "Balance" followed by numbers
    balance_patterns = [
        (r"(?:期末余额|结余|Balance)[^\d]*[¥$]?\s*([\d,]+\.?\d*)", "closing"),
        (r"(?:期初余额|上期余额|Opening)[^\d]*[¥$]?\s*([\d,]+\.?\d*)", "opening"),
    ]

    for pattern, balance_type in balance_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                value = float(matches[-1].replace(",", ""))
                if balance_type == "closing":
                    result.closing_balance = value
                else:
                    result.opening_balance = value
            except ValueError:
                pass

    # Detect currency
    if "USD" in text or "美元" in text or "$" in text:
        result.currency = "USD"
    elif "HKD" in text or "港币" in text or "HK$" in text:
        result.currency = "HKD"
    elif "¥" in text or "CNY" in text or "人民币" in text:
        result.currency = "CNY"

    # Calculate net flow
    if result.opening_balance and result.closing_balance:
        result.net_flow = result.closing_balance - result.opening_balance

    # Account number
    acct_match = re.search(r"(?:账号|Account\s*No)[:\s]*[*\d]+([*\d]{4})", text)
    if acct_match:
        result.account_number_masked = f"****{acct_match.group(1)}"

    # Extract date
    date_match = re.search(r"(?:日期|Date|对账单周期)[:\s]*(\d{4}[-/]\d{2}[-/]\d{2})", text)
    if date_match:
        result.statement_date = date_match.group(1).replace("/", "-")

    # Confidence based on how much we found
    score = 0
    if result.institution:
        score += 3
    if result.closing_balance:
        score += 4
    if result.opening_balance:
        score += 2
    if result.statement_date:
        score += 1
    result.confidence = min(score / 10.0, 1.0)

    return result


async def parse_with_ai(
    text: str,
    filename: str = "",
    model: str = "",
) -> ParsedStatement:
    """
    AI-powered parser for complex or non-standard bank statements.
    Uses the configured LLM to extract structured data from raw text.

    Falls back to rule-based parser if LLM is unavailable.
    """
    # Try rule-based first — faster and cheaper
    rule_result = parse_with_rules(text, filename)
    if rule_result.confidence >= 0.7:
        return rule_result

    # If rules failed, try AI
    try:
        from butler.services.llm.client import get_llm_client
        from butler.services.llm.router import route_model

        client = get_llm_client()
        if client._mock_mode:
            return rule_result

        model_name, provider = route_model([{"role": "user", "content": text[:500]}])

        prompt = f"""Extract structured data from this bank statement text.
Return ONLY valid JSON, no other text.

{{
  "institution": "Bank name",
  "account_name": "Account name/type",
  "currency": "CNY/USD/HKD",
  "statement_date": "YYYY-MM-DD",
  "opening_balance": 0.0,
  "closing_balance": 0.0,
  "account_number_masked": "****1234 or empty"
}}

Text:
{text[:3000]}
"""
        full_text = ""
        async for event in client.stream(
            provider=provider,
            model=model_name or "deepseek-chat",
            system="You are a financial data extraction system. Output only JSON.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        ):
            if event.get("type") == "text_delta":
                full_text += event.get("text", "")

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", full_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return ParsedStatement(
                institution=data.get("institution", rule_result.institution),
                account_name=data.get("account_name", rule_result.account_name),
                account_number_masked=data.get("account_number_masked", ""),
                currency=data.get("currency", rule_result.currency),
                statement_date=data.get("statement_date", ""),
                opening_balance=float(data.get("opening_balance", 0)),
                closing_balance=float(data.get("closing_balance", 0)),
                raw_text=text[:2000],
                confidence=0.85,
            )
    except Exception:
        pass

    return rule_result


async def parse_statement(
    file_path: Path | str,
    filename: str = "",
) -> ParsedStatement:
    """Full pipeline: extract text → parse (rules or AI)."""
    text = extract_text_from_pdf(str(file_path))
    if not text.strip():
        return ParsedStatement(raw_text="", confidence=0.0)
    return await parse_with_ai(text, filename)
