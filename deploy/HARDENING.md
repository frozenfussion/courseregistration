# Server hardening

Run once, from the project folder, in a second terminal (it needs your sudo password). Keep your current SSH session open while you do:

```bash
sudo ./deploy/4-harden-server.sh
```

Safe to run again. It backs up what it changes to `/var/backups/regsite-hardening/<date-time>/`, never reboots, and never changes how you log in.

## What it changes

| Change | In plain words |
|---|---|
| **Firewall (ufw)** | Blocks every incoming connection except SSH (22/tcp) and the website (80/tcp, 443/tcp, and 443/udp for HTTP/3). Outgoing is unrestricted. The SSH rule is added before the firewall is switched on, and the script refuses to switch it on without it. |
| **fail2ban** | Watches `/var/log/auth.log`. An address with 5 failed SSH logins within 10 minutes is blocked for 1 hour. Settings are in `/etc/fail2ban/jail.d/sshd-regsite.conf`. |
| **SSH drop-in** `/etc/ssh/sshd_config.d/10-hardening.conf` | `PermitEmptyPasswords no`, `X11Forwarding no`, `MaxAuthTries 4`, `LoginGraceTime 30`. It does **not** set `PermitRootLogin`, `PasswordAuthentication` or `AllowUsers`, and the script checks the first two are identical before and after, and puts things back if not. Applied with a reload, not a restart. |
| **Updates** | Makes sure `unattended-upgrades` is installed and on, with `Automatic-Reboot "false"`. Runs `apt-get upgrade` once now. If a reboot is needed it only tells you. |

Not touched: the SSH port, root's SSH access, password login, Caddy, the app, the database, `.env`, kernel settings, the DigitalOcean dashboard.

## Check it

```bash
sudo ufw status verbose
sudo fail2ban-client status sshd
sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin|permitemptypasswords|x11forwarding|maxauthtries|logingracetime'
systemctl status unattended-upgrades --no-pager | head -5
ss -ltnp
curl -s https://register.faysalaziz.com/healthz
```

Before closing your existing SSH session, open a new one from your laptop and log in with your password.

## Undo

```bash
sudo ./deploy/4-harden-server.sh --undo
```

Removes the SSH drop-in (and reloads ssh), disables ufw, and stops and disables fail2ban. Installed packages and automatic security updates stay. Running the script again re-applies everything.

## Unban yourself

If you mistype your password too many times, you are blocked for an hour. From another address, or the DigitalOcean web console:

```bash
sudo fail2ban-client set sshd unbanip YOUR.IP.ADDRESS
sudo fail2ban-client status sshd        # lists currently banned addresses
```

## See who has been trying to log in

```bash
sudo grep 'Failed password' /var/log/auth.log | tail -20
sudo grep 'Failed password' /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head
sudo fail2ban-client status sshd
last -n 20
sudo zgrep Ban /var/log/fail2ban.log*
```

## Not covered

A DigitalOcean Cloud Firewall (if any) is set in the dashboard and cannot be checked from the server. Root can still log in over SSH with a password, as before; that was kept on purpose, so a strong root password matters.
