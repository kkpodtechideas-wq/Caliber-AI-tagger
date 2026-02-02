# Calibre AI Tagger

Uses Claude Haiku to auto-tag books in Calibre with rich metadata:
- Genre, themes, topics
- Mood and difficulty level
- People mentioned / biography subjects
- Language detection

## Setup
```bash
cd ~/calibre-tagger
python3 -m venv venv
source venv/bin/activate
pip install anthropic
export ANTHROPIC_API_KEY='your-key'
```

## Usage

1. Close Calibre
2. Run: `python tagger.py`
3. Reopen Calibre to see tags

Cost: ~$0.003 per book (Claude Haiku)

## Adding New Books

1. Open Calibre, drag in new book(s)
2. Right-click → Edit metadata → Download metadata and covers
3. Close Calibre
4. Run the tagger — it automatically skips already-tagged books:
```bash
cd ~/calibre-tagger
source venv/bin/activate
python tagger.py
```

### Quick alias (optional)

Add this to your shell so you can just type `tagbooks`:
```bash
echo 'alias tagbooks="cd ~/calibre-tagger && source venv/bin/activate && python tagger.py"' >> ~/.zshrc
source ~/.zshrc
```

## Customizing Tags

The tagging categories are defined in the `TAGGING_PROMPT` variable in `tagger.py`. 

### Current tag categories:
| Prefix | What it captures |
|--------|------------------|
| `genre:` | fiction, biography, business, psychology, etc. |
| `theme:` | Abstract concepts: power, identity, consciousness |
| `topic:` | Specific subjects: options trading, Jungian archetypes |
| `mood:` | Tone: academic, conversational, dense, practical |
| `level:` | Difficulty: introductory, intermediate, advanced |
| `biography:` | Who the book is about (for biographies) |
| `person:` | Notable figures discussed in the book |
| `era:` | Time period if relevant |
| `language:` | Language if non-English |

### To add new tag categories:

1. Open `tagger.py`
2. Find the `TAGGING_PROMPT` string
3. Add your new category to the JSON format section, e.g.:
```
   "reading_context": ["where or when to read this - beach, study, commute"],
```
4. Add guidelines for the AI in the Guidelines section
5. In the `format_tags_for_calibre()` function, add:
```python
   if analysis.get("reading_context"): 
       tags.extend([f"context:{c}" for c in analysis["reading_context"]])
```

### To re-tag all books with new categories:

The script skips books that already have tags with `:` in them. To force re-tagging:

**Option A: Re-tag everything**
In `tagger.py`, find this line in `main()`:
```python
has_ai_tags = any(":" in tag for tag in existing)
if not has_ai_tags:
```
Change to:
```python
if True:  # Force re-tag all
```

**Option B: Re-tag specific books**
In Calibre, select the books you want to re-tag, right-click → Edit metadata → Remove tags (clear the AI tags), then run the script.

## Configuration

At the top of `tagger.py`:
```python
CALIBRE_LIBRARY = os.path.expanduser("~/Desktop/Calibre Library")  # Your library path
MODEL = "claude-haiku-4-5-20251001"  # Can change to sonnet for deeper analysis
DELAY_BETWEEN_CALLS = 0.5  # Seconds between API calls
```

## Troubleshooting

**"Database not found"** — Check your `CALIBRE_LIBRARY` path matches where Calibre stores your library.

**"Database is locked"** — Calibre is still open. Close it completely.

**High error rate** — Some books lack enough metadata for good tagging. The script continues past errors.
