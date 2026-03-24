FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# Runtime config via environment variables:
# CONTACT_EMAIL    — required by SEC (your email in User-Agent header)
# MCP_TRANSPORT    — "sse" for HTTP server, "stdio" for local (default: stdio)
# PORT             — HTTP port when using SSE transport (default: 8080)
# EDGAR_MCP_API_KEY — secret key that unlocks paid tier (set this to any strong secret)
# FREE_DAILY_LIMIT — calls/day for free tier (default: 10)

ENV MCP_TRANSPORT=sse
ENV PORT=8080

EXPOSE 8080

CMD ["python", "server.py"]
