"""Tool: Search the family document vault (contracts, policies, statements)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class DocSearchInput(BaseModel):
    """Input for searching documents."""
    query: str = Field(description="What to search for: keywords, document type, institution name, or date range")
    doc_type: str | None = Field(default=None, description="Filter by document type: bank_statement, insurance, contract, tax, health, education, other")
    limit: int = Field(default=5, ge=1, le=20, description="Max results to return")


class SearchDocsTool(BaseTool):
    """
    Search the family's encrypted document vault.

    Searches by filename, document type, tags, and content excerpts.
    Returns metadata and relevant excerpts without exposing raw document content.
    """

    name = "search_docs"
    aliases = ["查文件", "搜文档", "文档搜索"]
    search_hint = "document vault search file contract policy statement"

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    async def call(self, args: dict, context: Any) -> ToolResult:
        tenant_id = self._require_tenant(context)
        query = args.get("query", "").lower()
        doc_type = args.get("doc_type")
        limit = args.get("limit", 5)

        all_docs = _get_mock_documents(tenant_id)

        # Score and filter
        scored = []
        for doc in all_docs:
            score = 0
            if query:
                if query in doc["filename"].lower():
                    score += 5
                if query in doc.get("tags", "").lower():
                    score += 3
                if query in doc.get("institution", "").lower():
                    score += 3
                if query in doc.get("doc_type", ""):
                    score += 1
            if doc_type:
                if doc["doc_type"] != doc_type:
                    continue

            if score > 0 or not query:  # No query = return all matching type
                scored.append((doc, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = [s[0] for s in scored[:limit]]

        return ToolResult(data={
            "matches": [
                {
                    "filename": d["filename"],
                    "doc_type": d["doc_type"],
                    "date": d.get("date", ""),
                    "institution": d.get("institution", ""),
                    "tags": d.get("tags", ""),
                    "excerpt": d.get("excerpt", ""),
                    "expiry_date": d.get("expiry_date"),
                }
                for d in results
            ],
            "total_found": len(scored),
            "returned": len(results),
        })

    async def description(self, input: dict, options: dict) -> str:
        return f"Search documents for: {input.get('query', 'all')}"

    def input_schema(self) -> type[BaseModel]:
        return DocSearchInput


def _get_mock_documents(tenant_id: str = "demo-001") -> list[dict[str, Any]]:
    """Mock document vault for MVP. Tenant-filtered."""
    _vaults: dict[str, list[dict[str, Any]]] = {
        "demo-001": [
        {
            "filename": "CMB_Private_2026Q1_Statement.pdf",
            "doc_type": "bank_statement",
            "institution": "China Merchants Bank",
            "date": "2026-04-05",
            "tags": "CMB, 活期, Q1, 2026",
            "excerpt": "期初余额¥7,800,000，期末余额¥8,500,000，季度净流入¥700,000",
            "expiry_date": None,
        },
        {
            "filename": "HSBC_Premier_2026Q1_Statement.pdf",
            "doc_type": "bank_statement",
            "institution": "HSBC Hong Kong",
            "date": "2026-04-10",
            "tags": "HSBC, HK, 外币, Q1, 2026",
            "excerpt": "Ending balance USD 1,200,000. Net inflow USD 150,000 (dividend income)",
            "expiry_date": None,
        },
        {
            "filename": "Family_Trust_1_Education_Deed.pdf",
            "doc_type": "contract",
            "institution": "China International Trust",
            "date": "2020-03-15",
            "tags": "信托, 教育, 洪明, 洪悦",
            "excerpt": "Settlor: Hong Wei. Beneficiaries: Hong Ming, Hong Yue. Purpose: education expenses including tuition, living, and extracurricular.",
            "expiry_date": None,
        },
        {
            "filename": "AIA_Life_Insurance_Policy.pdf",
            "doc_type": "insurance",
            "institution": "AIA Hong Kong",
            "date": "2018-06-01",
            "tags": "保险, 寿险, 友邦, 美元",
            "excerpt": "Policy type: Universal Life. Insured: Hong Wei. Sum assured: USD 5,000,000. Annual premium: USD 50,000.",
            "expiry_date": None,
        },
        {
            "filename": "Shanghai_Property_Tax_2025.pdf",
            "doc_type": "tax",
            "institution": "Shanghai Tax Bureau",
            "date": "2025-12-15",
            "tags": "房产税, 上海, 2025",
            "excerpt": "Property tax assessment for Tomson Riviera. Taxable value ¥45,000,000. Tax due: ¥85,000.",
            "expiry_date": "2026-12-31",
        },
        {
            "filename": "Annual_Health_Checkup_ZhangWei_2026.pdf",
            "doc_type": "health",
            "institution": "Shanghai United Family Hospital",
            "date": "2026-02-20",
            "tags": "体检, 洪伟, 2026",
            "excerpt": "Overall: Good. LDL cholesterol slightly elevated (3.8mmol/L). Recommendation: dietary adjustment and recheck in 6 months.",
            "expiry_date": None,
        },
        {
            "filename": "Zhang_Ming_Andover_Acceptance.pdf",
            "doc_type": "education",
            "institution": "Phillips Academy Andover",
            "date": "2025-03-10",
            "tags": "教育, 洪明, 录取, 美高",
            "excerpt": "Admission offer for Grade 11, academic year 2025-2026. Annual tuition: USD 65,000.",
            "expiry_date": None,
        },
    ],
    }
    return _vaults.get(tenant_id, _vaults["demo-001"])
