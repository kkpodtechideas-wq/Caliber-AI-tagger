#!/usr/bin/env python3
"""
Add synonym Russian tags to Calibre library.
Uses partial matching to find tags containing synonyms.
"""

import sqlite3
from pathlib import Path

CALIBRE_LIBRARY = Path.home() / "Desktop" / "Calibre Library"

# Keywords to match (case-insensitive, partial match)
# Format: if tag contains any word in group, add tags for ALL words in group
SYNONYMS = [
    # Renaissance - match any form
    ["ренессанс", "возрождение", "возрождения"],
    # Medieval
    ["средневековье", "средневековья", "средние века"],
    # Antiquity
    ["античность", "античности", "древность", "древний мир"],
]

def fix_tags():
    db_path = CALIBRE_LIBRARY / "metadata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all Russian tags
    cursor.execute("SELECT id, name FROM tags")
    all_tags = cursor.fetchall()
    
    added = 0
    
    for synonym_group in SYNONYMS:
        # Find books that have ANY tag containing ANY word from this group
        books_with_tags = {}  # book_id -> set of prefixes
        
        for tag_id, tag_name in all_tags:
            if ":" not in tag_name:
                continue
            
            tag_lower = tag_name.lower()
            
            for keyword in synonym_group:
                if keyword in tag_lower:
                    prefix = tag_name.split(":")[0]
                    
                    cursor.execute("SELECT book FROM books_tags_link WHERE tag = ?", (tag_id,))
                    for (book_id,) in cursor.fetchall():
                        if book_id not in books_with_tags:
                            books_with_tags[book_id] = set()
                        books_with_tags[book_id].add(prefix)
                    break
        
        # For each book found, add simple synonym tags
        for book_id, prefixes in books_with_tags.items():
            for prefix in prefixes:
                for keyword in synonym_group:
                    new_tag = f"{prefix}:{keyword}"
                    
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (new_tag,))
                    row = cursor.fetchone()
                    if row:
                        syn_tag_id = row[0]
                    else:
                        cursor.execute("INSERT INTO tags (name) VALUES (?)", (new_tag,))
                        syn_tag_id = cursor.lastrowid
                    
                    cursor.execute(
                        "INSERT OR IGNORE INTO books_tags_link (book, tag) VALUES (?, ?)",
                        (book_id, syn_tag_id)
                    )
                    if cursor.rowcount > 0:
                        added += 1
                        print(f"  Added '{new_tag}' to book {book_id}")
    
    conn.commit()
    conn.close()
    print(f"\n✓ Added {added} synonym tag links")

if __name__ == "__main__":
    print("Adding Russian synonym tags...\n")
    fix_tags()
    print("\nDone! Run 'syncbooks' to push changes to VPS.")
