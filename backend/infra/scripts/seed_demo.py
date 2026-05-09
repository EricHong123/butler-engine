#!/usr/bin/env python3
"""
Seed demo data: Zhang family tenant, assets, tax deadlines, documents.
Run: python infra/scripts/seed_demo.py
"""

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from butler.config import settings
from butler.models.document import Asset, Document, TaxDeadline
from butler.models.tenant import Customer, Tenant
from butler.services.database import close_db, get_engine, get_sessionmaker
from butler.tenants.store import TenantStore


async def seed():
    engine = get_engine()
    maker = get_sessionmaker()

    async with maker() as session:
        # ── Tenant ──
        tenant = Tenant(
            id="demo-001",
            name="Zhang Family Office",
            plan_tier="family",
            is_active=True,
            profile_path="data/demo-001/profile/CLAUDE.md",
            memory_path="data/demo-001/memory/",
        )
        session.add(tenant)

        # ── Customer ──
        customer = Customer(
            id="cust-001",
            tenant_id="demo-001",
            display_name="Zhang Wei",
            wechat_id="zhang_wei",
            phone="138****8000",
            email="zhangwei@example.com",
        )
        session.add(customer)

        # ── Assets (8 accounts) ──
        assets = [
            Asset(tenant_id="demo-001", account_name="CMB Private Banking 活期",
                  asset_type="bank_deposit", currency="CNY", value_snapshot=8_500_000,
                  value_date=date(2026, 5, 1), institution="China Merchants Bank",
                  account_number_masked="****8891", notes="日常流动资金"),
            Asset(tenant_id="demo-001", account_name="CMB Wealth 稳健型组合",
                  asset_type="securities", currency="CNY", value_snapshot=25_000_000,
                  value_date=date(2026, 4, 30), institution="CMB Wealth Management",
                  account_number_masked="****4452", notes="固收+权益混合，年化收益约5.2%"),
            Asset(tenant_id="demo-001", account_name="HSBC Premier 储蓄",
                  asset_type="bank_deposit", currency="USD", value_snapshot=1_200_000,
                  value_date=date(2026, 5, 1), institution="HSBC Hong Kong",
                  account_number_masked="****3321", notes="国际支出 + 子女留学费用"),
            Asset(tenant_id="demo-001", account_name="家族信托 #1 — 张氏教育信托",
                  asset_type="trust", currency="CNY", value_snapshot=30_000_000,
                  value_date=date(2026, 3, 31), institution="China International Trust",
                  account_number_masked="****7762", notes="子女教育专项，受益人：张明、张悦"),
            Asset(tenant_id="demo-001", account_name="家族信托 #2 — 世代传承信托",
                  asset_type="trust", currency="CNY", value_snapshot=50_000_000,
                  value_date=date(2026, 3, 31), institution="CITIC Trust",
                  account_number_masked="****9901", notes="长期传承，不动产+金融资产组合"),
            Asset(tenant_id="demo-001", account_name="友邦 终身寿险",
                  asset_type="insurance", currency="USD", value_snapshot=800_000,
                  value_date=date(2026, 4, 15), institution="AIA Hong Kong",
                  account_number_masked="****5543", notes="保单现金价值，年缴保费$50,000"),
            Asset(tenant_id="demo-001", account_name="汤臣一品 自住",
                  asset_type="real_estate", currency="CNY", value_snapshot=45_000_000,
                  value_date=date(2026, 1, 1), institution="",
                  account_number_masked="", notes="浦东新区，建筑面积430㎡"),
            Asset(tenant_id="demo-001", account_name="北京朝阳区 投资房产",
                  asset_type="real_estate", currency="CNY", value_snapshot=12_000_000,
                  value_date=date(2026, 1, 1), institution="",
                  account_number_masked="", notes="年租金收入约60万，出租中"),
        ]
        for a in assets:
            session.add(a)

        # ── Tax Deadlines ──
        deadlines = [
            TaxDeadline(tenant_id="demo-001", jurisdiction="CN",
                        tax_type="个人所得税 — 年度汇算清缴",
                        deadline_date=date(2026, 6, 30), status="pending",
                        currency="CNY", notes="综合所得年度汇算"),
            TaxDeadline(tenant_id="demo-001", jurisdiction="CN",
                        tax_type="房产税", deadline_date=date(2026, 12, 31),
                        status="pending", amount_due=85_000, currency="CNY",
                        notes="上海+北京房产"),
            TaxDeadline(tenant_id="demo-001", jurisdiction="HK",
                        tax_type="利得税 — 2025/26课税年度",
                        deadline_date=date(2026, 8, 15), status="pending",
                        currency="HKD", notes="香港公司利得税申报"),
            TaxDeadline(tenant_id="demo-001", jurisdiction="HK",
                        tax_type="物业税", deadline_date=date(2026, 5, 31),
                        status="pending", amount_due=120_000, currency="HKD",
                        notes="香港投资物业租金收入报税"),
            TaxDeadline(tenant_id="demo-001", jurisdiction="US",
                        tax_type="FBAR申报", deadline_date=date(2026, 10, 15),
                        status="pending", currency="USD",
                        notes="海外账户申报"),
            TaxDeadline(tenant_id="demo-001", jurisdiction="CN",
                        tax_type="CRS信息申报", deadline_date=date(2026, 5, 31),
                        status="pending", currency="CNY",
                        notes="共同申报准则"),
        ]
        for d in deadlines:
            session.add(d)

        # ── Documents ──
        docs = [
            Document(tenant_id="demo-001", filename="CMB_Private_2026Q1_Statement.pdf",
                     doc_type="bank_statement", encrypted_path="data/demo-001/documents/cmb_q1.pdf",
                     tags="CMB, 活期, Q1, 2026"),
            Document(tenant_id="demo-001", filename="HSBC_Premier_2026Q1_Statement.pdf",
                     doc_type="bank_statement", encrypted_path="data/demo-001/documents/hsbc_q1.pdf",
                     tags="HSBC, HK, 外币, Q1, 2026"),
            Document(tenant_id="demo-001", filename="Family_Trust_1_Education_Deed.pdf",
                     doc_type="contract", encrypted_path="data/demo-001/documents/trust_deed.pdf",
                     tags="信托, 教育, 张明, 张悦"),
            Document(tenant_id="demo-001", filename="AIA_Life_Insurance_Policy.pdf",
                     doc_type="insurance", encrypted_path="data/demo-001/documents/aia_policy.pdf",
                     tags="保险, 寿险, 友邦, 美元", is_sensitive=True),
            Document(tenant_id="demo-001", filename="Shanghai_Property_Tax_2025.pdf",
                     doc_type="tax", encrypted_path="data/demo-001/documents/prop_tax.pdf",
                     tags="房产税, 上海, 2025", expiry_date=date(2026, 12, 31)),
            Document(tenant_id="demo-001", filename="Annual_Health_Checkup_ZhangWei_2026.pdf",
                     doc_type="health", encrypted_path="data/demo-001/documents/health.pdf",
                     tags="体检, 张伟, 2026", is_sensitive=True),
            Document(tenant_id="demo-001", filename="Zhang_Ming_Andover_Acceptance.pdf",
                     doc_type="education", encrypted_path="data/demo-001/documents/andover.pdf",
                     tags="教育, 张明, 录取, 美高"),
        ]
        for d in docs:
            session.add(d)

        await session.commit()
        print(f"Seeded: 1 tenant, 1 customer, {len(assets)} assets, "
              f"{len(deadlines)} tax deadlines, {len(docs)} documents")

    # ── Write CLAUDE.md profile ──
    profile_dir = settings.data_root / "demo-001" / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "CLAUDE.md"
    profile_path.write_text(PROFILE_MARKDOWN, encoding="utf-8")
    print(f"Profile written: {profile_path}")

    await close_db()


PROFILE_MARKDOWN = """# Customer Profile: Zhang Family

## Household Members
- **Zhang Wei** (principal, age 48): Founder of WeiTech Holdings. Net worth ~500M RMB.
  Communication style: Direct, values efficiency. Prefers morning check-ins.
  WeChat ID: zhang_wei
- **Zhang Li** (spouse, age 45): Manages household finances. Oversees children's education.
- **Zhang Ming** (son, age 16): Boarding at Phillips Academy Andover. College prep year.
  SAT scheduled June 7, 2026. Target score 1550+.
- **Zhang Yue** (daughter, age 12): Harrow International School Shanghai. Piano and tennis.
  Piano ABRSM Grade 7 passed. Competition May 20.

## Financial Setup
- Primary bank: China Merchants Bank (private banking tier), account ****8891
- Secondary: HSBC Premier (Hong Kong) for international, account ****3321
- Investment accounts: CMB Wealth Management (稳健型组合, ****4452)
- Trusts: 2 family trusts managed by CITIC Trust and China International Trust
  - Trust #1: Education trust for Zhang Ming and Zhang Yue (¥30M)
  - Trust #2: Generational wealth preservation (¥50M)
- Insurance: AIA Hong Kong Universal Life (USD 5M coverage, annual premium $50,000)
- Properties: Tomson Riviera (primary, ¥45M), Beijing Chaoyang (rental, ¥12M, ~¥60万/yr)
- Accountant: Li & Partners, contact: accountant@li-partners.cn

## Tax Jurisdictions
- Mainland China: Personal income tax, property tax, CRS reporting
- Hong Kong: Profits tax, property tax
- United States: FBAR filing (HSBC HK account >$10,000)

## Preferences
- Reports: Monthly, Chinese language, visual charts preferred
- Alert threshold: Single transactions >1M RMB, monthly total >5M RMB
- Communication: WeChat preferred over email. No calls before 9am or after 9pm.
- Privacy: Never mention specific amounts to household staff via WeChat.
- Style: Concise but thorough. Present data with context (MoM change, risk flags).

## Key Dates
- May 31: HK property tax deadline + CRS reporting
- June 1: AIA annual premium due
- June 7: Zhang Ming SAT exam
- June 30: China personal income tax reconciliation
- August 15: HK profits tax filing
- October 15: US FBAR filing
- December 31: China property tax deadline
"""


if __name__ == "__main__":
    asyncio.run(seed())
