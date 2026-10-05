# Prompt for Claude Code on the droplet

Start `claude` inside `~/projects/regsite` (after the code is there, see `DEPLOY.md` section 1), then paste everything in the box below.

```text
You are deploying the course registration app in this folder (~/projects/regsite) on this Ubuntu 24.04
DigitalOcean droplet, to https://register.faysalaziz.com. Read CLAUDE.md, README.md and deploy/DEPLOY.md first.

How to work:
- Never make anything up. Back every claim with command output. If you do not know something, say so.
- You cannot use sudo. Whenever a step needs sudo, tell me the exact command, wait while I run it in my second
  terminal, and continue only when I say it is done. Do not try to work around sudo.
- Never print, log, commit or ask me for secrets. Do not cat or echo .env. Use "sed" to show it with the
  secret values hidden if you need to look at it. The Resend key and the admin password are typed by me at hidden
  prompts.
- Keep updates short. Do only what is asked. Work on the main branch only, no other branches or pull requests.

Do this, in order, and show proof for each step:
1. Check the starting state: whoami, pwd, git status and git log -1 (the repo should be on main and clean),
   python3 --version, free -h, df -h /, and whether anything is already listening on ports 80, 443 or 8000
   (ss -ltnp). Tell me anything unexpected before going on.
2. Confirm DNS: that register.faysalaziz.com resolves to this server's public IP (compare with curl -s ifconfig.me).
3. Tell me to run:  sudo ./deploy/1-system-setup.sh   and wait. Afterwards verify caddy, gh, and the two systemd unit
   files exist (they must not be running yet).
4. Run ./deploy/2-app-setup.sh. It asks me for the Resend API key and the admin username and password at hidden
   prompts, so tell me when it is waiting for me and let me type. Afterwards verify: .env exists with mode 600,
   alembic is at head, one active course exists, one admin exists (count only, never show the hash).
5. Run the tests: .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q. Report the result.
6. Tell me to run:  sudo ./deploy/3-start-services.sh   and wait.
7. Verify like a skeptic and show the output of each:
   - systemctl status regsite (active), systemctl list-timers regsite-backup.timer
   - curl -s https://register.faysalaziz.com/healthz
   - curl -sI https://register.faysalaziz.com/ (200, HSTS and the other security headers present)
   - curl -sI http://register.faysalaziz.com/ redirects to https
   - the brochure: curl -s -o /tmp/b.pdf -w "%{http_code} %{content_type}\n" https://register.faysalaziz.com/brochure.pdf
     and check it starts with %PDF and pdfinfo (if installed) reports 3 pages
   - /admin redirects to /admin/login, and /docs and /openapi.json return 404
   - .venv/bin/python -m scripts.send_test_email faysalabdulaziz@gmail.com  (tell me to check my inbox)
   - listening sockets (ss -ltnp): the app is bound only to 127.0.0.1:8000, and the only public listeners are SSH (22)
     and Caddy (80 and 443). Say plainly that a DigitalOcean Cloud Firewall, if any, cannot be checked from the server.
8. Run .venv/bin/python -m scripts.backup and show that a backup file was created in data/backups.
9. Finish with a short report: what passed, what failed or could not be verified, and what I should do next
   (open the admin, fill in dates, venue and fee, then replace the setup Resend key with a sending-only key using
   ./deploy/set-resend-key.sh).
```
