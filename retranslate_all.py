#!/usr/bin/env python3
"""
Re-translate all English tags to Russian with multiple synonyms.
Case-insensitive matching.
"""

import os
import sqlite3
import json
import time
from pathlib import Path
from anthropic import Anthropic

CALIBRE_LIBRARY = os.path.expanduser("~/Desktop/Calibre Library")
MODEL = "claude-haiku-4-5-20251001"
DELAY_BETWEEN_CALLS = 0.5
BATCH_SIZE = 40

client = Anthropic()

PREFIX_MAP = {
    "genre": "жанр",
    "theme": "тема",
    "topic": "тема",
    "mood": "настроение",
    "level": "уровень",
    "biography": "биография",
    "person": "персона",
    "era": "эпоха",
    "language": "язык",
}

TRANSLATION_PROMPT = """You are a professional English-to-Russian translator for a book library search system.

For each English tag, provide 2-4 Russian search terms a user might type to find it.

Rules:
- Include the main translation plus common synonyms
- Include different grammatical cases (nominative, genitive) if commonly searched
- Include both formal and colloquial forms where relevant
- For people's names: just one standard transliteration
- Keep each term short (1-3 words max)
- Make all terms LOWERCASE

Tags to translate:
{tags}

Return JSON mapping each English tag to an ARRAY of lowercase Russian search terms:
{{"Renaissance": ["ренессанс", "возрождение", "эпоха возрождения"], "psychology": ["психология", "психологии", "псих"], "Warren Buffett": ["уоррен баффетт"]}}
"""


def get_db_connection():
    return sqlite3.connect(Path(CALIBRE_LIBRARY) / "metadata.db")


def translate_batch(tag_values):
    tags_str = json.dumps(tag_values, ensure_ascii=False)
    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": TRANSLATION_PROMPT.format(tags=tags_str)}]
    )
    text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def main():
    print("=" * 60)
    print("RE-TRANSLATE ALL TAGS WITH SYNONYMS")
    print("=" * 60)
    print("\n⚠️  Make sure Calibre is CLOSED!\n")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all English tags with prefixes and their book links
    cursor.execute("""
        SELECT t.id, t.name, btl.book 
        FROM tags t 
        JOIN books_tags_link btl ON t.id = btl.tag
        WHERE t.name LIKE '%:%' 
        AND t.name NOT GLOB '*[А-Яа-яЁё]*'
    """)
    rows = cursor.fetchall()

    # Build mapping: english_value -> [(book_id, prefix), ...]
    value_to_books = {}
    for tag_id, tag_name, book_id in rows:
        if ":" not in tag_name:
            continue
        prefix, value = tag_name.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix not in PREFIX_MAP:
            continue
        value = value.strip()
        if value not in value_to_books:
            value_to_books[value] = []
        value_to_books[value].append((book_id, prefix))

    unique_values = list(value_to_books.keys())
    print(f"Found {len(unique_values)} unique English tag values to translate")

    if not unique_values:
        print("Nothing to translate!")
        return

    estimated_cost = (len(unique_values) / BATCH_SIZE) * 0.003
    print(f"Estimated API cost: ${estimated_cost:.2f}")
    response = input("Proceed? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return

    # Translate in batches
    translations = {}
    for i in range(0, len(unique_values), BATCH_SIZE):
        batch = unique_values[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(unique_values) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Translating batch {batch_num}/{total_batches}...")
        try:
            result = translate_batch(batch)
            translations.update(result)
        except Exception as e:
            print(f"  Batch error: {e}, trying one-by-one...")
            for val in batch:
                try:
                    result = translate_batch([val])
                    translations.update(result)
                except Exception as e2:
                    print(f"    Skipping '{val}': {e2}")
        time.sleep(DELAY_BETWEEN_CALLS)

    print(f"\nGot translations for {len(translations)} values")
    print("Adding Russian synonym tags to database...")

    added = 0
    for english_value, book_prefix_list in value_to_books.items():
        if english_value not in translations:
            continue

        russian_values = translations[english_value]
        if isinstance(russian_values, str):
            russian_values = [russian_values]

        for book_id, english_prefix in book_prefix_list:
            russian_prefix = PREFIX_MAP[english_prefix]

            for russian_value in russian_values:
                # Ensure lowercase
                russian_value = russian_value.lower().strip()
                russian_tag = f"{russian_prefix}:{russian_value}"

                cursor.execute("SELECT id FROM tags WHERE LOWER(name) = LOWER(?)", (russian_tag,))
                row = cursor.fetchone()
                if row:
                    tag_id = row[0]
                else:
                    cursor.execute("INSERT INTO tags (name) VALUES (?)", (russian_tag,))
                    tag_id = cursor.lastrowid

                cursor.execute(
                    "INSERT OR IGNORE INTO books_tags_link (book, tag) VALUES (?, ?)",
                    (book_id, tag_id)
                )
                if cursor.rowcount > 0:
                    added += 1

    conn.commit()
    conn.close()

    print(f"\n✓ Added {added} Russian synonym tag links")
    print("\nDone! Run 'syncbooks' to push to VPS.")


if __name__ == "__main__":
    main()
