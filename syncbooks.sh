#!/bin/bash
echo "=== Syncing Calibre Library to VPS ==="
rsync -avz --progress ~/Desktop/"Calibre Library"/ kirill@77.42.19.116:~/calibre-library/"Calibre Library"/
echo "=== Patching database & restarting Calibre-Web ==="
ssh -t kirill@77.42.19.116 'sudo systemctl stop calibre-web; sqlite3 ~/calibre-library/"Calibre Library"/metadata.db "ALTER TABLE books ADD COLUMN isbn TEXT DEFAULT \"\";" 2>/dev/null; sqlite3 ~/calibre-library/"Calibre Library"/metadata.db "ALTER TABLE books ADD COLUMN flags INTEGER DEFAULT 1;" 2>/dev/null; sudo systemctl start calibre-web'
echo "=== Done! ==="
