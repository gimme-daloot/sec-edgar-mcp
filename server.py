"""
SEC EDGAR Financial Intelligence MCP Server
============================================
Gives AI agents real-time access to SEC filings, company financials,
insider transactions, and regulatory disclosures.

Monetization: API key required for >10 calls/day (freemium)
Target: Financial analysts, investors, journalists, researchers
"""

import asyncio
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# ── Logging (stderr only — never stdout in stdio mode) ──────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sec-edgar-mcp")

# ── Server init ──────────────────────────────────────────────────────────────
mcp = FastMCP(
    "sec-edgar-intelligence",
    instructions=(
        "Access SEC EDGAR filings, company financials, insider transactions, "
        "and regulatory disclosures. All data is sourced directly from the "
        "official SEC EDGAR database in real time."
    ),
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

# ── Config ───────────────────────────────────────────────────────────────────
EDGAR_BASE = "https://data.sec.gov"
EDGAR_WWW = "https://www.sec.gov"
EFTS_BASE = "https://efts.sec.gov"

# Required by SEC: identify your application + contact email
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "your-email@example.com")
USER_AGENT = f"sec-edgar-mcp/1.0 ({CONTACT_EMAIL})"

# Rate limiting: SEC allows 10 req/s. We stay under at 8/s with burst of 40.
_rate_limiter_tokens: float = 40.0
_rate_limiter_last: float = time.monotonic()
_rate_limiter_lock = asyncio.Lock()

# Simple in-memory usage tracking for freemium gate.
# Typed as defaultdict so subscript assignment works correctly.
_usage_counts: defaultdict[str, int] = defaultdict(int)
_usage_reset_date: dict[str, str] = {}
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "10"))
API_KEY = os.getenv("EDGAR_MCP_API_KEY", "")  # empty = free tier only

_UPGRADE_MSG = (
    "Daily free limit reached (10 calls/day). "
    "Get an API key at https://mcpize.com/sec-edgar-mcp for unlimited access ($19/month)."
)

# ── Helpers ──────────────────────────────────────────────────────────────────


async def _rate_limit() -> None:
    """Token-bucket rate limiter: max 8 tokens/sec, burst 40."""
    global _rate_limiter_tokens, _rate_limiter_last
    async with _rate_limiter_lock:
        now = time.monotonic()
        elapsed = now - _rate_limiter_last
        _rate_limiter_tokens = min(40.0, _rate_limiter_tokens + elapsed * 8.0)
        _rate_limiter_last = now
        if _rate_limiter_tokens < 1.0:
            wait = (1.0 - _rate_limiter_tokens) / 8.0
            await asyncio.sleep(wait)
            _rate_limiter_tokens = 0.0
        else:
            _rate_limiter_tokens -= 1.0


async def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to SEC EDGAR."""
    await _rate_limit()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


def _pad_cik(cik: str | int) -> str:
    """Zero-pad CIK to 10 digits as required by SEC API."""
    return str(int(cik)).zfill(10)


def _check_usage(client_id: str) -> bool:
    """
    Freemium gate: returns True if request is allowed.
    - With valid API key: unlimited
    - Without key: FREE_DAILY_LIMIT calls/day per client_id
    """
    if API_KEY and client_id == API_KEY:
        return True
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if _usage_reset_date.get(client_id) != today:
        _usage_counts[client_id] = 0
        _usage_reset_date[client_id] = today
    if _usage_counts[client_id] >= FREE_DAILY_LIMIT:
        return False
    _usage_counts[client_id] += 1
    return True


async def _search_company_cik(name_or_ticker: str) -> list[dict[str, str]]:
    """Search for a company by ticker or name. Returns up to 10 CIK matches."""
    # company_tickers.json lives on www.sec.gov, not data.sec.gov
    tickers_url = f"{EDGAR_WWW}/files/company_tickers.json"
    data = await _get(tickers_url)
    results: list[dict[str, str]] = []
    query_upper = name_or_ticker.upper()
    for entry in data.values():
        ticker: str = entry.get("ticker", "").upper()
        title: str = entry.get("title", "").upper()
        if query_upper == ticker or query_upper in title:
            results.append({
                "cik": str(entry["cik_str"]),
                "cik_padded": _pad_cik(entry["cik_str"]),
                "ticker": entry.get("ticker", ""),
                "name": entry.get("title", ""),
            })
        if len(results) >= 10:
            break
    return results


def _fmt_usd(val: float) -> str:
    """Format a USD value as human-readable string."""
    if abs(val) >= 1e9:
        return f"${val / 1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:.1f}M"
    return f"${val:,.0f}"


def _fmt_shares(val: float) -> str:
    """Format a share count as human-readable string."""
    if val >= 1e9:
        return f"{val / 1e9:.2f}B shares"
    if val >= 1e6:
        return f"{val / 1e6:.1f}M shares"
    return f"{val:,.0f} shares"


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_company(
    query: str,
    api_key: str = "",
) -> str:
    """
    Search for a public company by name or ticker symbol.
    Returns CIK number, ticker, and company name.
    Use the CIK returned here in all other tools.

    Args:
        query: Company name or ticker symbol (e.g. "AAPL", "Apple", "Tesla")
        api_key: Your API key for unlimited access (optional, free tier: 10 calls/day)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    try:
        results = await _search_company_cik(query)
        if not results:
            return f"No companies found matching '{query}'. Try a different name or ticker."
        lines = [f"Found {len(results)} match(es) for '{query}':\n"]
        for r in results:
            lines.append(
                f"  CIK: {r['cik']}  |  Ticker: {r['ticker']}  |  Name: {r['name']}"
            )
        lines.append("\nUse the CIK number in other tools to fetch filings and financials.")
        return "\n".join(lines)
    except Exception as e:
        logger.error("search_company error: %s", e)
        return f"Error searching for company: {e}"


@mcp.tool()
async def get_recent_filings(
    cik: str,
    form_type: str = "",
    limit: int = 10,
    api_key: str = "",
) -> str:
    """
    Get the most recent SEC filings for a company.
    Returns filing dates, form types, descriptions, and document URLs.

    Args:
        cik: Company CIK number (from search_company tool, e.g. "320193" for Apple)
        form_type: Filter by form type: "10-K" (annual), "10-Q" (quarterly),
                   "8-K" (material events), "4" (insider trades), "S-1" (IPO),
                   "DEF 14A" (proxy/votes), "13F" (hedge fund holdings).
                   Leave empty for all recent filings.
        limit: Number of filings to return (1-40, default 10)
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    limit = max(1, min(40, limit))
    try:
        cik_padded = _pad_cik(cik)
        data = await _get(f"{EDGAR_BASE}/submissions/CIK{cik_padded}.json")

        company_name: str = data.get("name", "Unknown")
        recent: dict[str, Any] = data.get("filings", {}).get("recent", {})
        if not recent:
            return f"No filings found for CIK {cik}."

        forms: list[Any] = recent.get("form", [])
        dates: list[Any] = recent.get("filingDate", [])
        accessions: list[Any] = recent.get("accessionNumber", [])
        descriptions: list[Any] = recent.get("primaryDocument", [])
        doc_descriptions: list[Any] = recent.get("primaryDocDescription", [])

        filing_results: list[dict[str, str]] = []
        for i in range(len(forms)):
            if form_type and str(forms[i]).upper() != form_type.upper():
                continue
            acc: str = str(accessions[i]).replace("-", "")
            primary_doc: str = str(descriptions[i]) if i < len(descriptions) else ""
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{primary_doc}"
            )
            filing_results.append({
                "form": str(forms[i]),
                "date": str(dates[i]) if i < len(dates) else "",
                "description": str(doc_descriptions[i]) if i < len(doc_descriptions) else "",
                "url": filing_url,
                "accession": str(accessions[i]),
            })
            if len(filing_results) >= limit:
                break

        if not filing_results:
            filter_msg = f" of type '{form_type}'" if form_type else ""
            return f"No filings{filter_msg} found for {company_name} (CIK {cik})."

        lines = [f"Recent filings for {company_name} (CIK {cik}):\n"]
        for r in filing_results:
            lines.append(
                f"  [{r['form']}] {r['date']}  —  {r['description']}\n"
                f"    URL: {r['url']}\n"
                f"    Accession: {r['accession']}"
            )
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Company with CIK {cik} not found. Use search_company to find the correct CIK."
        return f"HTTP error fetching filings: {e}"
    except Exception as e:
        logger.error("get_recent_filings error: %s", e)
        return f"Error fetching filings: {e}"


@mcp.tool()
async def get_financial_facts(
    cik: str,
    metric: str = "Revenues",
    api_key: str = "",
) -> str:
    """
    Get standardized financial data (XBRL) for a company over time.
    Returns historical values for a specific financial metric across all filings.

    Common metric names:
    - Revenue: "Revenues" or "RevenueFromContractWithCustomerExcludingAssessedTax"
    - Net Income: "NetIncomeLoss"
    - EPS: "EarningsPerShareBasic"
    - Assets: "Assets"
    - Liabilities: "Liabilities"
    - Cash: "CashAndCashEquivalentsAtCarryingValue"
    - Operating Income: "OperatingIncomeLoss"
    - Gross Profit: "GrossProfit"
    - R&D: "ResearchAndDevelopmentExpense"
    - Shares Outstanding: "CommonStockSharesOutstanding"
    - Long-term Debt: "LongTermDebt"
    - Free Cash Flow: "NetCashProvidedByUsedInOperatingActivities"

    Args:
        cik: Company CIK number
        metric: XBRL financial concept name (see list above)
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    try:
        cik_padded = _pad_cik(cik)
        data: dict[str, Any] | None = None
        # Try us-gaap taxonomy first, then dei
        for taxonomy in ["us-gaap", "dei"]:
            try:
                url = (
                    f"{EDGAR_BASE}/api/xbrl/companyconcept/"
                    f"CIK{cik_padded}/{taxonomy}/{metric}.json"
                )
                data = await _get(url)
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and taxonomy == "us-gaap":
                    continue
                raise

        if data is None:
            return (
                f"Metric '{metric}' not found for CIK {cik}. "
                "Try a different concept name or check the XBRL taxonomy."
            )

        company_name: str = data.get("entityName", "Unknown")
        units_data: dict[str, Any] = data.get("units", {})

        # Find the best unit (USD, shares, etc.)
        unit_key: str | None = None
        for uk in ["USD", "USD/shares", "shares", "pure"]:
            if uk in units_data:
                unit_key = uk
                break
        if unit_key is None and units_data:
            unit_key = next(iter(units_data))

        if unit_key is None:
            return f"No data units found for {metric}."

        entries: list[Any] = units_data[unit_key]
        # Filter to annual filings (10-K) for cleaner output
        annual: list[Any] = [e for e in entries if e.get("form") in ("10-K", "20-F")]
        quarterly: list[Any] = [e for e in entries if e.get("form") == "10-Q"]

        lines = [
            f"Financial metric '{metric}' for {company_name} (CIK {cik}):",
            f"Unit: {unit_key}",
            "",
        ]

        if annual:
            lines.append("Annual (10-K) filings:")
            for e in sorted(annual, key=lambda x: x.get("end", ""))[-10:]:
                val = e.get("val")
                if val is not None:
                    formatted = _fmt_usd(float(val)) if unit_key == "USD" else f"{val:,.0f} {unit_key}"
                    lines.append(
                        f"  {e.get('end', 'N/A')}  "
                        f"(FY {e.get('fy', 'N/A')} {e.get('fp', '')}):  {formatted}"
                    )
        elif quarterly:
            lines.append("Quarterly (10-Q) filings:")
            for e in sorted(quarterly, key=lambda x: x.get("end", ""))[-8:]:
                val = e.get("val")
                if val is not None:
                    formatted = _fmt_usd(float(val)) if unit_key == "USD" else f"{val:,.0f} {unit_key}"
                    lines.append(
                        f"  {e.get('end', 'N/A')}  "
                        f"({e.get('fy', 'N/A')} {e.get('fp', '')}):  {formatted}"
                    )

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return (
                f"Metric '{metric}' not found for CIK {cik} in us-gaap or dei taxonomy. "
                "Common alternatives: Revenues, NetIncomeLoss, Assets, Liabilities, "
                "CashAndCashEquivalentsAtCarryingValue"
            )
        return f"HTTP error: {e}"
    except Exception as e:
        logger.error("get_financial_facts error: %s", e)
        return f"Error fetching financial facts: {e}"


@mcp.tool()
async def get_insider_transactions(
    cik: str,
    limit: int = 20,
    api_key: str = "",
) -> str:
    """
    Get recent insider trading transactions (Form 4 filings) for a company.
    Shows purchases, sales, and awards by executives, directors, and 10%+ owners.
    This is SEC-reported data — all transactions are public record.

    Args:
        cik: Company CIK number
        limit: Number of Form 4 filings to return (1-40, default 20)
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    limit = max(1, min(40, limit))
    try:
        cik_padded = _pad_cik(cik)
        data = await _get(f"{EDGAR_BASE}/submissions/CIK{cik_padded}.json")
        company_name: str = data.get("name", "Unknown")

        recent: dict[str, Any] = data.get("filings", {}).get("recent", {})
        forms: list[Any] = recent.get("form", [])
        dates: list[Any] = recent.get("filingDate", [])
        accessions: list[Any] = recent.get("accessionNumber", [])

        form4_entries: list[dict[str, str]] = []
        browse_url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            f"&CIK={cik}&type=4&dateb=&owner=include&count=40"
        )
        for i in range(len(forms)):
            if str(forms[i]) in ("4", "4/A"):
                form4_entries.append({
                    "form": str(forms[i]),
                    "date": str(dates[i]) if i < len(dates) else "",
                    "accession": str(accessions[i]),
                })
                if len(form4_entries) >= limit:
                    break

        if not form4_entries:
            return (
                f"No Form 4 (insider transaction) filings found for "
                f"{company_name} (CIK {cik}) in recent filings."
            )

        lines = [
            f"Recent insider transactions (Form 4) for {company_name} (CIK {cik}):",
            f"(Showing {len(form4_entries)} filings — click URLs for transaction details)\n",
        ]
        for e in form4_entries:
            lines.append(
                f"  [{e['form']}] Filed: {e['date']}  |  Accession: {e['accession']}"
            )
        lines.append(f"\nView all Form 4s: {browse_url}")
        lines.append(
            "\nTip: Use get_filing_document to retrieve the XML of a specific Form 4 "
            "for full transaction details (shares bought/sold, price, insider title)."
        )
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Company with CIK {cik} not found."
        return f"HTTP error: {e}"
    except Exception as e:
        logger.error("get_insider_transactions error: %s", e)
        return f"Error fetching insider transactions: {e}"


@mcp.tool()
async def get_full_text_search(
    query: str,
    form_type: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 10,
    api_key: str = "",
) -> str:
    """
    Full-text search across all SEC EDGAR filings.
    Search for any term, phrase, or topic across millions of filings.
    Useful for finding mentions of a competitor, technology, risk factor,
    lawsuit, or any other disclosure language.

    Args:
        query: Search term or phrase (use quotes for exact phrase, e.g. '"climate risk"')
        form_type: Filter by form type (e.g. "10-K", "8-K", "10-Q", "S-1", "4")
        date_from: Start date in YYYY-MM-DD format (e.g. "2024-01-01")
        date_to: End date in YYYY-MM-DD format (e.g. "2025-03-17")
        limit: Number of results (1-20, default 10)
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    limit = max(1, min(20, limit))
    try:
        params: dict[str, Any] = {"q": query}
        if form_type:
            params["forms"] = form_type
        if date_from or date_to:
            params["dateRange"] = "custom"
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to

        url = f"{EFTS_BASE}/LATEST/search-index"
        data = await _get(url, params=params)

        hits_wrapper: dict[str, Any] = data.get("hits", {})
        hits: list[Any] = hits_wrapper.get("hits", [])
        total_obj: Any = hits_wrapper.get("total", {})
        total: int = total_obj.get("value", 0) if isinstance(total_obj, dict) else int(total_obj)

        if not hits:
            return f"No filings found matching '{query}'."

        lines = [
            f"Full-text search results for '{query}':",
            f"Total matches: {total} (showing {min(len(hits), limit)})\n",
        ]
        for h in hits[:limit]:
            source: dict[str, Any] = h.get("_source", {})
            entity: str = source.get("entity_name", "Unknown")
            file_date: str = source.get("file_date", "")
            form: str = source.get("form_type", "")
            period: str = source.get("period_of_report", "")
            acc: str = str(h.get("_id", "")).replace("-", "")
            ciks_list: list[Any] = source.get("ciks", [])
            first_cik: str = str(ciks_list[0]) if ciks_list else ""
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{first_cik}/{acc}/"
                if first_cik and acc
                else "N/A"
            )
            lines.append(
                f"  [{form}] {entity}  |  Filed: {file_date}  |  Period: {period}\n"
                f"    URL: {filing_url}"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.error("get_full_text_search error: %s", e)
        return f"Error performing full-text search: {e}"


@mcp.tool()
async def get_company_facts_summary(
    cik: str,
    api_key: str = "",
) -> str:
    """
    Get a comprehensive financial summary for a company using all available
    XBRL facts from their most recent annual filing (10-K or 20-F).
    Returns revenue, net income, assets, liabilities, cash, and more
    in a single call.

    Args:
        cik: Company CIK number
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    # Key metrics: label -> ordered list of XBRL concept names to try
    KEY_METRICS: dict[str, list[str]] = {
        "Revenue": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ],
        "Net Income": ["NetIncomeLoss"],
        "Gross Profit": ["GrossProfit"],
        "Operating Income": ["OperatingIncomeLoss"],
        "R&D Expense": ["ResearchAndDevelopmentExpense"],
        "Total Assets": ["Assets"],
        "Total Liabilities": ["Liabilities"],
        "Stockholders Equity": ["StockholdersEquity"],
        "Cash & Equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
        "Long-term Debt": ["LongTermDebt"],
        "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities"],
        "CapEx": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "EPS (Basic)": ["EarningsPerShareBasic"],
        "Shares Outstanding": ["CommonStockSharesOutstanding"],
    }

    try:
        cik_padded = _pad_cik(cik)
        data = await _get(f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json")
        company_name: str = data.get("entityName", "Unknown")
        us_gaap: dict[str, Any] = data.get("facts", {}).get("us-gaap", {})

        # label -> (formatted_value, period_end_date, unit_key)
        results: dict[str, tuple[str, str, str]] = {}

        for label, concepts in KEY_METRICS.items():
            for concept in concepts:
                if concept not in us_gaap:
                    continue
                units: dict[str, Any] = us_gaap[concept].get("units", {})
                for unit_key in ("USD", "USD/shares", "shares"):
                    if unit_key not in units:
                        continue
                    unit_entries: list[Any] = units[unit_key]
                    annual: list[Any] = [
                        e for e in unit_entries
                        if e.get("form") in ("10-K", "20-F") and e.get("val") is not None
                    ]
                    if not annual:
                        continue
                    latest = sorted(annual, key=lambda x: x.get("end", ""))[-1]
                    val: float = float(latest["val"])
                    if unit_key == "USD":
                        formatted = _fmt_usd(val)
                    elif unit_key == "shares":
                        formatted = _fmt_shares(val)
                    else:
                        formatted = str(val)
                    results[label] = (formatted, str(latest.get("end", "")), unit_key)
                    break
                if label in results:
                    break

        if not results:
            return f"No XBRL financial facts found for CIK {cik}. Company may not file XBRL."

        period_dates = [v[1] for v in results.values() if v[1]]
        most_common_date = Counter(period_dates).most_common(1)[0][0] if period_dates else "N/A"

        lines = [
            f"Financial Summary — {company_name} (CIK {cik})",
            f"Most recent annual data (as of approx. {most_common_date}):",
            "=" * 55,
        ]
        for label, (val_str, date, _) in results.items():
            lines.append(f"  {label:<25}  {val_str:>15}  (period ending {date})")

        lines.append("")
        lines.append(
            "Source: SEC EDGAR XBRL data. "
            "Use get_financial_facts for full historical series per metric."
        )
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Company with CIK {cik} not found or no XBRL data available."
        return f"HTTP error: {e}"
    except Exception as e:
        logger.error("get_company_facts_summary error: %s", e)
        return f"Error fetching company facts: {e}"


@mcp.tool()
async def get_filing_document(
    cik: str,
    accession_number: str,
    api_key: str = "",
) -> str:
    """
    Get the index of documents in a specific SEC filing.
    Returns all documents in the filing with their names and URLs.
    Use this to access the actual 10-K, 10-Q, 8-K, proxy, or Form 4 document.

    Args:
        cik: Company CIK number
        accession_number: Filing accession number (e.g. "0000320193-24-000123")
                          Obtain from get_recent_filings results.
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    try:
        acc_clean = accession_number.replace("-", "")
        filing_index_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
            f"{acc_clean}-index.json"
        )
        try:
            data = await _get(filing_index_url)
        except httpx.HTTPStatusError:
            # Fallback: return constructed URLs the user can visit directly
            return (
                f"Filing index for CIK {cik}, accession {accession_number}:\n"
                f"  Directory: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/\n"
                f"  HTML index: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
                f"{accession_number}-index.htm\n"
                f"  EDGAR viewer: https://www.sec.gov/cgi-bin/browse-edgar?"
                f"action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40"
            )

        items: list[Any] = data.get("directory", {}).get("item", [])
        if not items:
            return f"No documents found in filing {accession_number}."

        base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
        lines = [f"Documents in filing {accession_number} (CIK {cik}):\n"]
        for item in items[:20]:
            name: str = item.get("name", "")
            doc_type: str = item.get("type", "")
            size: str = str(item.get("size", ""))
            lines.append(
                f"  [{doc_type}] {name}  ({size} bytes)\n"
                f"    URL: {base_url}{name}"
            )
        return "\n".join(lines)

    except Exception as e:
        logger.error("get_filing_document error: %s", e)
        return f"Error fetching filing document index: {e}"


@mcp.tool()
async def compare_companies(
    cik_list: str,
    metric: str = "Revenues",
    api_key: str = "",
) -> str:
    """
    Compare a financial metric across multiple companies side by side.
    Returns the most recent annual value for each company.

    Args:
        cik_list: Comma-separated CIK numbers (e.g. "320193,789019,1652044"
                  for Apple, Microsoft, Alphabet)
        metric: XBRL financial concept to compare (e.g. "Revenues", "NetIncomeLoss",
                "Assets", "ResearchAndDevelopmentExpense")
        api_key: Your API key for unlimited access (optional)
    """
    client_id = api_key or "anonymous"
    if not _check_usage(client_id):
        return _UPGRADE_MSG

    ciks = [c.strip() for c in cik_list.split(",") if c.strip()]
    if not ciks:
        return "No CIK numbers provided."
    if len(ciks) > 5:
        return "Maximum 5 companies per comparison to respect API rate limits."

    try:
        # Each row: (company_name, cik, formatted_value, period_date)
        rows: list[tuple[str, str, str, str]] = []
        for company_cik in ciks:
            cik_padded = _pad_cik(company_cik)
            try:
                url = (
                    f"{EDGAR_BASE}/api/xbrl/companyconcept/"
                    f"CIK{cik_padded}/us-gaap/{metric}.json"
                )
                cdata = await _get(url)
                name: str = cdata.get("entityName", f"CIK {company_cik}")
                units: dict[str, Any] = cdata.get("units", {})
                unit_key: str | None = next(iter(units), None)
                if unit_key is None:
                    rows.append((name, company_cik, "No data", ""))
                    continue
                entries: list[Any] = units[unit_key]
                annual: list[Any] = [
                    e for e in entries
                    if e.get("form") in ("10-K", "20-F") and e.get("val") is not None
                ]
                if not annual:
                    rows.append((name, company_cik, "No annual data", ""))
                    continue
                latest = sorted(annual, key=lambda x: x.get("end", ""))[-1]
                val = float(latest["val"])
                formatted = _fmt_usd(val) if unit_key == "USD" else f"{val:,.0f} {unit_key}"
                rows.append((name, company_cik, formatted, str(latest.get("end", ""))))
            except Exception as err:
                rows.append((f"CIK {company_cik}", company_cik, f"Error: {err}", ""))

        lines = [
            f"Comparison: {metric}\n",
            f"{'Company':<35} {'CIK':<12} {'Value':>18} {'Period'}",
            "-" * 75,
        ]
        for name, cik_val, val_str, date in rows:
            lines.append(f"{name:<35} {cik_val:<12} {val_str:>18} {date}")
        return "\n".join(lines)

    except Exception as e:
        logger.error("compare_companies error: %s", e)
        return f"Error comparing companies: {e}"


# ── Health check ──────────────────────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "sec-edgar-mcp"})


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "sse":
        # HTTP/SSE mode for cloud deployment (Railway, Render, etc.)
        mcp.run(transport="sse")
    else:
        # Default: stdio for local Claude Desktop / Cursor usage
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
