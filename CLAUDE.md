# Project guide for Claude Code

Course registration web app for the trainer Aziz (Faysal Aziz). Public course page + registration + PDF brochure, and an admin area to approve / reject / KIV registrations and edit courses. Read `README.md` for the full picture and `deploy/DEPLOY.md` for deployment.

## How to work here

- Stack: FastAPI, Jinja + htmx + Alpine.js, plain CSS (`app/static/css`), SQLite + SQLAlchemy 2 + Alembic, WeasyPrint, Resend. Python 3.10+.
- Run tests with `python -m pytest` (uses a throwaway database). Keep them passing; add a test with each behaviour change.
- Database changes need an Alembic migration (`alembic revision --autogenerate`), never an edited table.
- Match the existing code: small modules under `app/modules`, templates under `app/templates`, display helpers in `app/formatting.py`.
- Design: dark `#0a0a0a`, off-white `#ede9e1`, gold `#b8955a`, Bodoni Moda for display and Inter for text. Tokens are in `app/static/css/base.css`. The brand logo is `app/static/img/logo-mark.svg`.

## Rules (from the owner)

- Do not make things up. If you do not know something, say so and say where it can be checked. Back claims with command output.
- Never print, log, commit or ask for secrets. `.env` holds the Resend API key and `SECRET_KEY`; it is mode 600 and ignored by git. To change the key use `deploy/set-resend-key.sh` (hidden prompt).
- You cannot use `sudo`, and you cannot answer interactive or hidden prompts. For anything needing either, tell the owner exactly which script or command to run in a second terminal, then wait. The sudo scripts are `deploy/1-system-setup.sh` and `deploy/3-start-services.sh`; `deploy/2-app-setup.sh` needs typed (hidden) input, so the owner runs it too.
- Admin username and password are typed by the owner at a hidden prompt (`python -m scripts.create_admin`). Never set or log one.
- Keep answers short and plain. Do only what was asked.
- Work on `main`. Do not create other branches or pull requests unless asked.

## Server facts

- Droplet: Ubuntu 24.04, user `aziz`, project folder `/home/aziz/projects/regsite`, public name `register.faysalaziz.com` (A record to 168.144.242.29, DNS at DigitalOcean).
- Caddy terminates HTTPS and proxies to uvicorn on `127.0.0.1:8000`. systemd unit: `regsite`. Backup timer: `regsite-backup.timer`.
- Email: Resend, sender `Faysal Aziz <registration@register.faysalaziz.com>`, replies and alerts to `faysalabdulaziz@gmail.com`. Free plan: 100 emails a day, 3,000 a month.
