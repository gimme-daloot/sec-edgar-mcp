# SEC EDGAR Financial Intelligence MCP Server

Real-time access to SEC EDGAR — the world's largest public repository of corporate financial disclosures — exposed as MCP tools for AI agents.

## What It Does

8 tools that give AI agents direct access to:

| Tool | What it returns |
|------|----------------|
| `search_company` | Find any public company's CIK by name or ticker |
| `get_recent_filings` | List 10-K, 10-Q, 8-K, Form 4, S-1, and other filings with URLs |
| `get_financial_facts` | Historical time series for any XBRL financial metric |
| `get_company_facts_summary` | Full financial snapshot (revenue, NI, assets, debt, cash) in one call |
| `get_insider_transactions` | Form 4 insider buy/sell activity |
| `get_full_text_search` | Full-text search across 40M+ SEC filings |
| `get_filing_document` | Index of all documents in a specific filing |
| `compare_companies` | Side-by-side metric comparison across up to 5 companies |

## Why This Earns Money

SEC EDGAR is free but the API is painful:
- Requires correct User-Agent headers or get rate-limited/blocked
- XBRL taxonomy is opaque (what's the right concept name for "revenue"?)
- Full-text search API is undocumented
- No AI-friendly interface

This server solves all of that. Target users pay $19-49/month for tools that save them hours of research.

## Quick Start (Local)

```bash
# Install dependencies
pip install mcp[cli] httpx

# Set required environment variable (SEC requires this in User-Agent)
export CONTACT_EMAIL="you@example.com"

# Run locally (stdio mode for Claude Desktop / Cursor)
python server.py
```

Add to Claude Desktop `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "sec-edgar": {
      "command": "python",
      "args": ["/Users/chris/mcp-server-business/server.py"],
      "env": {
        "CONTACT_EMAIL": "you@example.com"
      }
    }
  }
}
```

## Deploy to Railway (10 minutes)

1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Create project: `railway init`
4. Set environment variables in Railway dashboard:
   - `CONTACT_EMAIL` = your email (SEC requirement)
   - `MCP_TRANSPORT` = `sse`
   - `PORT` = `8080`
   - `EDGAR_MCP_API_KEY` = generate a strong random string (this is your paid tier secret)
   - `FREE_DAILY_LIMIT` = `10`
5. Deploy: `railway up`
6. Copy the Railway URL and paste it into `mcpize.yaml` under `server.url`

Railway free tier: 500 hours/month. Hobby plan ($5/month) for production.

## Deploy to Render

1. Push this directory to a GitHub repo
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — just click Deploy
5. Set env vars in Render dashboard (CONTACT_EMAIL, EDGAR_MCP_API_KEY)
6. Copy the Render URL into `mcpize.yaml`

Render free tier: sleeps after 15 min inactivity. Starter plan ($7/month) stays awake.

## Deploy to Fly.io (recommended for production)

```bash
# Install flyctl
brew install flyctl

# Launch
flyctl launch --name sec-edgar-mcp

# Set secrets
flyctl secrets set CONTACT_EMAIL=you@example.com
flyctl secrets set EDGAR_MCP_API_KEY=your-secret-key-here
flyctl secrets set MCP_TRANSPORT=sse

# Deploy
flyctl deploy
```

Fly.io free tier: 3 shared VMs, 256MB RAM each. More than enough.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CONTACT_EMAIL` | Yes | — | Your email, included in SEC User-Agent header |
| `MCP_TRANSPORT` | No | `stdio` | Set to `sse` for cloud deployment |
| `PORT` | No | `8080` | HTTP port for SSE mode |
| `EDGAR_MCP_API_KEY` | No | — | Secret key for paid tier. Anyone who provides this as `api_key` parameter gets unlimited access |
| `FREE_DAILY_LIMIT` | No | `10` | Calls per day on free tier |

## Monetization Flow

1. User installs free tier via MCPize → 10 calls/day
2. User hits the limit → sees upgrade message
3. User buys Pro plan ($19/month) on MCPize → receives API key
4. User sets `api_key` parameter in their MCP client config → unlimited access

MCPize handles: Stripe billing, API key distribution, usage dashboards.
You get 85% of revenue.

## Rate Limits & SEC Compliance

The server implements token-bucket rate limiting (8 req/sec, burst 40) to stay under SEC's 10 req/sec limit. The SEC requires a descriptive User-Agent header with contact info — this is handled automatically via the `CONTACT_EMAIL` env var.

SEC EDGAR data is public domain. No redistribution restrictions.

## Publishing to MCPize

1. Create developer account: https://mcpize.com/developers
2. Deploy your server (Railway/Render/Fly.io)
3. Update `mcpize.yaml` with your server URL
4. Run: `mcpize deploy` (install CLI: `npm install -g @mcpize/cli`)
5. Monitor earnings in your MCPize dashboard

Revenue: 85% to you, 15% to MCPize. Payouts via Stripe Connect.

## Publishing to Apify

Apify is better suited for actors (individual tools), not full MCP servers.
Wrap each tool as a separate Apify Actor for maximum discoverability.

1. Create Apify account: https://apify.com
2. Publish via Apify Console → Actors → Create New
3. Set pricing: Pay-per-result or fixed monthly
4. Apify handles billing and payout (70% revenue share)

For this server, the best Apify approach is wrapping `get_financial_facts`
and `get_full_text_search` as separate pay-per-result actors ($0.10-0.50/call).

## Example Usage (with Claude)

> "What was Apple's revenue for the last 5 years?"

Claude calls:
1. `search_company("AAPL")` → CIK: 320193
2. `get_financial_facts("320193", "Revenues")` → revenue time series

> "Show me all insider selling at Tesla in the past 3 months"

Claude calls:
1. `search_company("TSLA")` → CIK: 1318605
2. `get_insider_transactions("1318605", limit=40)` → Form 4 list

> "Find all 8-K filings mentioning 'cybersecurity incident' in 2025"

Claude calls:
1. `get_full_text_search('"cybersecurity incident"', form_type='8-K', date_from='2025-01-01')`

> "Compare R&D spending: Apple vs Microsoft vs Google"

Claude calls:
1. `compare_companies("320193,789019,1652044", "ResearchAndDevelopmentExpense")`
