# AGENT_RULES.md - قواعد التطوير لمشروع مرصاد الذهب (Gold Radar)

1. **Language:** python 3.12. Keep it simple and readable. Add short comments. Pin every dependency version in requirements.txt. Do not add a dependency unless truly needed.
2. **SECURITY (repo is public):**
   - Never write any secret in any file: Telegram bot token, Telegram chat id, Google service-account JSON, Google Sheet id. Read them only from environment variables (names: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID`).
   - Never print or log a secret or a full request URL containing a secret, even on errors.
   - Create `.gitignore` at the start (include `.env`, `*.json` credentials, `__pycache__`, `.venv`). Never commit `.env`.
   - Never ask me to paste a secret into this chat. If a secret is needed, tell me to put it in a local `.env` file myself.
3. **STRUCTURE:** separate modules for sources, calculations, alert logic, message building, telegram, sheets storage, and main. Calculation and alert logic must be pure functions with no network calls, and must have unit tests (pytest).
4. **CONFIG:** all tunable numbers (alert threshold 0.25%, balanced-gap threshold 1%, timeouts, retries, sanity limits) live in one config file.
5. **RELIABILITY:** every network call has a timeout and limited retries with clear error messages. Validate data: reject zero/empty/absurd values. Never send a customer message built from bad data.
6. **POLITE SCRAPING:** before reading any website, check its robots.txt and terms if available, send at most one request per source per run, use a clear User-Agent (GoldRadar/0.1), and never bypass logins, captchas, or blocks. If blocked, stop and report.
7. **COMMUNICATION:** after each task, explain in simple Arabic what you did, and give me the exact commands to test it and what output I should expect. Do not move to the next task until I confirm.
8. **Do not do more than the current task asks.**
