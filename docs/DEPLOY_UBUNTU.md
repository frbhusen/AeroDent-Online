# Hosting AeroDent for free on your own Ubuntu server

This guide takes a fresh Ubuntu server to a public, secure AeroDent site at an address like
`https://myclinic.duckdns.org`. It covers the database, HTTPS, automatic start on boot, daily
backups and updates.

**Total cost: $0.** Everything used is free: Ubuntu, PostgreSQL, nginx, Python, gunicorn,
a free DuckDNS address, and free Let's Encrypt HTTPS certificates. (You still pay for your
server's electricity and internet, of course.)

The commands and configuration files below were rehearsed on Ubuntu 24.04 before being written
down. The rehearsal covered:

* the dedicated system user, Python environment and settings file;
* database creation, migrations and the Super Admin command;
* the service's exact start command;
* nginx with HTTPS in front, in production mode, with a browser sign-in;
* creating a clinic, uploading an X-ray and exporting a clinic backup;
* the backup script, and both restore procedures;
* the Tailscale-style nginx setup.

The only steps not rehearsed are those that need your real internet connection: DuckDNS,
Let's Encrypt's certificate check, your router, and signing in to Tailscale. For those, the
standard tools and commands are used unchanged.

---

## Contents

0. [Before you start](#0-before-you-start)
1. [Choose how people will reach your server](#1-choose-how-people-will-reach-your-server)
2. [Prepare Ubuntu](#2-prepare-ubuntu)
3. [Install and secure PostgreSQL (the database)](#3-install-and-secure-postgresql-the-database)
4. [Download AeroDent and install its Python packages](#4-download-aerodent-and-install-its-python-packages)
5. [Write the settings file](#5-write-the-settings-file)
6. [Create the database tables and your admin account](#6-create-the-database-tables-and-your-admin-account)
7. [Run AeroDent as a service (starts on boot)](#7-run-aerodent-as-a-service-starts-on-boot)
8. [Get a free address with DuckDNS](#8-get-a-free-address-with-duckdns)
9. [Open the firewall and your router](#9-open-the-firewall-and-your-router)
10. [nginx + free HTTPS with Let's Encrypt](#10-nginx--free-https-with-lets-encrypt)
11. [First sign-in and creating your first clinic](#11-first-sign-in-and-creating-your-first-clinic)
12. [Automatic daily backups (and how to restore)](#12-automatic-daily-backups-and-how-to-restore)
13. [Updating AeroDent](#13-updating-aerodent)
14. [Security checklist](#14-security-checklist)
15. [Alternative: no public IP? Use Tailscale Funnel](#15-alternative-no-public-ip-use-tailscale-funnel)
16. [Troubleshooting](#16-troubleshooting)
17. [Command cheat sheet](#17-command-cheat-sheet)

---

## 0. Before you start

**You need:**

| Requirement | Notes |
|---|---|
| Ubuntu **22.04** or **24.04** (server or desktop) | 20.04 is too old (its Python is 3.8; AeroDent needs 3.10+). Check with `lsb_release -a`. |
| At least **1 GB RAM** (2 GB+ recommended) and **10 GB free disk** | X-ray images are stored in the database, so give it room to grow. |
| An account on the server that can use `sudo` | |
| Internet access on the server | |
| Access to your router's settings (if the server is at home or in the clinic) | Needed to forward ports 80 and 443. |

**How to read this guide:**

* Run commands in a terminal on the server, **one block at a time**, and read the output.
* Lines starting with `#` are comments; you don't need to type them.
* Anything in `UPPER_CASE` like `YOUR_NAME` must be replaced with your own value.
* If you connect over SSH: `ssh your-user@SERVER_LAN_IP`.

**What you are building:**

```
 Patient/clinic browser or Android app
            │  https://myclinic.duckdns.org   (encrypted)
            ▼
 ┌──────────────── your Ubuntu server ─────────────────┐
 │ nginx  (ports 80/443, HTTPS certificate, redirects) │
 │   │  http://127.0.0.1:8000  (only reachable inside) │
 │   ▼                                                 │
 │ gunicorn → AeroDent (Flask)       systemd keeps it  │
 │   │                               running           │
 │   ▼                                                 │
 │ PostgreSQL (only reachable inside the server)       │
 │   all clinic data + X-ray images                    │
 └─────────────────────────────────────────────────────┘
```

---

## 1. Choose how people will reach your server

People on the internet need a way to reach your server. Check which situation you are in:

1. On the server, run:
   ```bash
   curl -4 https://ifconfig.me ; echo
   ```
   This prints your **public IP** (for example `93.184.216.34`).
2. Log in to your router and find its **WAN / Internet IP** (often on the status page).

| Result | What it means | Follow |
|---|---|---|
| Both numbers are the **same** | You have a real public IP. | **Main path: sections 2 → 14** (DuckDNS + your router). |
| The router's WAN IP starts with `100.64`–`100.127`, `10.`, `172.16`–`172.31` or `192.168.`, or differs from ifconfig.me | Your ISP uses CGNAT; incoming connections can't reach you. | Sections 2 → 7, then **section 15 (Tailscale Funnel)** instead of 8–10. |
| You rent a VPS (the server is in a data center) | It already has a public IP. | Main path; skip the router part of section 9. |
| Your ISP blocks incoming ports 80/443 | Main path won't work. | Section 15. |

> Your home/clinic public IP may change from time to time. That's fine: DuckDNS (section 8)
> follows the change automatically.

---

## 2. Prepare Ubuntu

### 2.1 Update everything

```bash
sudo apt update
sudo apt -y full-upgrade
sudo reboot          # only needed if the upgrade installed a new kernel; safe anyway
```

Reconnect after the reboot.

### 2.2 Install the tools AeroDent needs

```bash
sudo apt install -y git curl python3 python3-venv python3-pip \
                    postgresql nginx certbot python3-certbot-nginx ufw
python3 --version     # must be 3.10 or newer
```

### 2.3 Set the server's time zone to the clinic's time zone

AeroDent uses the server's clock for "today" (agenda, dashboard, recall list), so this
matters. Pick your zone from the list:

```bash
timedatectl list-timezones | grep -i -E "damascus|riyadh|dubai|cairo|amman|beirut|baghdad|istanbul"
sudo timedatectl set-timezone Asia/Damascus     # ← use yours
timedatectl                                     # check "Time zone" and "System clock synchronized: yes"
```

### 2.4 Turn on automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades   # answer "Yes"
```

### 2.5 Create a dedicated user for AeroDent

AeroDent runs as its own locked-down user (no password, no login shell), never as root:

```bash
sudo adduser --system --group --home /opt/aerodent --shell /usr/sbin/nologin aerodent
sudo mkdir -p /var/lib/aerodent/storage
sudo chown -R aerodent:aerodent /var/lib/aerodent
```

---

## 3. Install and secure PostgreSQL (the database)

PostgreSQL was installed in 2.2 and is already running. Check:

```bash
sudo systemctl status postgresql --no-pager | head -5    # should say "active"
```

### 3.1 Create a database and a database user

First generate a strong random password for the database user. Letters and digits only, so it
works inside a URL:

```bash
DB_PASSWORD=$(openssl rand -hex 24)
echo "Your database password is: $DB_PASSWORD"
```

**Copy that password somewhere safe for the next 10 minutes;** you'll paste it in section 5.

```bash
sudo -u postgres psql -c "CREATE ROLE aerodent LOGIN PASSWORD '$DB_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE aerodent OWNER aerodent;"
```

Both commands should answer `CREATE ROLE` and `CREATE DATABASE`.

### 3.2 Make sure the database is not reachable from the internet

Ubuntu's PostgreSQL only listens inside the server by default. Confirm:

```bash
sudo ss -ltnp | grep 5432
```

You must only see `127.0.0.1:5432` and/or `[::1]:5432`. If you see `0.0.0.0:5432`, someone
changed `listen_addresses`. Set it back to `'localhost'` in
`/etc/postgresql/*/main/postgresql.conf` and run `sudo systemctl restart postgresql`.

---

## 4. Download AeroDent and install its Python packages

### 4.1 Download the code

```bash
sudo -u aerodent git clone https://github.com/frbhusen/aerodent-online.git /opt/aerodent/app
```

**If the repository is private**, GitHub will ask for a username and password. Passwords
don't work there; use one of these:

* **Personal access token (easiest):** on GitHub go to *Settings → Developer settings →
  Personal access tokens → Fine-grained tokens → Generate new token*. Give it access to
  only this repository with **Contents: Read-only**. Use your GitHub username and paste the
  token as the password.
* **Deploy key (best for servers):**
  ```bash
  sudo -u aerodent mkdir -p /opt/aerodent/.ssh
  sudo -u aerodent ssh-keygen -t ed25519 -N "" -f /opt/aerodent/.ssh/id_ed25519
  sudo cat /opt/aerodent/.ssh/id_ed25519.pub
  ```
  In the repository on GitHub: *Settings → Deploy keys → Add deploy key*, paste the key, and
  leave "Allow write access" **off**. Then:
  ```bash
  sudo -u aerodent git clone git@github.com:frbhusen/aerodent-online.git /opt/aerodent/app
  ```

### 4.2 Create the Python environment and install packages

```bash
sudo -u aerodent python3 -m venv /opt/aerodent/venv
sudo -u aerodent /opt/aerodent/venv/bin/pip install --upgrade pip
sudo -u aerodent /opt/aerodent/venv/bin/pip install -r /opt/aerodent/app/requirements.txt gunicorn
```

`gunicorn` is the production web server that runs AeroDent. The last line should end with
`Successfully installed ...`.

---

## 5. Write the settings file

All settings live in one file readable only by root and the `aerodent` user.

### 5.1 Generate a secret key

```bash
openssl rand -hex 32
```

Copy the output (64 characters). It signs session cookies. Never share it or commit it to git.

### 5.2 Create the file

```bash
sudo mkdir -p /etc/aerodent
sudo nano /etc/aerodent/aerodent.env
```

Paste this, then replace `DB_PASSWORD_FROM_SECTION_3` and `SECRET_KEY_FROM_5_1`:

```ini
# --- Required -------------------------------------------------------------
AERODENT_ENV=production
DATABASE_URL=postgresql+psycopg://aerodent:DB_PASSWORD_FROM_SECTION_3@localhost:5432/aerodent
SECRET_KEY=SECRET_KEY_FROM_5_1

# nginx sits in front of AeroDent and sets the visitor's real IP address itself,
# so AeroDent may trust it (used for login protection and the activity log).
TRUST_PROXY_HEADERS=True

# Only used for X-rays uploaded by very old versions (new X-rays live in the database).
AERODENT_STORAGE_PATH=/var/lib/aerodent/storage

# --- Optional (these are the defaults) --------------------------------------
# AERODENT_SESSION_IDLE_MINUTES=120      # sign out after 2 hours without activity
# AERODENT_SESSION_MAX_HOURS=12          # sign out 12 hours after signing in, at the latest
# AERODENT_XRAY_MAX_MB=25                # largest X-ray upload
# AERODENT_IMPORT_MAX_MB=2048            # largest clinic backup a head doctor can import
# AERODENT_ALLOW_SELF_REGISTRATION=false # keep false: you create clinics as Super Admin
```

Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`. Then lock the file down:

```bash
sudo chown root:aerodent /etc/aerodent/aerodent.env
sudo chmod 640 /etc/aerodent/aerodent.env
```

What `AERODENT_ENV=production` does:

* refuses to start without a strong `SECRET_KEY`,
* sends the sign-in cookie only over HTTPS (`Secure`, `__Host-` prefix),
* turns on HSTS, so browsers always use HTTPS for your site.

**One consequence:** you cannot sign in over plain `http://` or by typing the server's IP.
Always use `https://your-address` (set up in section 10).

### 5.3 A helper for running AeroDent commands

Instead of typing a long command each time, create a helper:

```bash
sudo tee /usr/local/bin/aerodent-flask > /dev/null <<'EOF'
#!/bin/bash
# Runs AeroDent's `flask` commands with the production settings, as the aerodent user.
set -euo pipefail
if [ "$(id -un)" != "aerodent" ]; then exec sudo -u aerodent "$0" "$@"; fi
set -a; . /etc/aerodent/aerodent.env; set +a
cd /opt/aerodent/app
exec /opt/aerodent/venv/bin/flask --app backend.app "$@"
EOF
sudo chmod 755 /usr/local/bin/aerodent-flask
```

From now on: `sudo aerodent-flask <command>`.

---

## 6. Create the database tables and your admin account

### 6.1 Create all tables

```bash
sudo aerodent-flask db upgrade
```

You'll see several `Running upgrade ...` lines and no errors. Check:

```bash
sudo aerodent-flask db current     # ends with "(head)"
```

### 6.2 Create your Super Admin account

The **Super Admin** runs the platform: it creates clinics and their head doctors. Use a real
e-mail address you control and a strong password (at least 8 characters; 12+ recommended):

```bash
sudo aerodent-flask admin create-super-admin
```

It asks for the e-mail, a display name and the password (typed twice, hidden). It ends with
`Super Admin you@example.com created.`

> ⚠️ **Do not run `backend/seed.py` on this server.** It creates demo clinics and demo accounts
> whose passwords are published in the source code. It's for development only.

**Forgot a password later?** Any account can be reset from the server:

```bash
sudo aerodent-flask admin reset-password --email someone@example.com
```

---

## 7. Run AeroDent as a service (starts on boot)

### 7.1 Create the service

```bash
sudo tee /etc/systemd/system/aerodent.service > /dev/null <<'EOF'
[Unit]
Description=AeroDent web application (gunicorn)
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=exec
User=aerodent
Group=aerodent
WorkingDirectory=/opt/aerodent/app
EnvironmentFile=/etc/aerodent/aerodent.env
ExecStart=/opt/aerodent/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:8010 \
    --timeout 300 \
    --forwarded-allow-ips 127.0.0.1 \
    --access-logfile - \
    --error-logfile - \
    backend.app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now aerodent
sudo systemctl status aerodent --no-pager | head -5
curl -s -o /dev/null -w "AeroDent: %{http_code}\n" http://127.0.0.1:8010/
curl -s -o /dev/null -w "Other app on 8000: %{http_code}\n" http://127.0.0.1:8000/
```

What the important parts mean:

* `--bind 127.0.0.1:8010`: AeroDent only listens inside the server; nginx is the only way in.
* `--workers 3`: handles several users at once. Use about `2 × CPU cores + 1` (check cores
  with `nproc`), but not more than your RAM allows (~150 MB per worker).
* `--timeout 300`: gives large backup exports/imports time to finish.
* `--forwarded-allow-ips 127.0.0.1`: trust the "this was HTTPS" header only from nginx on
  the same machine.
* `Restart=always`: if AeroDent ever crashes, systemd restarts it within 5 seconds.

### 7.2 Start it

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aerodent
sudo systemctl status aerodent --no-pager | head -5    # "active (running)"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/     # prints 200
```

If it isn't running, see the logs: `sudo journalctl -u aerodent -n 50 --no-pager`
(section 16 lists common messages).

---

## 8. Get a free address with DuckDNS

DuckDNS gives you a free name like `myclinic.duckdns.org` that always points to your current
public IP.

1. Go to **https://www.duckdns.org** and sign in (GitHub, Google, etc.).
2. Under *domains*, type a name (for example `myclinic`) and click **add domain**.
3. Note the **token** shown at the top of the page (a long code).

Save both on the server (the file is readable only by root):

```bash
sudo tee /etc/aerodent/duckdns.env > /dev/null <<'EOF'
DUCKDNS_DOMAIN=myclinic
DUCKDNS_TOKEN=PASTE-YOUR-TOKEN-HERE
EOF
sudo chmod 600 /etc/aerodent/duckdns.env
sudo nano /etc/aerodent/duckdns.env      # put your real name (without .duckdns.org) and token
```

Keep DuckDNS updated automatically, every 5 minutes:

```bash
sudo tee /etc/systemd/system/duckdns.service > /dev/null <<'EOF'
[Unit]
Description=Update DuckDNS with this server's public IP
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/aerodent/duckdns.env
ExecStart=/usr/bin/curl -fsS --max-time 30 -o /var/log/duckdns.log "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip="
EOF

sudo tee /etc/systemd/system/duckdns.timer > /dev/null <<'EOF'
[Unit]
Description=Update DuckDNS every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now duckdns.timer
sudo systemctl start duckdns.service
cat /var/log/duckdns.log ; echo          # must print: OK
```

Check that the name points to you (it can take a minute):

```bash
getent hosts myclinic.duckdns.org        # shows the same IP as `curl -4 https://ifconfig.me`
```

---

## 9. Open the firewall and your router

### 9.1 Ubuntu firewall (ufw)

Allow SSH first (so you don't lock yourself out), then web traffic, then turn the firewall on:

```bash
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"          # ports 80 and 443
sudo ufw enable                      # answer "y"
sudo ufw status                      # lists OpenSSH and Nginx Full as ALLOW
```

The database (5432) and AeroDent itself (8000) stay closed to the outside. That's intended.

### 9.2 Router port forwarding (home/clinic servers only; skip for a VPS)

1. Find the server's local IP: `hostname -I` (for example `192.168.1.50`).
2. In your router, give the server a **fixed/reserved IP** (DHCP reservation), so it doesn't
   change.
3. Add two **port forwarding** rules to that IP:

| Name | External port | Internal IP | Internal port | Protocol |
|---|---|---|---|---|
| AeroDent HTTP | 80 | 192.168.1.50 | 80 | TCP |
| AeroDent HTTPS | 443 | 192.168.1.50 | 443 | TCP |

Do **not** forward 22 (SSH), 5432 or 8000.

> Many routers can't open their own public address from inside the network ("hairpin NAT").
> If the site works from a phone on mobile data but not from inside the clinic's Wi-Fi, see
> section 16.

---

## 10. nginx + free HTTPS with Let's Encrypt

### 10.1 Configure nginx

Replace `myclinic.duckdns.org` (twice) with your address:

```bash
sudo tee /etc/nginx/sites-available/aerodent > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name myclinic.duckdns.org;

    # Large enough for clinic backup imports (AERODENT_IMPORT_MAX_MB) and big X-rays.
    client_max_body_size 2100m;
    client_body_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        # Overwrite (never append) so visitors cannot fake their IP address.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/aerodent /etc/nginx/sites-enabled/aerodent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t                  # must say "syntax is ok" and "test is successful"
sudo systemctl reload nginx
```

> The `X-Forwarded-For $remote_addr` line matters for security: AeroDent's sign-in protection
> counts failed attempts per IP address, and this line stops attackers from pretending to be
> someone else.

### 10.2 Get the HTTPS certificate

```bash
sudo certbot --nginx -d myclinic.duckdns.org --redirect \
     -m you@example.com --agree-tos --no-eff-email
```

Certbot proves to Let's Encrypt that you control the address (over port 80), installs the
certificate into your nginx file, and adds an automatic HTTP→HTTPS redirect. It ends with
`Congratulations! You have successfully enabled HTTPS`.

Certificates last 90 days and **renew automatically** (Ubuntu installs a `certbot.timer`).
Test the renewal once:

```bash
sudo certbot renew --dry-run          # "Congratulations, all simulated renewals succeeded"
systemctl list-timers | grep certbot  # shows when the next check runs
```

### 10.3 Turn on HTTP/2 (optional, faster)

Open the file and change the `listen 443 ssl;` line(s) Certbot added:

```bash
sudo nano /etc/nginx/sites-available/aerodent
#   listen 443 ssl;          →   listen 443 ssl http2;
#   listen [::]:443 ssl ...; →   listen [::]:443 ssl http2 ...;
sudo nginx -t && sudo systemctl reload nginx
```

> Use `listen 443 ssl http2;`. The newer `http2 on;` directive does **not** exist in the nginx
> version Ubuntu ships (1.24) and makes `nginx -t` fail.

### 10.4 Check it

From any device (a phone on mobile data is a good test), open
**https://myclinic.duckdns.org**. You should see the AeroDent sign-in page with a padlock.

From the server:

```bash
curl -sI https://myclinic.duckdns.org | grep -iE "^HTTP|strict-transport"
#   HTTP/2 200
#   strict-transport-security: max-age=31536000; includeSubDomains
```

---

## 11. First sign-in and creating your first clinic

1. Open `https://myclinic.duckdns.org` and sign in with the **Super Admin** from 6.2.
2. Go to **Clinics & Subscriptions → New Clinic**. Enter the clinic's name, currency, and the **head doctor**'s
   name, e-mail and a temporary password.
3. Sign out. Sign in as the head doctor, go to **Settings**:
   * change the password (Security card),
   * fill in the clinic's details, working hours and appointment length,
   * add doctors and secretaries (Staff card).
4. Add a test patient, book an appointment, upload an X-ray. Everything is saved in the
   PostgreSQL database on your server.

People asking for a trial from the login page are stored in the `trial_requests` table. To see
them:

```bash
sudo -u postgres psql aerodent -c "SELECT created_at, name, phone, email, message FROM trial_requests ORDER BY id DESC LIMIT 20;"
```

**Android app:** build it against your address (HTTPS is required, which you now have):

```bash
cd mobile/android && ./gradlew assembleRelease -PaerodentServerUrl=https://myclinic.duckdns.org
```

See [MOBILE.md](MOBILE.md) for signing and installing.

---

## 12. Automatic daily backups (and how to restore)

Everything (every clinic, patient, X-ray image and setting) is in the PostgreSQL database, so
backing up the database backs up everything.

> Head doctors can also download their own clinic's backup from **Settings → Backup**
> (see [CLINIC_BACKUP.md](CLINIC_BACKUP.md)). The server backup below covers **all** clinics
> and is what you'd use after a disk failure.

### 12.1 The backup script

```bash
sudo tee /usr/local/bin/aerodent-backup > /dev/null <<'EOF'
#!/bin/bash
# Daily AeroDent database backup (all clinics, including X-ray images).
set -euo pipefail
umask 077                                     # backups contain patient data: owner-only
set -a; . /etc/aerodent/aerodent.env; set +a
DEST=/var/backups/aerodent
KEEP_DAYS=14
mkdir -p "$DEST"
STAMP=$(date +%F-%H%M)
pg_dump --format=custom --no-owner --file="$DEST/aerodent-$STAMP.dump" "${DATABASE_URL/+psycopg/}"
find "$DEST" -name 'aerodent-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "Backup written: $DEST/aerodent-$STAMP.dump"
EOF
sudo chmod 700 /usr/local/bin/aerodent-backup
sudo aerodent-backup
sudo ls -lh /var/backups/aerodent/
```

### 12.2 Run it every night

```bash
sudo tee /etc/systemd/system/aerodent-backup.service > /dev/null <<'EOF'
[Unit]
Description=AeroDent database backup
After=postgresql.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/aerodent-backup
EOF

sudo tee /etc/systemd/system/aerodent-backup.timer > /dev/null <<'EOF'
[Unit]
Description=Daily AeroDent database backup

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now aerodent-backup.timer
systemctl list-timers | grep aerodent-backup
```

`Persistent=true` means that if the server was off at 02:30, the backup runs when it starts.

### 12.3 Keep a copy somewhere else (strongly recommended, still free)

A backup on the same disk doesn't survive that disk dying. A free option is Google Drive (15 GB
free) with **rclone**, **encrypted** so Google cannot read patient data:

```bash
sudo apt install -y rclone
sudo rclone config
```

In the interactive menu:

1. `n` (new remote) → name `gdrive` → storage type **drive** (Google Drive) → leave
   client id/secret empty → scope `1` (full access) → accept the defaults → when asked
   "Use web browser to automatically authenticate", answer `n` on a server without a screen
   and follow the instructions (run the shown `rclone authorize` command on your own
   computer).
2. `n` again → name `gdrive-crypt` → type **crypt** → remote `gdrive:aerodent-backups` →
   filename encryption `standard` → choose a **strong password** and a second one (salt).
   **Write both passwords down offline: without them the copies can never be decrypted.**
3. `q` to quit.

Then add one line to the end of `/usr/local/bin/aerodent-backup`:

```bash
sudo nano /usr/local/bin/aerodent-backup
# add as the last line:
rclone copy "$DEST" gdrive-crypt: --max-age 3d
```

Run `sudo aerodent-backup` once and check your Google Drive: an `aerodent-backups` folder with
unreadable (encrypted) file names should appear.

### 12.4 Restoring from a backup

**Practise this once**, so you know it works before you need it. (Backups are readable only by
root, which is why the file is passed in with `sudo cat … |`.)

Restore into a scratch database to check a backup (safe, doesn't touch the live site):

```bash
BACKUP=/var/backups/aerodent/aerodent-YYYY-MM-DD-HHMM.dump     # ← pick one from: sudo ls /var/backups/aerodent
sudo -u postgres createdb -O aerodent aerodent_check
sudo cat "$BACKUP" | sudo -u postgres pg_restore --no-owner --role=aerodent -d aerodent_check
sudo -u postgres psql aerodent_check -c "SELECT count(*) AS patients FROM patients;"
sudo -u postgres dropdb aerodent_check
```

Real restore (replaces **all** current data with the backup):

```bash
BACKUP=/var/backups/aerodent/aerodent-YYYY-MM-DD-HHMM.dump
sudo systemctl stop aerodent
sudo -u postgres dropdb aerodent
sudo -u postgres createdb -O aerodent aerodent
sudo cat "$BACKUP" | sudo -u postgres pg_restore --no-owner --role=aerodent -d aerodent
sudo aerodent-flask db upgrade          # in case the code is newer than the backup
sudo systemctl start aerodent
```

**Moving to a new server:** follow sections 2–7 on the new machine, copy a `.dump` file over
(`scp`; put it in `/var/backups/aerodent/` on the new server), do the "real restore" above, then sections 8–10 (point DuckDNS at the new server).
Copy `/etc/aerodent/aerodent.env` too, or at least reuse the same `SECRET_KEY`, so it continues
where the old server left off.

---

## 13. Updating AeroDent

When a new version is pushed to GitHub:

```bash
sudo aerodent-backup                                               # 1. safety backup first
sudo -u aerodent git -C /opt/aerodent/app pull                     # 2. get the new code
sudo -u aerodent /opt/aerodent/venv/bin/pip install -r /opt/aerodent/app/requirements.txt gunicorn   # 3. new packages
sudo aerodent-flask db upgrade                                     # 4. database changes
sudo systemctl restart aerodent                                    # 5. restart
sudo systemctl status aerodent --no-pager | head -5
```

Browsers pick up the new version automatically: file names change with every release, so
nobody needs to clear their cache.

To undo an update, go back to the previous version with
`sudo -u aerodent git -C /opt/aerodent/app checkout <previous-commit>`, restore the backup from
step 1 if the database changed (12.4), then restart.

---

## 14. Security checklist

AeroDent already does the heavy lifting: HTTPS-only secure cookies, server-side sessions with
timeouts, sign-in brute-force protection, strict security headers, per-clinic data isolation,
and an activity log. Make sure the server side is tight too:

- [ ] `AERODENT_ENV=production` and a random 64-character `SECRET_KEY` (section 5).
- [ ] `/etc/aerodent/aerodent.env` is `640 root:aerodent` (`ls -l /etc/aerodent`).
- [ ] PostgreSQL listens on `127.0.0.1` only (3.2); ports 5432 and 8000 are **not** forwarded.
- [ ] `sudo ufw status` shows only OpenSSH and Nginx Full.
- [ ] `seed.py` was **not** run; no `@aerodent.local` demo accounts exist:
      `sudo -u postgres psql aerodent -c "SELECT email FROM users WHERE email LIKE '%@aerodent.local';"` → 0 rows.
- [ ] Automatic security updates are on (2.4).
- [ ] Daily backups run and an **encrypted off-site copy** exists (12); you tested a restore.
- [ ] SSH: use key-based login and disable password login. After adding your key with
      `ssh-copy-id`, set `PasswordAuthentication no` in `/etc/ssh/sshd_config` and run
      `sudo systemctl restart ssh`. Optionally `sudo apt install fail2ban`.
- [ ] Only the Super Admin creates clinics; `AERODENT_ALLOW_SELF_REGISTRATION` stays `false`.
- [ ] Staff use strong, unique passwords. Head doctors can see and sign out other devices in
      *Settings → Active sessions*.

---

## 15. Alternative: no public IP? Use Tailscale Funnel

If your ISP uses CGNAT or blocks ports 80/443 (section 1), **Tailscale Funnel** (free for
personal use) gives your server a public HTTPS address like
`https://myserver.tail1234.ts.net` without opening any router ports. HTTPS certificates are
automatic.

Do sections **2–7** first. Then, **instead of sections 8–10**:

### 15.1 Install Tailscale and enable Funnel

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up            # open the printed link and sign in (free account)
```

In the Tailscale admin console (https://login.tailscale.com/admin):

1. **DNS** tab: make sure **MagicDNS** is enabled, and enable **HTTPS Certificates**.
2. Funnel must be allowed for this machine. The first time you run the command in 15.3,
   Tailscale prints a link to enable it; open it and confirm.

Find your public name:

```bash
tailscale status --json | grep -m1 '"DNSName"'     # e.g. "myserver.tail1234.ts.net."
```

(Use it without the final dot.)

### 15.2 nginx for Funnel

Tailscale handles HTTPS; nginx listens only locally. Replace `myserver.tail1234.ts.net`
(twice) with your name:

```bash
sudo tee /etc/nginx/sites-available/aerodent > /dev/null <<'EOF'
server {
    listen 127.0.0.1:8080;
    server_name myserver.tail1234.ts.net;

    client_max_body_size 2100m;
    client_body_timeout 300s;

    # Tailscale Funnel connects from this machine and passes the visitor's address along.
    set_real_ip_from 127.0.0.1;
    real_ip_header X-Forwarded-For;

    location / {
        proxy_pass http://127.0.0.1:8000;
        # The public name, so AeroDent's cross-site-request protection matches the browser.
        proxy_set_header Host myserver.tail1234.ts.net;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/aerodent /etc/nginx/sites-enabled/aerodent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 15.3 Publish it

```bash
sudo tailscale funnel --bg 8080
tailscale funnel status          # shows https://myserver.tail1234.ts.net → http://127.0.0.1:8080
```

The `--bg` setting survives reboots. Open `https://myserver.tail1234.ts.net` from a phone on
mobile data. Then continue with sections **11–14** (skip the DuckDNS/Let's Encrypt/router
items in the checklist; keep `sudo ufw allow OpenSSH && sudo ufw enable`. No web ports need
opening).

### 15.4 Two checks specific to Funnel

1. **Actions work.** Sign in, then save something (e.g. add a patient). If every save fails
   with a "forbidden"/403 error, the name in the two nginx lines doesn't exactly match the
   address in your browser's address bar. Fix it and `sudo systemctl reload nginx`.
2. **Real visitor IPs.** Sign in once from your phone on mobile data, then:
   ```bash
   sudo -u postgres psql aerodent -c "SELECT created_at, action, ip_address FROM audit_logs ORDER BY id DESC LIMIT 5;"
   ```
   You should see your phone's public IP. If every row shows `127.0.0.1`, your Tailscale
   version isn't passing the visitor's address. Everything still works, but sign-in protection
   then counts everyone as one visitor, so many failed sign-ins from anyone can briefly delay
   sign-ins for others. Update Tailscale (`sudo apt update && sudo apt install tailscale`) and
   check again.

> **If you ever buy a domain** (from about $10/year): **Cloudflare Tunnel** is another good
> no-open-ports option. Otherwise, the main path (sections 8–10) works with any domain in place
> of DuckDNS.

---

## 16. Troubleshooting

**Where to look first:**

```bash
sudo journalctl -u aerodent -n 100 --no-pager      # AeroDent (Python) messages
sudo tail -n 50 /var/log/nginx/error.log           # nginx problems
sudo systemctl status aerodent nginx postgresql --no-pager
```

| Symptom | Cause and fix |
|---|---|
| `aerodent` service keeps restarting; log says `DATABASE_URL is not configured` | The settings file isn't read. Check `EnvironmentFile=/etc/aerodent/aerodent.env` in the service and the file's permissions (`640 root:aerodent`). Then `sudo systemctl daemon-reload && sudo systemctl restart aerodent`. |
| Log says `SECRET_KEY is required` / `must be at least 32 characters` | Put the 64-character value from `openssl rand -hex 32` in `SECRET_KEY`. |
| Log says `password authentication failed for user "aerodent"` | The password in `DATABASE_URL` doesn't match section 3.1. Reset it: `sudo -u postgres psql -c "ALTER ROLE aerodent PASSWORD 'NEWPASS';"` (letters/digits only) and update the file. |
| Log says `relation "users" does not exist` | Tables weren't created: `sudo aerodent-flask db upgrade`. |
| `nginx -t` says `socket() [::]:80 failed (97: Address family not supported by protocol)` | IPv6 is disabled on this server. Delete the `listen [::]:80;` line (and any `listen [::]:443 …` line) from `/etc/nginx/sites-available/aerodent`, then `sudo nginx -t`. |
| Browser shows **502 Bad Gateway** | nginx is fine but AeroDent isn't running. See the first rows of this table; `curl http://127.0.0.1:8000/` on the server must print HTML. |
| Sign-in "does nothing" / you're sent back to the sign-in page | You're using `http://` or the IP address. In production the sign-in cookie only works over **https://your-address**. |
| Signed in, but **every save fails with 403 / "forbidden"** | The `Host` or `X-Forwarded-Proto` lines are missing from the nginx `location /` block, or `--forwarded-allow-ips 127.0.0.1` is missing from the service. Compare with sections 7.1 and 10.1 (or 15.2). |
| **413 Request Entity Too Large** on X-ray upload or backup import | Raise `client_max_body_size` in nginx (and `AERODENT_XRAY_MAX_MB` / `AERODENT_IMPORT_MAX_MB` in the settings file), then reload nginx and restart aerodent. |
| **504 Gateway Timeout** on very large backup exports | Raise `proxy_read_timeout` (nginx) and `--timeout` (service) to e.g. `900`. |
| Certbot: `Timeout during connect (likely firewall problem)` | Port 80 isn't reachable from the internet: check the router forwarding (9.2) and `ufw status`. Some ISPs block port 80; then use section 15. |
| Certbot: `NXDOMAIN` / DNS problem | DuckDNS doesn't point to you yet: `cat /var/log/duckdns.log` must say `OK`; `getent hosts myclinic.duckdns.org` must show your public IP. |
| Works on mobile data but **not inside the clinic's Wi-Fi** | The router doesn't support hairpin NAT. Either enable "NAT loopback" in the router, or make the name resolve to the server's LAN IP inside the network (router "local DNS"/"static DNS" entry `myclinic.duckdns.org → 192.168.1.50`). |
| The site worked, then stopped after a few days (home internet) | Your public IP changed and DuckDNS didn't update: `systemctl list-timers \| grep duckdns` must show the timer; check `/var/log/duckdns.log`. |
| Dates on the agenda/dashboard are off by a day near midnight | The server's time zone isn't the clinic's (section 2.3). |
| Backup timer ran but no file | `sudo systemctl status aerodent-backup.service` shows the error; run `sudo aerodent-backup` by hand to see it. |

---

## 17. Command cheat sheet

```bash
# Status / logs
sudo systemctl status aerodent
sudo journalctl -u aerodent -f                 # live log (Ctrl+C to stop)

# Restart after changing settings
sudo systemctl restart aerodent
sudo nginx -t && sudo systemctl reload nginx

# Accounts
sudo aerodent-flask admin create-super-admin
sudo aerodent-flask admin reset-password --email someone@example.com

# Database
sudo aerodent-flask db upgrade
sudo aerodent-flask db current
sudo -u postgres psql aerodent                 # SQL console (\q to quit)

# X-ray integrity check (all images, all clinics)
sudo aerodent-flask xrays verify

# Backups
sudo aerodent-backup                           # back up now
sudo ls -lh /var/backups/aerodent/
systemctl list-timers | grep -E "aerodent|duckdns|certbot"

# HTTPS certificate
sudo certbot certificates
sudo certbot renew --dry-run
```
