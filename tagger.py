#!/usr/bin/env python3
"""
Calibre AI Tagger v3
Uses Claude Haiku to generate rich metadata tags for your book library.
Automatically adds Russian translations of all tags.
Writes directly to Calibre's SQLite database (no command-line tools needed).

IMPORTANT: Close Calibre before running this script!
"""

import os
import sqlite3
import json
import time
from pathlib import Path
from anthropic import Anthropic

# Configuration
CALIBRE_LIBRARY = os.path.expanduser("~/Desktop/Calibre Library")
MODEL = "claude-haiku-4-5-20251001"
DELAY_BETWEEN_CALLS = 0.5  # Seconds between API calls
TRANSLATION_BATCH_SIZE = 40

client = Anthropic()

# Russian prefix mapping
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

TAGGING_PROMPT = """Analyze this book and provide structured metadata tags.

BOOK INFORMATION:
Title: {title}
Author: {author}
Existing Description: {description}

Generate tags in the following categories. Be specific and useful - these tags will be used to search and discover books.

Respond in this exact JSON format:
{{
  "genre": ["primary genre", "secondary genre if applicable"],
  "themes": ["theme1", "theme2", "theme3"],
  "topics": ["specific topic 1", "specific topic 2", "specific topic 3"],
  "mood": ["tone descriptor 1", "tone descriptor 2"],
  "difficulty": "introductory|intermediate|advanced|mixed",
  "subject_of": ["person name if this is a biography/memoir ABOUT someone"],
  "people_mentioned": ["notable figures discussed significantly in the book"],
  "time_period": ["relevant era or time period if applicable"],
  "language_note": "if non-English, note the language"
}}

Guidelines:
- Genre: Use broad categories (fiction, biography, business, psychology, self-help, history, science, philosophy, finance, technical, etc.)
- Themes: Abstract concepts explored (power, identity, mortality, wealth, consciousness, etc.)
- Topics: Concrete subjects covered (options trading, Jungian archetypes, marketing funnels, etc.)
- Mood: How it reads (academic, conversational, inspirational, dense, practical, narrative, etc.)
- Difficulty: Reader level required
- Subject_of: ONLY for biographies/memoirs - who is it about
- People_mentioned: Notable figures discussed (historical figures, business leaders, thinkers, etc.)
- Time_period: Leave empty if not relevant
- Language_note: Only include if not English

Be concise. 2-4 items per category is ideal. Empty arrays are fine if a category doesn't apply."""

TRANSLATION_PROMPT = """You are a professional English-to-Russian translator.
Translate the following book tags from English to Russian.

Rules:
- Translate naturally, not literally. Use how a Russian reader would actually describe the concept.
- For people's names: transliterate to standard Russian spelling (e.g., "Warren Buffett" → "Уоррен Баффетт", "Carl Jung" → "Карл Юнг")
- For well-known concepts, use the standard Russian term
- Keep it concise - tags should be short
- Return ONLY a JSON object mapping each English tag value to its Russian translation
- Do NOT include the prefix (genre:, theme:, etc.) - just translate the value part

Tags to translate:
{tags}

Return format (JSON only, no markdown, no backticks):
{{"english_value": "russian_value", "english_value2": "russian_value2"}}
"""


def get_db_connection():
    """Get connection to Calibre database."""
    db_path = Path(CALIBRE_LIBRARY) / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found at {db_path}")
    return sqlite3.connect(db_path)


def get_calibre_books():
    """Read all books from Calibre database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT
        b.id,
        b.title,
        b.path,
        GROUP_CONCAT(DISTINCT a.name) as authors,
        c.text as description
    FROM books b
    LEFT JOIN books_authors_link bal ON b.id = bal.book
    LEFT JOIN authors a ON bal.author = a.id
    LEFT JOIN comments c ON b.id = c.book
    GROUP BY b.id
    """

    cursor.execute(query)
    books = cursor.fetchall()
    conn.close()

    return [
        {
            "id": b[0],
            "title": b[1],
            "path": b[2],
            "author": b[3] or "Unknown",
            "description": b[4] or ""
        }
        for b in books
    ]


def get_existing_tags(book_id):
    """Get existing tags for a book."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.name FROM tags t
        JOIN books_tags_link btl ON t.id = btl.tag
        WHERE btl.book = ?
    """, (book_id,))

    tags = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tags


def analyze_book_with_ai(book):
    """Send book to Claude for analysis."""
    prompt = TAGGING_PROMPT.format(
        title=book["title"],
        author=book["author"],
        description=book["description"][:3000] if book["description"] else "No description available"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        return json.loads(text.strip())

    except Exception as e:
        print(f"  Error analyzing '{book['title'][:50]}': {e}")
        return None


def format_tags_for_calibre(analysis):
    """Convert AI analysis to Calibre tag format."""
    tags = []

    if analysis.get("genre"):
        tags.extend([f"genre:{g}" for g in analysis["genre"]])

    if analysis.get("themes"):
        tags.extend([f"theme:{t}" for t in analysis["themes"]])

    if analysis.get("topics"):
        tags.extend([f"topic:{t}" for t in analysis["topics"]])

    if analysis.get("mood"):
        tags.extend([f"mood:{m}" for m in analysis["mood"]])

    if analysis.get("difficulty"):
        tags.append(f"level:{analysis['difficulty']}")

    if analysis.get("subject_of"):
        tags.extend([f"biography:{p}" for p in analysis["subject_of"]])

    if analysis.get("people_mentioned"):
        tags.extend([f"person:{p}" for p in analysis["people_mentioned"]])

    if analysis.get("time_period"):
        tags.extend([f"era:{t}" for t in analysis["time_period"]])

    if analysis.get("language_note") and analysis["language_note"]:
        tags.append(f"language:{analysis['language_note']}")

    return tags


def add_tags_to_calibre_db(book_id, tags):
    """Add tags directly to Calibre's SQLite database."""
    if not tags:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for tag_name in tags:
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            result = cursor.fetchone()

            if result:
                tag_id = result[0]
            else:
                cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                tag_id = cursor.lastrowid

            cursor.execute("""
                INSERT OR IGNORE INTO books_tags_link (book, tag)
                VALUES (?, ?)
            """, (book_id, tag_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"  Database error: {e}")
        conn.rollback()
        conn.close()
        return False


# ── Russian Translation ──────────────────────────────────────────────────────

def get_all_russian_tag_values(db_path):
    """Get all existing Russian tag values to avoid re-translating."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM tags")
    all_tags = cursor.fetchall()
    conn.close()
    russian_tags = set()
    for (name,) in all_tags:
        if any('\u0400' <= c <= '\u04FF' for c in name):
            russian_tags.add(name)
    return russian_tags


def translate_batch(tag_values):
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
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def translate_new_tags(new_english_tags):
    """Translate newly added English tags to Russian and add to same books.

    Args:
        new_english_tags: list of (book_id, tag_name) tuples for newly added tags
    """
    if not new_english_tags:
        return

    db_path = str(Path(CALIBRE_LIBRARY) / "metadata.db")
    existing_russian = get_all_russian_tag_values(db_path)

    # Parse and collect unique values needing translation
    tag_info = []  # (book_id, prefix, value, full_tag)
    unique_values = set()

    for book_id, tag_name in new_english_tags:
        if ":" not in tag_name:
            continue
        prefix, value = tag_name.split(":", 1)
        prefix = prefix.strip().lower()
        value = value.strip()
        if prefix not in PREFIX_MAP:
            continue

        tag_info.append((book_id, prefix, value, tag_name))
        unique_values.add(value)

    if not unique_values:
        return

    unique_list = list(unique_values)
    print(f"\n📖 Translating {len(unique_list)} unique tag values to Russian...")

    # Translate in batches
    translations = {}
    for i in range(0, len(unique_list), TRANSLATION_BATCH_SIZE):
        batch = unique_list[i:i + TRANSLATION_BATCH_SIZE]
        batch_num = (i // TRANSLATION_BATCH_SIZE) + 1
        total_batches = (len(unique_list) + TRANSLATION_BATCH_SIZE - 1) // TRANSLATION_BATCH_SIZE
        print(f"  Translating batch {batch_num}/{total_batches}...")

        try:
            result = translate_batch(batch)
            translations.update(result)
        except Exception as e:
            print(f"  Translation error: {e}")
            for val in batch:
                try:
                    result = translate_batch([val])
                    translations.update(result)
                except:
                    print(f"    Skipping '{val}'")

        time.sleep(DELAY_BETWEEN_CALLS)

    # Apply translations
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    added = 0

    for book_id, prefix, value, full_tag in tag_info:
        if value not in translations:
            continue

        russian_prefix = PREFIX_MAP[prefix]
        russian_value = translations[value]
        russian_tag = f"{russian_prefix}:{russian_value}"

        # Get or create Russian tag
        cursor.execute("SELECT id FROM tags WHERE name = ?", (russian_tag,))
        row = cursor.fetchone()
        if row:
            tag_id = row[0]
        else:
            cursor.execute("INSERT INTO tags (name) VALUES (?)", (russian_tag,))
            tag_id = cursor.lastrowid

        # Link to book
        cursor.execute(
            "INSERT OR IGNORE INTO books_tags_link (book, tag) VALUES (?, ?)",
            (book_id, tag_id)
        )
        added += 1

    conn.commit()
    conn.close()
    print(f"  ✓ Added {added} Russian tag links")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("CALIBRE AI TAGGER v3 (with Russian translation)")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Make sure Calibre is CLOSED before continuing!\n")

    if not Path(CALIBRE_LIBRARY).exists():
        print(f"Error: Calibre library not found at {CALIBRE_LIBRARY}")
        return

    db_path = Path(CALIBRE_LIBRARY) / "metadata.db"
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return

    print(f"Reading library from: {CALIBRE_LIBRARY}")
    books = get_calibre_books()
    print(f"Found {len(books)} books")

    # Filter out already-tagged books
    books_to_process = []
    for book in books:
        existing = get_existing_tags(book["id"])
        has_ai_tags = any(":" in tag for tag in existing)
        if not has_ai_tags:
            books_to_process.append(book)

    print(f"Books needing AI tags: {len(books_to_process)}")

    if not books_to_process:
        print("All books already tagged!")
        return

    estimated_cost = len(books_to_process) * 0.004
    print(f"\nEstimated API cost: ${estimated_cost:.2f} (includes Russian translation)")
    response = input("Proceed? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return

    # Process books — collect new tags for translation
    success_count = 0
    error_count = 0
    all_new_tags = []  # (book_id, tag_name) for translation

    for i, book in enumerate(books_to_process):
        print(f"\n[{i+1}/{len(books_to_process)}] {book['title'][:50]}...")

        analysis = analyze_book_with_ai(book)
        if not analysis:
            error_count += 1
            continue

        tags = format_tags_for_calibre(analysis)
        print(f"  Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")

        if add_tags_to_calibre_db(book["id"], tags):
            success_count += 1
            for tag in tags:
                all_new_tags.append((book["id"], tag))
        else:
            error_count += 1

        time.sleep(DELAY_BETWEEN_CALLS)

    print("\n" + "=" * 60)
    print(f"TAGGING COMPLETE: {success_count} tagged, {error_count} errors")
    print("=" * 60)

    # Translate all new tags to Russian
    if all_new_tags:
        translate_new_tags(all_new_tags)

    print("\n" + "=" * 60)
    print("ALL DONE! Open Calibre to see your new tags.")
    print("Then run: syncbooks")
    print("=" * 60)


if __name__ == "__main__":
    main()
