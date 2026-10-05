# Course registration

A small web app for a professional trainer. Students read about the programme that is currently open, download a PDF brochure, and register. The trainer approves, rejects or keeps in view (KIV) each request from a private admin area, and the student is told by email.

Live at **https://register.faysalaziz.com** (once deployed, see [`deploy/DEPLOY.md`](deploy/DEPLOY.md)).

## What it does

**For students (public site, no accounts)**
- Shows the one **active** course: title, tagline, introduction, learning outcomes, prerequisites, who should attend, the module-by-module outline, dates, venue, fee and seats left.
- **Download brochure** builds a 3-page A4 PDF on the spot from the same course data, in the same dark theme, with a QR code to the page.
- A registration form (name, email, phone, company, job title, notes, consent). It confirms by email and tells the student the trainer will decide.
- When approved registrations reach the course capacity, the page says **Fully booked** and closes the form. A registration deadline closes it the same way.
- Works on phones and desktops, with a short entrance animation that respects "reduce motion".

**For the trainer (admin, one username and password)**
- **Registrations**: filter by All / Pending / Approved / KIV / Rejected, search by name, email or company, and approve, KIV or reject with one click. Any decision can be changed later. An optional note goes into the student's email. Every decision, and every email sent (or failed), is logged and visible per registration.
- **Seats**: only approved registrations use a seat. Approving beyond capacity is allowed but warns you.
- **CSV download** of the list you are looking at (a status, a search, or everything) for attendance sheets. It opens correctly in Excel and cannot run formulas hidden in a student's name.
- **Courses (CMS)**: create and edit courses (title, tagline, introduction, outcomes, prerequisites, audience, outline modules and topics, dates, venue, fee, capacity, deadline). A toggle makes a course active, and **only one course can be active**, enforced by the database itself. **Duplicate** copies a course for its next run, so earlier runs keep their own registrations and history.
- **Site content**: the trainer highlights (10,000+ training hours and so on), bio and credentials shown on the page and in the brochure.
- Sees new registrations by email too (alert to the trainer's Gmail, with Reply-To set to the student).

**Emails**: received, approved, KIV, rejected, plus the alert to the trainer. Sent through Resend over HTTPS. A failed email never loses a registration: it is logged, flagged in the admin, and can be sent again with one click.

## Tech stack

| Part | Choice | Why |
|---|---|---|
| Web framework | FastAPI | Small, modular routers, clean path to a JSON API later |
| Pages | Jinja templates + htmx + Alpine.js | Fast server-rendered pages with small interactive touches, no JavaScript build step |
| Styling | Plain CSS with design tokens (`app/static/css`) | Matches the approved design exactly with no build step. *(Tailwind was in the first plan; see "Decisions".)* |
| Database | SQLite (WAL mode) + SQLAlchemy 2 + Alembic migrations | One file, trivial to back up, ample for this load |
| PDF | WeasyPrint | HTML/CSS to PDF without a browser |
| Email | Resend HTTPS API (SMTP also supported) | Free tier, works even if SMTP ports are blocked |
| Server | uvicorn behind **Caddy**, managed by systemd | Caddy handles HTTPS certificates automatically |

Fonts (Bodoni Moda and Inter) are self-hosted; both are SIL Open Font License. htmx and Alpine.js are vendored in `app/static/js`, so the site loads nothing from third parties.

## Project layout

```
app/
  main.py            app factory, security headers, error handlers
  config.py          settings from environment variables (.env)
  db.py  models.py   SQLite engine and tables
  services.py        queries and rules: active course, seats, duplicate course, site content
  security.py        password hashing, sessions, CSRF, form token, login throttling
  formatting.py      dates and number display
  seed.py            the starter course (taken from the course outline)
  modules/
    public/          course page, /register, /brochure.pdf
    admin/           login, registrations, courses, site content
    mail/            email building, delivery log, providers (Resend, SMTP, console)
    spamcheck/       registration abuse checks (the place to plug in smarter checks)
    brochure/        PDF generation
  templates/  static/
migrations/          Alembic migrations
scripts/             create_admin, seed, backup, send_test_email
deploy/              Caddyfile, systemd units, the 3 setup scripts, DEPLOY.md
tests/               pytest suite
```

## Run it on your own computer

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # the defaults are fine for development
alembic upgrade head            # creates data/regsite.db
python -m scripts.seed          # adds the starter course
python -m scripts.create_admin  # asks for a username and password
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 (public) and http://127.0.0.1:8000/admin (admin). With `MAIL_PROVIDER=console`, emails are printed in the terminal instead of sent.

WeasyPrint needs Pango. On Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`.

Run the tests with `python -m pytest`. They use a throwaway database.

## Configuration

Everything is set by environment variables, normally in `.env` (never committed). See [`.env.example`](.env.example) for every setting with comments. The important ones:

| Setting | Meaning |
|---|---|
| `APP_ENV` | `production` turns on secure cookies and refuses to start with unsafe settings |
| `SECRET_KEY` | Long random string that signs sessions. Production refuses a default or short key |
| `BASE_URL` | Public address (`https://register.faysalaziz.com`), used in emails and the QR code |
| `MAIL_PROVIDER` | `resend`, `smtp` or `console` |
| `MAIL_FROM` | `Faysal Aziz <registration@register.faysalaziz.com>` (must be on the domain verified in Resend) |
| `MAIL_REPLY_TO`, `ADMIN_ALERT_EMAIL` | Where student replies and new-registration alerts go (`faysalabdulaziz@gmail.com`) |
| `RESEND_API_KEY` | A sending-access key limited to the verified domain |

## Email setup (Resend)

- The sending domain is `register.faysalaziz.com`, verified in Resend with a DKIM TXT record and two CNAME records added in DigitalOcean DNS. Region: Tokyo.
- Student replies go to the trainer's Gmail through the `Reply-To` header. Receiving is not needed on this domain.
- Resend's free plan allows **100 emails a day and 3,000 a month**. Each registration sends about 3 emails (the student's confirmation, the alert to the trainer, and later the decision), so roughly 30 registrations a day fit. Beyond that, sending pauses and failed emails show up in the admin.
- Check it with `python -m scripts.send_test_email you@example.com`.

## Security notes

- Admin passwords are hashed with Argon2. Sign-in is throttled (5 failures per 15 minutes per network address) and answers the same way for a wrong username and a wrong password.
- Sessions are signed, HttpOnly, `SameSite=Lax` cookies, and `Secure` in production. Every admin POST needs a CSRF token.
- The public form has a hidden trap field, a signed form token that also measures how fast it was filled, a per-network rate limit, and a link-spam flag. Suspicious submissions are either dropped quietly or saved with a **Flagged** badge for you to review.
- Responses carry a Content-Security-Policy and other security headers. The app listens only on localhost, and only Caddy faces the internet.
- Secrets live only in `.env` (mode 600). API docs endpoints are switched off.
- The CSV export neutralises spreadsheet formulas. The service runs as a normal user with write access limited to `data/`.

## Data and backups

All data is in `data/regsite.db`. A systemd timer writes a safe copy to `data/backups/` every night at 03:30 (the newest 14 are kept). To restore: stop the service, copy a backup over `data/regsite.db`, start it again. Copy `data/backups/` off the server now and then, because a backup on the same machine does not protect against losing the machine.

## Deploying

See [`deploy/DEPLOY.md`](deploy/DEPLOY.md). In short: `sudo ./deploy/1-system-setup.sh`, then `./deploy/2-app-setup.sh`, then `sudo ./deploy/3-start-services.sh`. The sudo steps are separate scripts so you type your own password. [`deploy/CLAUDE_CODE_PROMPT.md`](deploy/CLAUDE_CODE_PROMPT.md) has the prompt for letting Claude Code drive the deployment.

## Extending

The app is split into modules under `app/modules`. Each has its own router and templates, and is registered in `app/main.py` or `app/modules/admin/__init__.py`.

- **Smarter spam checks** (for example a small language model that reads the notes field): add a class with a `name` and `check(submission, db)` method to `app/modules/spamcheck` and list it in `DEFAULT_CHECKERS`. A check can accept, flag (save with a badge) or reject.
- **Another email provider**: add a class with `send(message)` to `app/modules/mail/providers.py` and return it from `get_provider`.
- **New admin page**: add a router in `app/modules/admin`, include it in the `protected` router so it gets login and CSRF checks automatically.
- **Database changes**: edit `app/models.py`, then `alembic revision --autogenerate -m "what changed"` and `alembic upgrade head`.

## Decisions worth knowing

- **Plain CSS instead of Tailwind.** The first plan listed Tailwind. The approved design was built with its own tokens, and plain CSS reproduces it exactly with no build step or Node on the server. Moving to Tailwind later is possible but is a rewrite of the templates' classes.
- **Where the brochure fits in.** The PDF is rendered from `app/templates/brochure/brochure.html`, using static font files (`app/static/fonts/pdf-*.ttf`) made by `scripts/make_pdf_fonts.sh`.
- **Sessions are signed cookies**, so signing out ends the browser session but cannot revoke a stolen cookie before it expires (12 hours). Changing `SECRET_KEY` signs everyone out.
- **Single process.** SQLite and the in-process brochure cache are designed for one uvicorn process, which is plenty here.

## Troubleshooting

| Symptom | Check |
|---|---|
| Site returns 502 | `systemctl status regsite` and `journalctl -u regsite -n 50` |
| HTTPS certificate not issued | DNS A record points at the server and ports 80 and 443 are open; `journalctl -u caddy -n 50` |
| No emails arrive | `.venv/bin/python -m scripts.send_test_email you@example.com`; check the admin banner and the registration's email history; confirm the domain shows Verified in Resend |
| App refuses to start | The error names the unsafe setting (secret key, base URL, missing API key) |
| Brochure fails | Pango libraries missing: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0` |
