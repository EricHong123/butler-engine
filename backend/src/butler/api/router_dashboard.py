"""
Dashboard API endpoints. Serve asset data, reports, and documents
to the Web portal frontend.
"""

from __future__ import annotations

import os
import shutil
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import select

from butler.api.deps import get_agent_tools
from butler.config import settings

router = APIRouter(prefix="/api", tags=["dashboard"])


async def _get_assets_from_db(tenant_id: str) -> list[dict] | None:
    """Try to load assets from DB. Returns None if DB unavailable."""
    try:
        from butler.models.document import Asset
        engine = None
        from butler.services.database import get_engine
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(
                select(Asset).where(Asset.tenant_id == tenant_id)
            )
            assets = result.scalars().all()
            if assets:
                return [
                    {
                        "account_name": a.account_name,
                        "asset_type": a.asset_type,
                        "institution": a.institution or "",
                        "currency": a.currency,
                        "value_snapshot": a.value_snapshot,
                        "value_date": str(a.value_date) if a.value_date else "",
                        "account_number_masked": a.account_number_masked or "",
                        "notes": a.notes or "",
                    }
                    for a in assets
                ]
    except Exception:
        pass
    return None


@router.get("/dashboard")
async def get_dashboard(tenant_id: str = "demo-001"):
    """Asset dashboard. Reads from DB with tool fallback."""

    # Try DB first
    accounts = await _get_assets_from_db(tenant_id)

    # Fallback to mock tool
    if not accounts:
        tools = get_agent_tools("wealth_advisor")
        asset_tool = tools.find("query_assets")
        if asset_tool:
            result = await asset_tool.call({"query": "all"}, _make_ctx(tenant_id))
            accounts = result.data.get("accounts", [])

    if not accounts:
        return {"total_value": 0, "total_value_formatted": "¥0", "error": "No data"}

    # Build derived metrics
    total = sum(a.get("value_snapshot", 0) for a in accounts)
    by_type: dict[str, float] = {}
    for a in accounts:
        t = a.get("asset_type", "other")
        by_type[t] = by_type.get(t, 0) + a.get("value_snapshot", 0)

    return {
        "total_value": total,
        "total_value_formatted": _fmt_cny(total),
        "monthly_change_pct": 1.2,
        "allocation": [
            {
                "label": _label(t),
                "asset_type": t,
                "value": v,
                "pct": round(v / total * 100, 1) if total else 0,
                "icon": _icon(t),
                "color": _color(t),
            }
            for t, v in by_type.items()
        ],
        "recent_activity": [
            {"date": "2026-05-05", "desc": "CMB活期利息入账", "amount": 15200, "currency": "CNY"},
            {"date": "2026-05-01", "desc": "HSBC股息入账", "amount": 150000, "currency": "USD"},
            {"date": "2026-04-28", "desc": "北京房产租金", "amount": 50000, "currency": "CNY"},
            {"date": "2026-04-15", "desc": "AIA保费支出", "amount": -50000, "currency": "USD"},
        ],
        "urgent_alerts": [
            {"type": "tax", "msg": "香港物业税申报 — 5月31日截止", "priority": "urgent"},
            {"type": "insurance", "msg": "友邦年缴保费 — 6月1日到期", "priority": "high"},
            {"type": "exam", "msg": "张明SAT考试 — 6月7日", "priority": "normal"},
        ],
    }


@router.get("/reports")
async def list_reports(tenant_id: str = "demo-001"):
    """List available AI-generated reports."""
    tools = get_agent_tools("butler")
    report_tool = tools.find("generate_report")
    if not report_tool:
        return {"reports": []}

    # Generate previews for all report types
    reports_data = []
    for rtype, period in [
        ("asset_monthly", "2026-04"),
        ("tax_quarterly", "2026-Q1"),
        ("health_annual", "2026"),
        ("education_progress", "2026-05"),
    ]:
        result = await report_tool.call(
            {"report_type": rtype, "period": period, "format": "markdown"},
            _make_ctx(tenant_id),
        )
        report_md = result.data.get("report_markdown", "")
        reports_data.append({
            "id": f"{rtype}-{period}",
            "title": _report_title(rtype, period),
            "type": rtype,
            "date": "2026-05-01",
            "summary": _extract_summary(report_md),
            "markdown": report_md,
        })

    return {"reports": reports_data}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, tenant_id: str = "demo-001"):
    """Get a specific report by ID."""
    parts = report_id.rsplit("-", 1)
    if len(parts) != 2:
        return {"error": "Invalid report ID"}

    rtype, period = parts[0], parts[1]
    tools = get_agent_tools("butler")
    report_tool = tools.find("generate_report")
    if not report_tool:
        return {"error": "report tool not available"}

    result = await report_tool.call(
        {"report_type": rtype, "period": period, "format": "markdown"},
        _make_ctx(tenant_id),
    )
    return {
        "id": report_id,
        "title": _report_title(rtype, period),
        "type": rtype,
        "date": "2026-05-01",
        "markdown": result.data.get("report_markdown", ""),
    }


@router.get("/documents")
async def list_documents(
    tenant_id: str = "demo-001",
    query: str = "",
    doc_type: str = "all",
):
    """List/search documents in the vault."""
    tools = get_agent_tools("butler")
    doc_tool = tools.find("search_docs")
    if not doc_tool:
        return {"documents": [], "total": 0}

    result = await doc_tool.call(
        {"query": query, "doc_type": doc_type if doc_type != "all" else None, "limit": 20},
        _make_ctx(tenant_id),
    )

    # Enrich with file metadata
    docs = []
    for m in result.data.get("matches", []):
        docs.append({
            "filename": m["filename"],
            "type": m["doc_type"],
            "date": m.get("date", ""),
            "institution": m.get("institution", ""),
            "tags": m.get("tags", ""),
            "excerpt": m.get("excerpt", "")[:200],
            "size": "245 KB",  # Placeholder
        })

    return {"documents": docs, "total": len(docs)}


# ── Helpers ──

def _make_ctx(tenant_id: str):
    from types import SimpleNamespace
    return SimpleNamespace(tenant_id=tenant_id, messages=[])


def _label(asset_type: str) -> str:
    return {
        "bank_deposit": "银行存款",
        "securities": "证券投资",
        "trust": "信托资产",
        "insurance": "保险",
        "real_estate": "不动产",
    }.get(asset_type, asset_type)


def _icon(asset_type: str) -> str:
    return {
        "bank_deposit": "piggybank",
        "securities": "trendingup",
        "trust": "landmark",
        "insurance": "shield",
        "real_estate": "building",
    }.get(asset_type, "wallet")


def _color(asset_type: str) -> str:
    return {
        "bank_deposit": "#4ade80",
        "securities": "#60a5fa",
        "trust": "#D4A83C",
        "insurance": "#a78bfa",
        "real_estate": "#fb923c",
    }.get(asset_type, "#6b7280")


def _report_title(rtype: str, period: str) -> str:
    titles = {
        "asset_monthly": f"家族资产月报 — {period}",
        "tax_quarterly": f"税务季度报告 — {period}",
        "health_annual": f"家庭健康年报 — {period}",
        "education_progress": f"子女教育进展 — {period}",
    }
    return titles.get(rtype, f"{rtype} — {period}")


def _extract_summary(md: str) -> str:
    """Extract first meaningful sentence from markdown."""
    for line in md.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) > 10 and not stripped.startswith("|"):
            return stripped[:150]
    return md[:150]


def _fmt_cny(n: float) -> str:
    if n >= 100_000_000:
        return f"¥{n/100_000_000:.2f}亿"
    if n >= 10_000:
        return f"¥{n/10_000:.0f}万"
    return f"¥{n:,.0f}"


# ── Document Upload ──

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = "demo-001",
):
    """
    Upload a PDF document. Extracts text, parses bank statements,
    and stores the document in the vault.
    """
    if not file.filename:
        return {"error": "No filename"}

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported"}

    # Save to tenant's document directory
    doc_dir = settings.data_root / tenant_id / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:12]
    saved_path = doc_dir / f"{file_id}_{file.filename}"
    content = await file.read()

    with open(saved_path, "wb") as f:
        f.write(content)

    # Parse the PDF
    from butler.documents.pdf_parser import parse_statement

    parsed = await parse_statement(saved_path, file.filename)

    # Try to save to DB
    asset_saved = False
    try:
        from butler.models.document import Document, Asset
        from butler.services.database import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            # Save document metadata
            await conn.execute(
                Document.__table__.insert().values(
                    id=f"doc-{file_id}",
                    tenant_id=tenant_id,
                    filename=file.filename,
                    doc_type="bank_statement" if parsed.institution else "other",
                    encrypted_path=str(saved_path),
                    file_size_bytes=len(content),
                    tags=f"{parsed.institution}, {parsed.currency}, statement",
                )
            )

            # If bank statement parsed, save as asset snapshot
            if parsed.institution and parsed.closing_balance:
                await conn.execute(
                    Asset.__table__.insert().values(
                        id=f"asset-{file_id}",
                        tenant_id=tenant_id,
                        account_name=f"{parsed.institution} {parsed.account_name}",
                        asset_type="bank_deposit",
                        currency=parsed.currency,
                        value_snapshot=parsed.closing_balance,
                        value_date=parsed.statement_date or "2026-01-01",
                        institution=parsed.institution,
                        account_number_masked=parsed.account_number_masked,
                        notes=f"Parsed from {file.filename}",
                    )
                )
                asset_saved = True
    except Exception:
        pass

    return {
        "status": "ok",
        "filename": file.filename,
        "file_id": file_id,
        "size_bytes": len(content),
        "parsed": {
            "institution": parsed.institution,
            "account_name": parsed.account_name,
            "currency": parsed.currency,
            "closing_balance": parsed.closing_balance,
            "statement_date": parsed.statement_date,
            "confidence": parsed.confidence,
        },
        "asset_saved": asset_saved,
    }
