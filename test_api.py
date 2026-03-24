"""Live integration test against SEC EDGAR APIs."""
from __future__ import annotations

import asyncio

import httpx  # installed in .venv via uv


async def test() -> None:
    headers = {
        "User-Agent": "sec-edgar-mcp-test/1.0 (test@example.com)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        # ── Test 1: company_tickers.json (used by search_company) ──────────
        # Lives on www.sec.gov, NOT data.sec.gov
        print("Test 1: company_tickers.json ...")
        r = await client.get(
            "https://www.sec.gov/files/company_tickers.json", headers=headers
        )
        r.raise_for_status()
        tickers_data: dict = r.json()
        apple = next(
            (v for v in tickers_data.values() if v.get("ticker") == "AAPL"), None
        )
        tsla = next(
            (v for v in tickers_data.values() if v.get("ticker") == "TSLA"), None
        )
        if apple is None or tsla is None:
            raise RuntimeError("Could not find AAPL or TSLA in tickers index")
        print(f"  Apple: CIK={apple['cik_str']}, name={apple['title']}")
        print(f"  Tesla: CIK={tsla['cik_str']}, name={tsla['title']}")
        print(f"  Total companies in index: {len(tickers_data)}")

        # ── Test 2: submissions endpoint (used by get_recent_filings) ───────
        print("\nTest 2: Recent filings for Apple (CIK 320193) ...")
        r2 = await client.get(
            "https://data.sec.gov/submissions/CIK0000320193.json", headers=headers
        )
        r2.raise_for_status()
        d2: dict = r2.json()
        print(f"  Entity: {d2['name']}")
        recent: dict = d2["filings"]["recent"]
        forms: list = recent["form"]
        dates: list = recent["filingDate"]
        print(f"  Recent filings count: {len(forms)}")
        print("  Last 5 filings:")
        for i in range(min(5, len(forms))):
            print(f"    [{forms[i]}] {dates[i]}")

        # ── Test 3: company facts (used by get_company_facts_summary) ────────
        print("\nTest 3: XBRL facts for Apple ...")
        r3 = await client.get(
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            headers=headers,
        )
        r3.raise_for_status()
        d3: dict = r3.json()
        usgaap: dict = d3["facts"]["us-gaap"]
        revenues: dict = usgaap.get("Revenues", {})
        usd_entries: list = revenues.get("units", {}).get("USD", [])
        annual_rev: list = [e for e in usd_entries if e.get("form") == "10-K"]
        if annual_rev:
            latest_rev = sorted(annual_rev, key=lambda x: x.get("end", ""))[-1]
            val_b = latest_rev["val"] / 1e9
            print(f"  Latest annual Revenues: ${val_b:.1f}B (period: {latest_rev['end']})")
        print(f"  Total XBRL concepts available: {len(usgaap)}")

        # ── Test 4: company concept endpoint (used by get_financial_facts) ───
        print("\nTest 4: NetIncomeLoss concept for Apple ...")
        r4 = await client.get(
            "https://data.sec.gov/api/xbrl/companyconcept/"
            "CIK0000320193/us-gaap/NetIncomeLoss.json",
            headers=headers,
        )
        r4.raise_for_status()
        d4: dict = r4.json()
        usd4: list = d4["units"]["USD"]
        annual_ni: list = sorted(
            [e for e in usd4 if e.get("form") == "10-K"],
            key=lambda x: x.get("end", ""),
        )
        if annual_ni:
            latest_ni = annual_ni[-1]
            val_b_ni = latest_ni["val"] / 1e9
            print(f"  Latest Net Income: ${val_b_ni:.1f}B (period: {latest_ni['end']})")
            print(f"  Historical annual entries available: {len(annual_ni)}")

    print("\nAll API tests passed.")


asyncio.run(test())
