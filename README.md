# Calibre AI Tagger

AI-powered book library management system using Claude Haiku for intelligent tagging, with Calibre-Web for a clean browsing interface.

## Architecture

```
Mac (local)                          VPS (remote)
┌──────────────────┐                ┌──────────────────────────┐
│  Calibre App     │   syncbooks    │  Calibre-Web             │
│  + AI Tagger     │ ──────────────>│  (browser interface)     │
│  + Tag Cleanup   │                │  https://kirillbooks.    │
│                  │                │    duckdns.org           │
│  ~/Desktop/      │                │                          │
│  Calibre Library │                │  ~/calibre-library/      │
└──────────────────┘                │  Calibre Library/        │
   Master copy                      │                          │
   (add/tag here)                   │  Nginx reverse proxy     │
                                    │  + Let's Encrypt SSL     │
                                    └──────────────────────────┘
                                       Synced copy
                                       (browse/read here)
```

- **Mac** = master library. Add books, fetch metadata, run AI tagger here.
- **VPS** = always-on Calibre-Web. Browse, search, and read from anywhere.

## Live Library

- **URL:** https://kirillbooks.duckdns.org
- **OPDS Feed:** https://kirillbooks.duckdns.org/opds

## Setup

### Prerequisites

- Python 3.10+
- Anthropic API key
- Calibre installed on Mac
- Ubuntu VPS with Calibre-Web

### Mac Setup

```bash
git clone https://github.com/kkpodtechideas-wq/Caliber-AI-tagger.git ~/calibre-tagger
cd ~/calibre-tagger
python3 -m venv venv
source venv/bin/activate
pip install anthropic
export ANTHROPIC_API_KEY='your-key-here'
```

### Shell Aliases (add to ~/.zshrc)

```bash
alias tagbooks="cd ~/calibre-tagger && source venv/bin/activate && python tagger.py"
alias syncbooks='rsync -avz --progress ~/Desktop/"Calibre Library"/ kirill@77.42.19.116:~/calibre-library/"Calibre Library"/'
```

After adding books: `tagbooks && syncbooks`

### VPS Setup

```bash
pip3 install calibreweb --break-system-packages
pip3 install anthropic --break-system-packages

sudo bash -c 'cat > /etc/systemd/system/calibre-web.service << EOF
[Unit]
Description=Calibre-Web
After=network.target
[Service]
User=kirill
ExecStart=/home/kirill/.local/bin/cps
WorkingDirectory=/home/kirill
Restart=always
[Install]
WantedBy=multi-user.target
EOF'

sudo systemctl enable calibre-web
sudo systemctl start calibre-web
```

Calibre-Web listens on `127.0.0.1:8083` (proxied through Nginx).
Database path: `/home/kirill/calibre-library/Calibre Library`

### Nginx + HTTPS Setup

Domain: `kirillbooks.duckdns.org` (free subdomain via DuckDNS, pointed at VPS IP)

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
```

Nginx config at `/etc/nginx/sites-available/calibre-web`:

```nginx
server {
    listen 80;
    server_name kirillbooks.duckdns.org;
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

SSL via Let's Encrypt:

```bash
sudo ln -s /etc/nginx/sites-available/calibre-web /etc/nginx/sites-enabled/
sudo certbot --nginx -d kirillbooks.duckdns.org
```

Certificate auto-renews every 90 days.

## Daily Workflows

### Adding New Books

1. Open Calibre on Mac, drag in new books
2. Right-click > Edit metadata > Download metadata and covers
3. Close Calibre
4. Run AI tagger: `tagbooks`
5. Sync to VPS: `syncbooks`

### Tag Cleanup (when needed)

```bash
ssh kirill@77.42.19.116
sudo systemctl stop calibre-web
export ANTHROPIC_API_KEY='your-key-here'
python3 ~/cleanup.py
sudo systemctl start calibre-web
```

## Tag Structure

| Prefix | Description | Examples |
|--------|-------------|---------|
| genre: | Book category | genre:philosophy, genre:business |
| theme: | Concepts explored | theme:power, theme:consciousness |
| topic: | Specific subjects | topic:options trading |
| mood: | Reading feel | mood:academic, mood:practical |
| level: | Difficulty | level:introductory, level:advanced |
| biography: | Who bio is about | biography:Steve Jobs |
| person: | People discussed | person:Warren Buffett |
| era: | Time period | era:19th century |
| language: | If non-English | language:Russian |

## Customizing Tags

Edit `tagger.py` > `TAGGING_PROMPT` to modify categories.

To add a new category:
1. Add to JSON format in the prompt
2. Add to `format_tags_for_calibre()` function
3. Update `cleanup.py` allowed lists if needed

## Force Re-Tagging

In `tagger.py`, change:
```python
has_ai_tags = any(":" in tag for tag in existing)
if not has_ai_tags:
```
to:
```python
if True:  # Force re-tag all
```

## UI Customizations

The dark theme (caliBlur) has several CSS overrides applied in:
`/home/kirill/.local/lib/python3.13/site-packages/calibreweb/cps/static/css/caliBlur_override.css`

Current customizations:
- **"You Might Enjoy"** random book recommendations on homepage (replaces hidden "Discover" section)
- **Hidden redundant "Books" header** from main content area
- Georgia serif heading style for the recommendation section

Template change in `index.html`:
- Heading changed from "Discover (Random Books)" to "You Might Enjoy"

Note: These customizations live on the VPS and will need to be reapplied if Calibre-Web is upgraded. Backup files:
- `caliBlur_override.css` — see `vps-customizations/` folder in this repo

## Connecting Devices

### iPhone (Safari)
1. Open https://kirillbooks.duckdns.org in Safari
2. Tap Share > Add to Home Screen
3. Name it "Library"

### iPhone (OPDS reader app — better for reading)
1. Download KyBook 3 from App Store
2. Add OPDS catalog: `https://kirillbooks.duckdns.org/opds`
3. Enter your login credentials

### Kindle
Set up email delivery in Admin > Edit Email Server Settings, then use "Send to Kindle" button on each book.

## User Management

Add users in Admin > Add New User. Recommended permissions for regular users:
- ✅ Download, View Books, Password (change own)
- ☐ Admin, Upload, Edit, Delete, Public Shelf

Users cannot see other users or admin settings. Reading progress, shelves, and bookmarks are private per user.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError: anthropic | `pip install anthropic` |
| Model not found | Check model string in tagger.py |
| Database not found | Check CALIBRE_LIBRARY path |
| Database is locked | Close Calibre first |
| Calibre-Web 500 error | Add missing columns (see below) |
| SSL cert expired | `sudo certbot renew` |

Fix missing DB columns:
```bash
sqlite3 ~/calibre-library/"Calibre Library"/metadata.db "ALTER TABLE books ADD COLUMN isbn TEXT DEFAULT '';"
sqlite3 ~/calibre-library/"Calibre Library"/metadata.db "ALTER TABLE books ADD COLUMN flags INTEGER DEFAULT 1;"
sudo systemctl restart calibre-web
```

VPS service management:
```bash
sudo systemctl start calibre-web
sudo systemctl stop calibre-web
sudo systemctl restart calibre-web
sudo systemctl status calibre-web
journalctl -u calibre-web -f
```

## Costs

- AI Tagger: ~$0.003/book (~$2.50 for 850 books)
- Tag Cleanup: ~$0.10-0.20 per run
- Domain: Free (DuckDNS)
- SSL: Free (Let's Encrypt)
