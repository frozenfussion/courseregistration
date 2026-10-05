# Deploying to the DigitalOcean droplet

Target: Ubuntu 24.04 droplet, user `aziz`, folder `/home/aziz/projects/regsite`, site `https://register.faysalaziz.com`.

Already done (do not redo): the DNS A record `register.faysalaziz.com` → `168.144.242.29`, and the Resend domain `register.faysalaziz.com` with its three DNS records.

Anything that needs `sudo` is in its own script, so you type your own password in a second terminal and Claude Code never sees it.

## 1. Get the code onto the droplet

### Option A: from GitHub (recommended, and the easiest way to update later)

1. Install the GitHub CLI (needs sudo, run in your second terminal). These are the official commands from the GitHub CLI project:

   ```bash
   (type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
     && sudo mkdir -p -m 755 /etc/apt/keyrings \
     && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
     && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
     && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
     && sudo mkdir -p -m 755 /etc/apt/sources.list.d \
     && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
     && sudo apt update \
     && sudo apt install gh -y
   ```

2. Sign in to GitHub (interactive, you do it): `gh auth login`
3. Clone into the project folder (it must be empty):

   ```bash
   cd ~/projects/regsite
   gh repo clone frozenfussion/courseregistration .
   ```

### Option B: copy a zip from your Windows laptop

In PowerShell on the laptop (Windows 10/11 include `scp` and `ssh`):

```powershell
cd C:\Users\faysa\Development\web\regsite
scp .\regsite.zip aziz@168.144.242.29:/home/aziz/projects/regsite/
ssh aziz@168.144.242.29
```

Then on the droplet:

```bash
cd ~/projects/regsite
sudo apt install -y unzip        # only if unzip is missing
unzip -o regsite.zip && rm regsite.zip
```

## 2. Install Claude Code on the droplet (optional, to let it drive the rest)

Claude Code needs 4 GB or more of RAM (the droplet has 7.8 GB) and a Pro, Max, Team, Enterprise or Console account.

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
cd ~/projects/regsite && claude
```

On first launch it opens a browser for login. On a server it cannot, so press `c` to copy the login URL, open it on your laptop, and if the page shows a code, paste it at the `Paste code here if prompted` prompt in the terminal.

Then paste the prompt from [`CLAUDE_CODE_PROMPT.md`](CLAUDE_CODE_PROMPT.md).

## 3. The three setup scripts (what Claude Code will walk you through)

| Step | Command | Sudo? | What it does |
|---|---|---|---|
| 1 | `sudo ./deploy/1-system-setup.sh` | yes | Installs system packages (Python venv, the PDF libraries), Caddy and the GitHub CLI; installs the Caddyfile and systemd units; opens ports 80/443 if `ufw` is active. Does not start the site. |
| 2 | `./deploy/2-app-setup.sh` | no | Python environment and dependencies; writes `.env` (asks for the Resend key at a hidden prompt, generates the secret key); creates the database; adds the starter course; asks you to choose the admin username and password. |
| 3 | `sudo ./deploy/3-start-services.sh` | yes | Starts the site and the nightly backup timer, reloads Caddy, and runs a local and a public health check. |

If a DigitalOcean Cloud Firewall is attached to the droplet, it must allow TCP 80 and 443 (this is set in the DigitalOcean dashboard, not on the server).

## 4. Check it works

```bash
curl -s https://register.faysalaziz.com/healthz              # {"status":"ok"}
curl -sI https://register.faysalaziz.com/ | head -5           # HTTP/2 200 and security headers
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://register.faysalaziz.com/brochure.pdf   # 200 application/pdf
systemctl status regsite --no-pager | head -5
systemctl list-timers regsite-backup.timer --no-pager
.venv/bin/python -m scripts.send_test_email faysalabdulaziz@gmail.com
```

Then, in a browser: open the site, register with a test email, check the confirmation email and the alert in your Gmail, sign in at `/admin`, approve the test registration, and check the approval email.

## 5. First things to do in the admin

1. **Courses**: set the dates, daily time, venue, map link, fee and capacity on the starter course. Until you do, the page shows "To be announced".
2. **Site content**: check the highlights, bio and credentials.
3. Remove your test registration: open it in Registrations (the arrow at the end of its row) and choose **Delete this registration**.

## 6. Replace the first Resend key with a restricted one

The key used during setup may have full access. In the Resend dashboard create a new API key with **Sending access** restricted to `register.faysalaziz.com` (Resend's docs say a key's value is shown only once, so copy it straight into the next step), then:

```bash
./deploy/set-resend-key.sh          # hidden prompt, updates .env
sudo systemctl restart regsite
.venv/bin/python -m scripts.send_test_email faysalabdulaziz@gmail.com
```

When the test passes, delete the old key in the Resend dashboard.

## 7. Updating later

```bash
cd ~/projects/regsite
git pull
./deploy/update.sh                   # backup, dependencies, database migrations
sudo systemctl restart regsite
```

(With Option B, unzip the new files over the folder first, then run `./deploy/update.sh`.)

## 8. Backups

The database is backed up every night at 03:30 into `data/backups/` (newest 14 kept). Run one now with `.venv/bin/python -m scripts.backup`. To restore:

```bash
sudo systemctl stop regsite
cp data/backups/regsite-YYYYMMDD-HHMMSS.db data/regsite.db
sudo systemctl start regsite
```

Copy `data/backups/` to your laptop now and then (`scp aziz@168.144.242.29:projects/regsite/data/backups/* .`).

## Server hardening (optional)

```bash
sudo ./deploy/4-harden-server.sh
```

Turns on the firewall (SSH, 80, 443 only), bans addresses after repeated failed SSH logins (fail2ban), tightens four SSH settings and keeps automatic security updates on. It does not change how you log in (port 22, password, root access as before) and never reboots. Undo with `sudo ./deploy/4-harden-server.sh --undo`. Details, checks and how to unban yourself: [`HARDENING.md`](HARDENING.md). A DigitalOcean Cloud Firewall is separate and set in the dashboard.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `502 Bad Gateway` | `journalctl -u regsite -n 50 --no-pager`: the app is not running or crashed (often a bad `.env`) |
| Browser says the certificate is invalid, or Caddy logs ACME errors | The A record must point to this droplet, and ports 80 and 443 must be reachable from the internet; `journalctl -u caddy -n 50 --no-pager` |
| App exits at start with "Unsafe production configuration" | The message names the problem; fix `.env` (never paste its contents anywhere) |
| Emails fail | `.venv/bin/python -m scripts.send_test_email you@example.com` prints the provider's reason. A 403 usually means the domain is not verified or the key does not allow sending from it |
| Brochure returns 500 | `journalctl -u regsite -n 50`: missing Pango libraries mean step 1 did not finish |
| Locked out of admin | `.venv/bin/python -m scripts.create_admin <username>` sets a new password |
