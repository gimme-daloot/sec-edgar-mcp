# Pricing Strategy — SEC EDGAR Intelligence MCP

## Recommended Pricing Tiers

### Free Tier (always-on)
- 10 calls/day, no API key required
- Purpose: discovery, trial, occasional research
- Conversion target: 5-8% to paid (industry standard for dev tools)

### Pro — $19/month
- Unlimited calls
- 1 seat
- Target: individual investors, analysts, journalists, researchers
- Comparable tools: Bloomberg Terminal ($24,000/yr), Koyfin ($25/mo), Wisesheets ($39/mo)
  → $19/mo is a clear no-brainer for anyone doing regular financial research

### Team — $49/month
- Unlimited calls, 5 API keys
- Target: small hedge funds, research teams, boutique M&A firms
- Positioning: cheaper than one Bloomberg Terminal for the whole team

### Enterprise — $199/month
- Unlimited calls, unlimited seats, priority support, SLA
- Target: compliance teams, large funds, corporate dev departments
- Discuss custom data needs (additional parsing, specific form types)

---

## Revenue Projections

### Conservative (3 months post-launch)
- Free users: ~200 (typical for a developer tool with good SEO)
- Paid conversion at 5%: 10 paid users
- Mix: 7 Pro ($19) + 2 Team ($49) + 1 Enterprise ($199)
- Monthly gross: $430
- After MCPize 15% cut: **$365/month**

### Realistic (6 months)
- Free users: ~800
- Paid: 50 users
- Mix: 35 Pro + 10 Team + 5 Enterprise
- Monthly gross: $2,610
- After MCPize 15% cut: **$2,218/month**

### Good (12 months, with Apify + direct + MCPize)
- 200 paid users across all channels
- Monthly gross: ~$8,000
- After platform cuts: **~$6,500/month**

---

## MCPize-Specific Notes

- Revenue share: 85% to you, 15% to MCPize
- Payout: via Stripe Connect, standard Stripe payout schedule (2-7 days)
- Pricing update: you can change tiers anytime via dashboard
- Trial periods: MCPize supports optional 7-day paid trials (recommended for Team/Enterprise)
- Metering: MCPize can handle call-based billing if you prefer pay-per-use instead of subscription

## Competing Products (to anchor your pricing)

| Product | Price | What it does |
|---------|-------|-------------|
| Bloomberg Terminal | $2,000/mo | Professional data terminal |
| Koyfin | $25/mo | Stock charts + fundamentals |
| Wisesheets | $39/mo | Excel/Sheets SEC data plugin |
| Macrotrends | Free/Ad | Manual web browsing only |
| SEC EDGAR Direct | Free | Requires manual API integration |
| **This server** | **$19/mo** | AI-native, no-code SEC data access |

---

## MCPize Publishing Checklist

1. Account: https://mcpize.com/developers → create developer account
2. CLI: `npm install -g @mcpize/cli` → `mcpize login`
3. Deploy server (Railway/Render/Fly) — get public HTTPS URL
4. Update `mcpize.yaml` → set `server.url` to your deployment URL
5. Run `mcpize deploy` — submits for review
6. Review time: typically 1-3 business days (based on MCPize blog posts)
7. Once approved: listing goes live, Stripe Connect setup prompt appears
8. Connect Stripe account → payouts enabled immediately

## Apify Publishing Checklist

1. Account: https://apify.com → create account
2. Wrap `get_financial_facts` and `get_full_text_search` as standalone Apify Actors
3. Pricing on Apify: Pay-per-result ($0.50 per query) or monthly ($15/mo)
4. Submit via Apify Console → publish to Store
5. Review time: 3-7 business days
6. Revenue share: 70% to you, 30% to Apify
7. Payout: monthly via bank transfer or PayPal, minimum $50

## Launch Strategy

**Week 1:** Deploy to Railway (free), list on MCPize free while in review.

**Week 2:** Post to:
- r/financialindependence, r/algotrading, r/investing — "built an MCP for SEC data"
- Hacker News Show HN — "SEC EDGAR as an MCP tool"
- Twitter/X finance community

**Week 3:** Reach out to:
- Claude/Cursor power user communities
- Financial analyst Discord servers
- AI agent builder communities (Langchain Discord, etc.)

**Ongoing:**
- Write one SEO blog post/week: "How to get Apple's 10-K with AI",
  "Insider trading research with Claude", etc.
- These drive free→paid conversion organically
