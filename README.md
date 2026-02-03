# Calibre AI Tagger

AI-powered book library management system using Claude Haiku for intelligent tagging, with Calibre-Web for a clean browsing interface.

## Architecture
```
Mac (local)                          VPS (remote)
┌──────────────────┐                ┌──────────────────────────┐
│  Calibre App     │   syncbooks    │  Calibre-Web             │
│  + AI Tagger     │ ──────────────>│  (browser interface)     │
│  + Tag Cleanup   │                │  http://YOUR_IP:8083     │
│                  │                │                          │
│  ~/Desktop/      │                │  ~/calibre-library/      │
│  Calibre Library │                │  Calibre Library/        │
└──────────────────┘                └──────────────────────────┘
   Master copy                         Synced copy
   (add/tag here)                      (browse/read here)
```

- **Mac** = master library. Add books, fetch metadata, run AI tagger here.
- **VPS** = always-on Calibre-Web. Browse, search, and read from anywhere.

## Setup

### Prerequisites

- Python 3.10+
- Anthropic API key
- Calibre installed on Mac
- Ubuntu VPS with Calibre-Web

### Mac Setup
```bash
git clone https://github.com/YOUR_USERNAME/calibre-ai-tagger.git ~/calibre-tagger
cd ~/calibre-tagger
python3 -m venv venv
source venv/bin/activate
pip install anthropic
export ANTHROPIC_API_KEY='your-key-here'
```

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
sudo ufw allow 8083
```

Calibre-Web: http://YOUR_VPS_IP:8083
Database path: /home/kirill/calibre-library/Calibre Library
Default login: admin / admin123 (change immediately)

## Daily Workflows

### Adding New Books

1. Open Calibre on Mac, drag in new books
2. Right-click > Edit metadata > Download metadata and covers
3. Close Calibre
4. Run AI tagger: `tagbooks`
5. Sync to VPS: `syncbooks`

### Shell Aliases (add to ~/.zshrc)
```bash
alias tagbooks="cd ~/calibre-tagger && source venv/bin/activate && python tagger.py"
alias syncbooks='rsync -avz --progress ~/Desktop/"Calibre Library"/ kirill@YOUR_VPS_IP:~/calibre-library/"Calibre Library"/'
```

After adding books: `tagbooks && syncbooks`

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

## Tag Cleanup

When tags get messy, run cleanup on VPS:
```bash
sudo systemctl stop calibre-web
export ANTHROPIC_API_KEY='your-key-here'
python3 ~/cleanup.py
sudo systemctl start calibre-web
```

## Customizing Tags

Edit tagger.py > TAGGING_PROMPT to modify categories.

To add a new category:
1. Add to JSON format in the prompt
2. Add to format_tags_for_calibre() function
3. Update cleanup.py allowed lists if needed

## Force Re-Tagging

In tagger.py, change:
```python
has_ai_tags = any(":" in tag for tag in existing)
if not has_ai_tags:
```
to:
```python
if True:  # Force re-tag all
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError: anthropic | pip install anthropic |
| Model not found | Check model string in tagger.py |
| Database not found | Check CALIBRE_LIBRARY path |
| Database is locked | Close Calibre first |
| Calibre-Web 500 error | Add missing columns (see below) |
| Can't connect to Calibre-Web | sudo ufw allow 8083 |

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
