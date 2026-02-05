#!/usr/bin/env python3
"""
Calibre Tag Translator - Adds Russian translations of existing English tags.
Keeps both English and Russian versions so users can search in either language.

Usage:
    sudo systemctl stop calibre-web
    export ANTHROPIC_API_KEY='your-key'
    python3 translate_tags.py
    sudo systemctl start calibre-web
"""

import sqlite3
import json
import os
import sys
import time
from anthropic import Anthropic

# ── Config ───────────────────────────────────────────────────────────────────
CALIBRE_DB = os.path.expanduser("~/calibre-library/Calibre Library/metadata.db")
MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 40  # tags per API call
DELAY = 0.5

# Prefix translations
PREFIX_MAP = {
    "genre": "жанр",
    "theme": "тема",
    "topic": "тема",  # same as theme in Russian, keeps it natural
    "mood": "настроение",
    "level": "уровень",
    "biography": "биография",
    "person": "персона",
    "era": "эпоха",
    "language": "язык",
}

TRANSLATION_PROMPT = """You are a professional English-to-Russian translator. 
Translate the following book tags from English to Russian. 
These are tags used to categorize books in a library.

Rules:
- Translate naturally, not literally. Use how a Russian reader would actually describe the concept.
- For people's names: transliterate to standard Russian spelling (e.g., "Warren Buffett" → "Уоррен Баффетт", "Carl Jung" → "Карл Юнг")
- For well-known concepts, use the standard Russian term (e.g., "stoicism" → "стоицизм", "existentialism" → "экзистенциализм")
- Keep it concise - tags should be short
- Return ONLY a JSON object mapping each English tag value to its Russian translation
- Do NOT include the prefix (genre:, theme:, etc.) - just translate the value part

Tags to translate:
{tags}

Return format (JSON only, no markdown, no backticks):
{{"english_value": "russian_value", "english_value2": "russian_value2"}}
"""


def get_all_ai_tags(db_path):
    """Get all tags that have a colon prefix (AI-generated tags)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM tags WHERE name LIKE '%:%'")
    tags = cursor.fetchall()
    conn.close()
    return tags


def get_existing_russian_tags(db_path):
    """Get all tags that already have Russian characters."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM tags")
    all_tags = cursor.fetchall()
    conn.close()
    # Filter for tags containing Cyrillic characters
    russian_tags = set()
    for (name,) in all_tags:
        if any('\u0400' <= c <= '\u04FF' for c in name):
            russian_tags.add(name)
    return russian_tags


def get_books_with_tag(db_path, tag_id):
    """Get all book IDs that have a specific tag."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT book FROM books_tags_link WHERE tag = ?", (tag_id,))
    books = [row[0] for row in cursor.fetchall()]
    conn.close()
    return books


def get_or_create_tag(db_path, tag_name):
    """Get existing tag ID or create new tag, return tag ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]
    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    tag_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tag_id


def link_book_to_tag(db_path, book_id, tag_id):
    """Link a book to a tag if not already linked."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM books_tags_link WHERE book = ? AND tag = ?",
        (book_id, tag_id)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO books_tags_link (book, tag) VALUES (?, ?)",
            (book_id, tag_id)
        )
        conn.commit()
    conn.close()


def translate_batch(client, tag_values):
    """Send a batch of tag values to Claude for translation."""
    tags_str = json.dumps(tag_values, ensure_ascii=False)
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": TRANSLATION_PROMPT.format(tags=tags_str)
        }]
    )
    text = response.content[0].text.strip()
    # Clean up potential markdown formatting
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def main():
    if not os.path.exists(CALIBRE_DB):
        print(f"Database not found: {CALIBRE_DB}")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # Get all AI tags
    all_tags = get_all_ai_tags(CALIBRE_DB)
    print(f"Found {len(all_tags)} AI-generated tags")

    # Get existing Russian tags to skip
    existing_russian = get_existing_russian_tags(CALIBRE_DB)
    print(f"Found {len(existing_russian)} existing Russian tags")

    # Parse tags into prefix:value pairs
    tags_to_translate = {}  # {tag_id: (prefix, value, full_name)}
    for tag_id, tag_name in all_tags:
        if ":" not in tag_name:
            continue
        prefix, value = tag_name.split(":", 1)
        prefix = prefix.strip().lower()
        value = value.strip()

        if prefix not in PREFIX_MAP:
            continue

        # Check if Russian version already exists
        russian_prefix = PREFIX_MAP[prefix]
        # We'll check after translation
        tags_to_translate[tag_id] = (prefix, value, tag_name)

    print(f"Tags to process: {len(tags_to_translate)}")

    # Group unique values for translation (avoid translating duplicates)
    unique_values = list(set(v for _, (_, v, _) in tags_to_translate.items()))
    print(f"Unique values to translate: {len(unique_values)}")

    # Translate in batches
    translations = {}
    for i in range(0, len(unique_values), BATCH_SIZE):
        batch = unique_values[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(unique_values) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"\nTranslating batch {batch_num}/{total_batches} ({len(batch)} tags)...")

        try:
            result = translate_batch(client, batch)
            translations.update(result)
            print(f"  ✓ Got {len(result)} translations")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            # Try one by one for failed batch
            for val in batch:
                try:
                    result = translate_batch(client, [val])
                    translations.update(result)
                except Exception as e2:
                    print(f"    Skipping '{val}': {e2}")

        time.sleep(DELAY)

    print(f"\nTotal translations: {len(translations)}")

    # Apply translations to books
    added_count = 0
    skipped_count = 0

    for tag_id, (prefix, value, full_name) in tags_to_translate.items():
        russian_prefix = PREFIX_MAP[prefix]

        if value not in translations:
            print(f"  No translation for: {value}")
            continue

        russian_value = translations[value]
        russian_tag_name = f"{russian_prefix}:{russian_value}"

        # Skip if this Russian tag already exists in the library
        if russian_tag_name in existing_russian:
            skipped_count += 1
            continue

        # Get books that have the English tag
        book_ids = get_books_with_tag(CALIBRE_DB, tag_id)
        if not book_ids:
            continue

        # Create Russian tag and link to same books
        russian_tag_id = get_or_create_tag(CALIBRE_DB, russian_tag_name)

        for book_id in book_ids:
            link_book_to_tag(CALIBRE_DB, book_id, russian_tag_id)

        added_count += 1
        print(f"  {full_name} → {russian_tag_name} ({len(book_ids)} books)")

    print(f"\n{'='*50}")
    print(f"Done!")
    print(f"  New Russian tags added: {added_count}")
    print(f"  Already existed (skipped): {skipped_count}")
    print(f"\nRestart Calibre-Web: sudo systemctl restart calibre-web")


if __name__ == "__main__":
    main()
