#!/usr/bin/env python3
"""
Calibre Tag Cleanup Script
"""

import os
import sqlite3
import json
import time
from pathlib import Path
from anthropic import Anthropic

CALIBRE_LIBRARY = os.path.expanduser("~/calibre-library/Calibre Library")
MODEL = "claude-haiku-4-5-20251001"

client = Anthropic()

ALLOWED_GENRES = [
    "fiction", "literary fiction", "science fiction", "historical fiction",
    "thriller", "mystery", "fantasy", "romance", "adventure", "satire",
    "biography", "autobiography", "memoir",
    "history", "military history", "political history",
    "business", "entrepreneurship", "marketing", "finance", "investing",
    "economics", "political economy",
    "philosophy", "psychology", "psychoanalysis", "spirituality", "religion",
    "science", "physics", "biology", "neuroscience", "medicine", "mathematics",
    "computer science", "technology",
    "self-help", "personal development", "health", "productivity",
    "politics", "geopolitics", "international relations", "law",
    "journalism", "true crime", "espionage",
    "art", "architecture", "design", "photography",
    "sociology", "anthropology", "cultural studies",
    "education", "reference", "textbook",
    "travel", "nature", "sports",
    "poetry", "drama", "essays",
    "children's literature",
]

ALLOWED_MOODS = [
    "academic", "conversational", "practical", "inspirational",
    "dense", "narrative", "analytical", "provocative",
    "meditative", "humorous", "dark", "accessible",
]

ALLOWED_LEVELS = ["introductory", "intermediate", "advanced", "mixed"]


def get_db_connection():
    db_path = Path(CALIBRE_LIBRARY) / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found at {db_path}")
    return sqlite3.connect(db_path)


def get_all_tags():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.name, COUNT(btl.book) as book_count
        FROM tags t LEFT JOIN books_tags_link btl ON t.id = btl.tag
        GROUP BY t.id, t.name ORDER BY t.name
    """)
    tags = cursor.fetchall()
    conn.close()
    return tags


def get_ai_tags_by_prefix(prefix):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.name, COUNT(btl.book) as book_count
        FROM tags t LEFT JOIN books_tags_link btl ON t.id = btl.tag
        WHERE t.name LIKE ? GROUP BY t.id, t.name ORDER BY t.name
    """, (f"{prefix}:%",))
    tags = cursor.fetchall()
    conn.close()
    return tags


def consolidate_with_ai(prefix, current_tags, allowed_list=None):
    tag_names = [t[1].split(":", 1)[1] for t in current_tags]
    allowed_section = ""
    if allowed_list:
        allowed_section = f"\nYou MUST map each tag to one of these allowed values (or \"DELETE\" if it doesn't fit any):\n{json.dumps(allowed_list)}\n"

    prompt = f"""I have these {prefix} tags from a book library that need consolidation.
Many are near-duplicates or overly specific. Map each to a cleaner, broader version.

Current tags:
{json.dumps(tag_names)}
{allowed_section}
Rules:
- Merge near-duplicates (e.g., "non-fiction" and "nonfiction" -> "non-fiction")
- Merge overly specific into broader categories (e.g., "narrative journalism" and "investigative journalism" -> "journalism")
- Keep important distinctions (e.g., "fiction" vs "historical fiction" are worth keeping separate)
- If a tag is junk/meaningless, map it to "DELETE"
- For biography/person tags, standardize name format: "First Last" (e.g., "C. G. Jung" -> "Carl Jung")
- For themes, consolidate aggressively. Aim for max 50-60 unique themes total.
- For topics, consolidate aggressively. Aim for max 80-100 unique topics total.

Respond ONLY with a JSON object mapping each original tag to its consolidated version:
{{
  "original tag": "consolidated tag",
  "another tag": "consolidated tag"
}}"""

    try:
        response = client.messages.create(model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        print(f"  Error consolidating {prefix}: {e}")
        return None


def apply_tag_mapping(prefix, mapping, current_tags, dry_run=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    changes = 0
    deletions = 0

    for tag_id, tag_name, book_count in current_tags:
        original = tag_name.split(":", 1)[1]
        if original not in mapping:
            continue
        new_value = mapping[original]
        new_tag_name = f"{prefix}:{new_value}"

        if new_value == "DELETE":
            if dry_run:
                print(f"  DELETE: {tag_name} ({book_count} books)")
            else:
                cursor.execute("DELETE FROM books_tags_link WHERE tag = ?", (tag_id,))
                cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            deletions += 1
            continue

        if new_tag_name == tag_name:
            continue

        if dry_run:
            print(f"  {tag_name} -> {new_tag_name} ({book_count} books)")
            changes += 1
            continue

        cursor.execute("SELECT id FROM tags WHERE name = ?", (new_tag_name,))
        existing = cursor.fetchone()
        if existing:
            target_id = existing[0]
            cursor.execute("UPDATE OR IGNORE books_tags_link SET tag = ? WHERE tag = ?", (target_id, tag_id))
            cursor.execute("DELETE FROM books_tags_link WHERE tag = ?", (tag_id,))
            cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        else:
            cursor.execute("UPDATE tags SET name = ? WHERE id = ?", (new_tag_name, tag_id))
        changes += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return changes, deletions


def delete_junk_tags(dry_run=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.name, COUNT(btl.book) as book_count
        FROM tags t LEFT JOIN books_tags_link btl ON t.id = btl.tag
        WHERE t.name NOT LIKE 'genre:%' AND t.name NOT LIKE 'theme:%'
          AND t.name NOT LIKE 'topic:%' AND t.name NOT LIKE 'mood:%'
          AND t.name NOT LIKE 'level:%' AND t.name NOT LIKE 'biography:%'
          AND t.name NOT LIKE 'person:%' AND t.name NOT LIKE 'era:%'
          AND t.name NOT LIKE 'language:%'
        GROUP BY t.id, t.name
    """)
    junk_tags = cursor.fetchall()

    if dry_run:
        print(f"\nWould delete {len(junk_tags)} junk tags")
        for tag_id, name, count in junk_tags[:20]:
            print(f"  {name} ({count} books)")
        if len(junk_tags) > 20:
            print(f"  ... and {len(junk_tags) - 20} more")
    else:
        for tag_id, name, count in junk_tags:
            cursor.execute("DELETE FROM books_tags_link WHERE tag = ?", (tag_id,))
            cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        conn.commit()
        print(f"Deleted {len(junk_tags)} junk tags")
    conn.close()
    return len(junk_tags)


def cleanup_orphan_tags():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag FROM books_tags_link)")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def main():
    print("=" * 60)
    print("CALIBRE TAG CLEANUP")
    print("=" * 60)
    print(f"\nUsing library: {CALIBRE_LIBRARY}")

    all_tags = get_all_tags()
    prefixes = ["genre", "theme", "topic", "mood", "level", "biography", "person", "era", "language"]
    ai_tags = [t for t in all_tags if any(t[1].startswith(p + ":") for p in prefixes)]
    junk_tags = [t for t in all_tags if t not in ai_tags]

    print(f"Total tags: {len(all_tags)}")
    print(f"AI tags: {len(ai_tags)}")
    print(f"Junk tags: {len(junk_tags)}")

    print("\n" + "=" * 60)
    print("STEP 1: Delete junk tags")
    print("=" * 60)
    delete_junk_tags(dry_run=True)
    resp = input("\nDelete these junk tags? (y/n): ")
    if resp.lower() == 'y':
        delete_junk_tags(dry_run=False)

    prefix_config = [
        ("genre", ALLOWED_GENRES), ("mood", ALLOWED_MOODS), ("level", ALLOWED_LEVELS),
        ("theme", None), ("topic", None), ("biography", None),
        ("person", None), ("era", None), ("language", None),
    ]

    for prefix, allowed in prefix_config:
        current = get_ai_tags_by_prefix(prefix)
        if not current:
            continue
        print(f"\n{'=' * 60}")
        print(f"CONSOLIDATING: {prefix} ({len(current)} tags)")
        print(f"{'=' * 60}")

        batch_size = 100
        all_mappings = {}
        for i in range(0, len(current), batch_size):
            batch = current[i:i + batch_size]
            print(f"  Processing batch {i//batch_size + 1}...")
            mapping = consolidate_with_ai(prefix, batch, allowed)
            if mapping:
                all_mappings.update(mapping)
            time.sleep(1)

        if not all_mappings:
            print(f"  Skipping {prefix}")
            continue

        changes, deletions = apply_tag_mapping(prefix, all_mappings, current, dry_run=True)
        print(f"\n  Summary: {changes} renames, {deletions} deletions")
        resp = input(f"  Apply {prefix} changes? (y/n): ")
        if resp.lower() == 'y':
            apply_tag_mapping(prefix, all_mappings, current, dry_run=False)
            print(f"  Done")

    orphans = cleanup_orphan_tags()
    print(f"\nCleaned up {orphans} orphan tags")

    final_tags = get_all_tags()
    print(f"\n{'=' * 60}")
    print(f"DONE! Tags reduced: {len(all_tags)} -> {len(final_tags)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
