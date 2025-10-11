# Bookmark Folders Strategy

## Current API State (as of 2025)

### Available Endpoints

**GET /2/users/{id}/bookmarks/folders**
- Returns list of bookmark folder names and IDs
- Rate limit:
  - **Free tier**: Unknown (likely very low)
  - **Basic tier ($200/mo)**: 5 requests per 15 min
- Fields: `id`, `name`
- Pagination: Supports `max_results` and `pagination_token`

**GET /2/users/{id}/bookmarks/folders/{folder_id}**
- Returns bookmarks within a specific folder
- Rate limit:
  - **Free tier**: Not available
  - **Basic tier ($200/mo)**: 5 requests per 15 min
- Limit: Returns bookmarks in specified folder only
- **This is the key endpoint for folder mapping**

**GET /2/users/{id}/bookmarks**
- Returns bookmarks (all folders mixed together)
- Rate limit:
  - **Free tier**: 180 requests per 15 min (but 1 req/15min total in practice)
  - **Basic tier ($200/mo)**: 10 requests per 15 min
- Limit: 800 most recent bookmarks
- **No folder filtering on this endpoint**

### Critical Limitation

⚠️ **The API does NOT support getting bookmarks from a specific folder**

The bookmarks endpoint returns all bookmarks mixed together, regardless of folder organization. This is a known limitation that developers have requested be fixed.

## Strategy Options

### Option 1: Free Tier - Manual Mapping (Current Implementation)

Since the free tier doesn't have access to folder-filtered endpoints, we use **manual folder management**:

**Approach:**
1. **Fetch folder list** from API (1 request)
2. **Collect all bookmarks** (existing collector.py workflow)
3. **Manually assign** bookmarks to folders via CLI
4. **Track assignments** in local database

**Benefits:**
- 100% accuracy (user-controlled)
- No API costs
- Works with free tier

**Trade-offs:**
- Manual effort required
- Time-consuming for large collections

---

### Option 2: Basic Tier - API Folder Mapping (Recommended for Speed)

With Basic tier ($200/mo), you get access to `GET /2/users/{id}/bookmarks/folders/{folder_id}`:

**Approach:**
1. **Fetch folder list** (1 request: GET /folders)
2. **Fetch bookmarks per folder** (N requests: GET /folders/{id} for each folder)
3. **Automatically map** in database during collection
4. **Complete accuracy** - ground truth from X API

**Benefits:**
- 100% accurate folder mapping
- Fully automated
- No manual tagging needed
- Complete folder organization preserved

**API Usage Calculation:**
See "Basic Tier Collection Timeline" section below.

## Implementation

### Database Schema

```sql
-- Bookmark folders table
CREATE TABLE bookmark_folders (
    folder_id TEXT PRIMARY KEY,
    folder_name TEXT NOT NULL,
    created_at TEXT,
    last_synced TEXT,
    UNIQUE(folder_name)
);

-- Many-to-many relationship (bookmarks can be in multiple folders)
CREATE TABLE bookmark_folder_membership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    folder_id TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,  -- Always 1.0 for manual mapping
    method TEXT DEFAULT 'manual', -- 'manual' for current implementation
    tagged_at TEXT,

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    FOREIGN KEY (folder_id) REFERENCES bookmark_folders(folder_id),
    UNIQUE(tweet_id, folder_id)
);

-- Folder classification rules (reserved for future auto-tagging)
CREATE TABLE folder_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,       -- 'keyword', 'author', 'domain', 'pattern'
    rule_value TEXT NOT NULL,      -- The actual rule
    weight REAL DEFAULT 1.0,       -- Rule importance

    FOREIGN KEY (folder_id) REFERENCES bookmark_folders(folder_id),
    INDEX idx_folder (folder_id),
    INDEX idx_type (rule_type)
);
```

### Folder Fetcher

```python
class BookmarkFolderManager:
    def __init__(self, db_path="complete_bookmarks.db"):
        self.db_path = db_path
        self.user_access_token = os.environ.get("USER_ACCESS_TOKEN")

    def fetch_folders(self, user_id):
        """Fetch folder list from X API"""
        url = f"https://api.twitter.com/2/users/{user_id}/bookmarks/folders"
        headers = {
            "Authorization": f"Bearer {self.user_access_token}",
            "Content-Type": "application/json",
        }
        params = {"max_results": 100}

        all_folders = []
        pagination_token = None

        while True:
            if pagination_token:
                params["pagination_token"] = pagination_token

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code != 200:
                print(f"Error fetching folders: {response.status_code}")
                break

            data = response.json()

            if "data" in data:
                all_folders.extend(data["data"])

            # Check for more pages
            if "meta" in data and "next_token" in data["meta"]:
                pagination_token = data["meta"]["next_token"]
            else:
                break

        return all_folders

    def sync_folders(self, user_id):
        """Sync folder list to database"""
        folders = self.fetch_folders(user_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for folder in folders:
            cursor.execute("""
                INSERT OR REPLACE INTO bookmark_folders
                (folder_id, folder_name, last_synced)
                VALUES (?, ?, ?)
            """, (folder["id"], folder["name"], datetime.now().isoformat()))

        conn.commit()
        conn.close()

        print(f"✓ Synced {len(folders)} folders")
        return folders

    def tag_bookmark(self, tweet_id, folder_name, method="manual", confidence=1.0):
        """Tag a bookmark with a folder"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get or create folder
        cursor.execute("SELECT folder_id FROM bookmark_folders WHERE folder_name = ?", (folder_name,))
        result = cursor.fetchone()

        if not result:
            folder_id = f"local_{folder_name.lower().replace(' ', '_')}"
            cursor.execute("""
                INSERT INTO bookmark_folders (folder_id, folder_name, created_at)
                VALUES (?, ?, ?)
            """, (folder_id, folder_name, datetime.now().isoformat()))
        else:
            folder_id = result[0]

        # Add membership
        cursor.execute("""
            INSERT OR REPLACE INTO bookmark_folder_membership
            (tweet_id, folder_id, confidence, method, tagged_at)
            VALUES (?, ?, ?, ?, ?)
        """, (tweet_id, folder_id, confidence, method, datetime.now().isoformat()))

        conn.commit()
        conn.close()

        print(f"✓ Tagged {tweet_id} → {folder_name} ({method}, {confidence:.2f})")

    def auto_tag_by_rules(self, folder_id):
        """Auto-tag bookmarks based on folder rules"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get rules for this folder
        cursor.execute("""
            SELECT rule_type, rule_value, weight
            FROM folder_rules
            WHERE folder_id = ?
        """, (folder_id,))
        rules = cursor.fetchall()

        if not rules:
            print(f"No rules found for folder {folder_id}")
            return

        # Get untagged bookmarks
        cursor.execute("""
            SELECT tweet_id, text, author_username, full_api_response
            FROM bookmarks
            WHERE tweet_id NOT IN (
                SELECT tweet_id FROM bookmark_folder_membership WHERE folder_id = ?
            )
        """, (folder_id,))

        bookmarks = cursor.fetchall()

        tagged_count = 0
        for tweet_id, text, author, full_response in bookmarks:
            score = 0.0
            text_lower = text.lower() if text else ""

            for rule_type, rule_value, weight in rules:
                if rule_type == "keyword" and rule_value.lower() in text_lower:
                    score += weight
                elif rule_type == "author" and rule_value.lower() == author.lower():
                    score += weight * 2  # Authors are strong signals
                elif rule_type == "domain":
                    # Extract domains from full_response
                    data = json.loads(full_response)
                    entities = data.get("entities", {})
                    urls = entities.get("urls", [])
                    for url_obj in urls:
                        expanded = url_obj.get("expanded_url", "")
                        if rule_value.lower() in expanded.lower():
                            score += weight * 1.5

            # Tag if score is high enough
            confidence = min(score / len(rules), 1.0)
            if confidence >= 0.3:  # Threshold for auto-tagging
                cursor.execute("""
                    INSERT OR REPLACE INTO bookmark_folder_membership
                    (tweet_id, folder_id, confidence, method, tagged_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (tweet_id, folder_id, confidence, "auto", datetime.now().isoformat()))
                tagged_count += 1

        conn.commit()
        conn.close()

        print(f"✓ Auto-tagged {tagged_count} bookmarks for folder {folder_id}")

    def create_rules_from_sample(self, folder_id, sample_tweet_ids):
        """Learn rules from manually tagged examples"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get sample bookmarks
        placeholders = ",".join("?" * len(sample_tweet_ids))
        cursor.execute(f"""
            SELECT text, author_username, full_api_response
            FROM bookmarks
            WHERE tweet_id IN ({placeholders})
        """, sample_tweet_ids)

        samples = cursor.fetchall()

        # Extract common keywords (simple approach)
        all_words = []
        all_authors = set()
        all_domains = set()

        for text, author, full_response in samples:
            if text:
                words = text.lower().split()
                all_words.extend([w for w in words if len(w) > 3])  # Skip short words
            all_authors.add(author)

            # Extract domains
            data = json.loads(full_response)
            entities = data.get("entities", {})
            for url_obj in entities.get("urls", []):
                expanded = url_obj.get("expanded_url", "")
                if "://" in expanded:
                    domain = expanded.split("://")[1].split("/")[0]
                    all_domains.add(domain)

        # Find most common keywords
        from collections import Counter
        word_counts = Counter(all_words)
        top_keywords = [word for word, count in word_counts.most_common(10) if count >= 2]

        # Create rules
        for keyword in top_keywords:
            cursor.execute("""
                INSERT OR REPLACE INTO folder_rules
                (folder_id, rule_type, rule_value, weight)
                VALUES (?, 'keyword', ?, 1.0)
            """, (folder_id, keyword))

        for author in all_authors:
            cursor.execute("""
                INSERT OR REPLACE INTO folder_rules
                (folder_id, rule_type, rule_value, weight)
                VALUES (?, 'author', ?, 2.0)
            """, (folder_id, author))

        for domain in all_domains:
            cursor.execute("""
                INSERT OR REPLACE INTO folder_rules
                (folder_id, rule_type, rule_value, weight)
                VALUES (?, 'domain', ?, 1.5)
            """, (folder_id, domain))

        conn.commit()
        conn.close()

        print(f"✓ Created {len(top_keywords) + len(all_authors) + len(all_domains)} rules")
```

## Basic Tier Collection Timeline

### Complete Bookmark + Folder Collection Estimate

**Scenario:** Collect all bookmarks with folder organization using Basic tier API

**Available Rate Limits (Basic Tier, $200/mo):**
- GET /2/users/{id}/bookmarks: 10 requests / 15 min
- GET /2/users/{id}/bookmarks/folders: 5 requests / 15 min
- GET /2/users/{id}/bookmarks/folders/{folder_id}: 5 requests / 15 min

### Timeline Calculation

#### Step 1: Fetch Folder List
```
Assumption: Most users have < 100 folders
API calls: 1 request (or N/100 if >100 folders)
Time: 15 minutes
```

#### Step 2: Fetch Bookmarks Per Folder
```
Assumptions:
- User has 10 folders
- Average 1,000 bookmarks per folder
- 10,000 total bookmarks
- Each folder request returns up to 100 bookmarks (requires pagination)

Requests per folder:
- 1,000 bookmarks / 100 per request = 10 requests per folder
- 10 folders × 10 requests = 100 total requests

Rate limit: 5 requests per 15 min
Timeline: 100 requests / 5 per 15min = 20 intervals
Total time: 20 × 15 min = 300 minutes = 5 hours
```

#### Step 3: Enrich with Full Bookmark Data (Optional)
```
If you want ALL fields (media, polls, etc.), you might need:
GET /2/users/{id}/bookmarks with expansions

Requests: 10,000 bookmarks / 100 per request = 100 requests
Rate limit: 10 requests per 15 min
Timeline: 100 / 10 = 10 intervals = 150 minutes = 2.5 hours
```

### Total Collection Time Estimates

**Folders Only (no bookmark data):**
- Folder list + folder membership
- Time: ~5 hours
- Result: Know which bookmark is in which folder

**Folders + Basic Bookmark Data:**
- Folders fetched via folder endpoints (includes basic tweet data)
- Time: ~5 hours
- Result: Bookmarks organized by folder with basic fields

**Folders + Full Bookmark Data:**
- Folders + full expansions/fields from main bookmarks endpoint
- Time: ~5 hours + 2.5 hours = **7.5 hours total**
- Result: Complete bookmark archive with folder organization

### Comparison: Free Tier vs Basic Tier

| Metric | Free Tier | Basic Tier |
|--------|-----------|------------|
| **Bookmark Collection** | ~105 days (10k bookmarks) | ~2.5 hours (10k bookmarks) |
| **Folder Mapping** | Manual (user effort) | Automatic (~5 hours) |
| **Total Time** | ~105 days + manual work | ~7.5 hours |
| **Cost** | $0 | $200/month |
| **Accuracy** | 100% (manual) | 100% (API ground truth) |
| **Effort** | High (manual tagging) | Low (automated) |

### Break-Even Analysis

**Time Saved:** ~105 days → 7.5 hours = **2,512 hours saved**

**Cost per Hour Saved:**
- $200 / 2,512 hours = **$0.08 per hour**

**If you value your time at $10/hr:**
- Manual work value: 2,512 hours × $10 = $25,120
- API cost: $200
- **Savings: $24,920**

**Recommendation:** Basic tier is worth it for any collection >1,000 bookmarks if you value your time.

---

## Optimal Workflow Given API Limits

### Free Tier Workflow

#### Phase 1: Sync Folders (1 API call)
```python
# Fetch folder list from X API
manager = BookmarkFolderManager()
folders = manager.sync_folders(user_id)
# Rate limit: 1 request
```

### Phase 2: Collect Bookmarks (Existing workflow)
```python
# Run normal bookmark collection
# All bookmarks collected without folder info
collector = CompleteBookmarkCollector()
collector.run_complete_collection()
```

### Phase 3: Manual Assignment (No API calls)
```bash
# User manually assigns bookmarks to folders
python3 folder_manager.py tag TWEET_ID --folder "Tech News"
python3 folder_manager.py tag TWEET_ID --folder "Research"

# Or batch assign
python3 folder_manager.py batch-tag --file assignments.csv
```

#### Phase 4: Query and Export (No API calls)
```python
# Query bookmarks by folder
SELECT b.* FROM bookmarks b
JOIN bookmark_folder_membership m ON b.tweet_id = m.tweet_id
JOIN bookmark_folders f ON m.folder_id = f.folder_id
WHERE f.folder_name = 'Tech News';

# Export folder organization
python3 folder_manager.py export --format json
```

---

### Basic Tier Workflow (Automated)

#### Phase 1: Fetch Folder List (1 request, 15 min)
```python
# GET /2/users/{id}/bookmarks/folders
manager = BookmarkFolderManager()
folders = manager.sync_folders(user_id)
print(f"Found {len(folders)} folders")
```

#### Phase 2: Fetch Bookmarks Per Folder (5 req/15min)
```python
# For each folder, GET /2/users/{id}/bookmarks/folders/{folder_id}
for folder in folders:
    bookmarks = manager.fetch_folder_bookmarks(folder['id'])

    # Store bookmarks with folder membership
    for bookmark in bookmarks:
        manager.store_bookmark_with_folder(
            bookmark,
            folder_id=folder['id'],
            folder_name=folder['name'],
            method='api'
        )

    # Rate limit: 5 requests per 15 min
    # Pagination: 100 bookmarks per request
    # Wait between requests if needed
```

#### Phase 3: Enrich with Full Data (Optional, 10 req/15min)
```python
# Get ALL fields/expansions for collected bookmarks
# GET /2/users/{id}/bookmarks with full expansions
enricher = BookmarkEnricher()
enricher.enrich_existing_bookmarks()

# This adds media, polls, places, etc.
# to bookmarks that only have basic data from folder endpoints
```

#### Phase 4: Query and Export (No API calls)
```python
# Same as free tier - query local database
SELECT * FROM bookmarks
WHERE tweet_id IN (
    SELECT tweet_id FROM bookmark_folder_membership
    WHERE folder_id = 'folder_123'
);
```

### Basic Tier Implementation Example

```python
class BasicTierFolderCollector:
    """Collector optimized for Basic tier API with folder support"""

    def __init__(self, db_path="complete_bookmarks.db"):
        self.db_path = db_path
        self.user_access_token = os.environ.get("USER_ACCESS_TOKEN")
        self.rate_limit_folders = 5  # requests per 15 min
        self.rate_limit_bookmarks = 10  # requests per 15 min

    def collect_all_with_folders(self, user_id):
        """Complete collection with folder organization"""

        # Step 1: Get folders
        print("Fetching folder list...")
        folders = self.sync_folders(user_id)
        print(f"Found {len(folders)} folders")

        # Step 2: Collect bookmarks per folder
        total_bookmarks = 0
        for i, folder in enumerate(folders, 1):
            print(f"\nProcessing folder {i}/{len(folders)}: {folder['name']}")

            folder_bookmarks = self.fetch_all_in_folder(
                user_id,
                folder['id'],
                folder['name']
            )

            total_bookmarks += len(folder_bookmarks)
            print(f"  Collected {len(folder_bookmarks)} bookmarks")

        print(f"\n✓ Total bookmarks collected: {total_bookmarks}")
        print(f"✓ Folder organization preserved")

        return total_bookmarks

    def fetch_all_in_folder(self, user_id, folder_id, folder_name):
        """Fetch all bookmarks in a specific folder with pagination"""
        all_bookmarks = []
        pagination_token = None

        while True:
            # GET /2/users/{id}/bookmarks/folders/{folder_id}
            url = f"https://api.twitter.com/2/users/{user_id}/bookmarks/folders/{folder_id}"
            headers = {"Authorization": f"Bearer {self.user_access_token}"}
            params = {
                "max_results": 100,
                "tweet.fields": "created_at,author_id,text,public_metrics",
                "expansions": "author_id",
            }

            if pagination_token:
                params["pagination_token"] = pagination_token

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                break

            data = response.json()

            if "data" in data:
                # Store bookmarks with folder membership
                for bookmark in data["data"]:
                    self.store_bookmark_with_folder(
                        bookmark,
                        folder_id,
                        folder_name,
                        method="api"
                    )
                    all_bookmarks.append(bookmark)

            # Check for pagination
            if "meta" in data and "next_token" in data["meta"]:
                pagination_token = data["meta"]["next_token"]

                # Rate limit: 5 requests per 15 min
                print(f"    Fetched {len(all_bookmarks)} so far, waiting 15 min...")
                time.sleep(15 * 60)
            else:
                break

        return all_bookmarks

    def store_bookmark_with_folder(self, bookmark, folder_id, folder_name, method="api"):
        """Store bookmark and folder membership"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Store bookmark (existing logic)
        # ...

        # Store folder membership
        cursor.execute("""
            INSERT OR REPLACE INTO bookmark_folder_membership
            (tweet_id, folder_id, confidence, method, tagged_at)
            VALUES (?, ?, 1.0, ?, ?)
        """, (bookmark["id"], folder_id, method, datetime.now().isoformat()))

        conn.commit()
        conn.close()
```

### Timeline Summary

**For 10,000 bookmarks across 10 folders:**

| Step | Requests | Rate Limit | Time |
|------|----------|------------|------|
| Fetch folders | 1 | 5/15min | 15 min |
| Fetch folder bookmarks | 100 | 5/15min | 5 hours |
| **Total (with folders)** | **101** | - | **~5 hours** |
| Enrich with full data (opt) | 100 | 10/15min | 2.5 hours |
| **Total (full archive)** | **201** | - | **~7.5 hours** |

## API Call Optimization

**Total API calls for folder management:**
- Fetch folders: 1 call (or N/100 if >100 folders)
- Folder assignment: 0 calls (local database only)
- Queries and exports: 0 calls (local processing)

**This adds minimal overhead to the existing collection strategy.**

---

## Future Enhancement: Automated Learning (Optional)

For users with large collections who want automation, we could add machine learning in the future:

### Auto-Tagging Approach (Future Feature)

#### Phase 1: Manual Sampling
```python
# User tags 5-10 examples per folder
manager.tag_bookmark("tweet1", "Tech News", method="manual")
manager.tag_bookmark("tweet2", "Tech News", method="manual")
```

#### Phase 2: Rule Learning
```python
# Learn patterns from manual tags
manager.create_rules_from_sample("folder_123", ["tweet1", "tweet2", ...])

# Extracted rules:
# - Keywords: "AI", "tech", "startup"
# - Authors: "@techcrunch", "@verge"
# - Domains: "techcrunch.com", "theverge.com"
```

#### Phase 3: Auto-Tag with Confidence
```python
# Auto-tag remaining bookmarks
for folder_id in folder_ids:
    manager.auto_tag_by_rules(folder_id)

# Results include confidence scores (0.0-1.0)
# User can review low-confidence tags
```

#### Phase 4: Iterative Improvement
```python
# Show uncertain tags for manual review
SELECT * FROM bookmark_folder_membership
WHERE confidence < 0.6 AND method = 'auto'
ORDER BY confidence ASC;

# User corrections improve rules over time
```

### Auto-Tagging Benefits

✅ **Faster organization** - Bulk categorization
✅ **Confidence tracking** - Know which tags are uncertain
✅ **Iterative improvement** - Rules get better with corrections
✅ **Still manual override** - Always correct mistakes

### Auto-Tagging Trade-offs

⚠️ **Not 100% accurate** - Inference-based, not ground truth
⚠️ **Requires initial effort** - Manual tagging of training samples
⚠️ **Complexity** - More code to maintain
✅ **Optional** - Users can stick to manual if preferred

### Implementation in folder_rules Table

The existing `folder_rules` table supports future auto-tagging:

```sql
CREATE TABLE folder_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,       -- 'keyword', 'author', 'domain', 'pattern'
    rule_value TEXT NOT NULL,      -- The actual rule
    weight REAL DEFAULT 1.0,       -- Rule importance

    FOREIGN KEY (folder_id) REFERENCES bookmark_folders(folder_id)
);
```

**Current use:** Empty (not used for manual mapping)
**Future use:** Store learned rules for auto-tagging

## CLI Tool (Current Implementation)

```bash
# Sync folders from API
python3 folder_manager.py sync

# List folders
python3 folder_manager.py list

# Tag bookmark manually
python3 folder_manager.py tag TWEET_ID --folder "Tech News"

# Batch tag from CSV file
python3 folder_manager.py batch-tag --file assignments.csv
# CSV format: tweet_id,folder_name

# Remove tag
python3 folder_manager.py untag TWEET_ID --folder "Tech News"

# Show bookmark's folders
python3 folder_manager.py show TWEET_ID

# Export folder organization
python3 folder_manager.py export --format json > folders.json

# Show stats
python3 folder_manager.py stats
```

## Future CLI (Auto-Tagging)

```bash
# Create rules from samples (future)
python3 folder_manager.py learn "Tech News" --samples tweet1,tweet2,tweet3

# Auto-tag all bookmarks (future)
python3 folder_manager.py auto-tag-all

# Review low-confidence tags (future)
python3 folder_manager.py review --threshold 0.6
```

## Benefits (Current Manual Approach)

✅ **Minimal API usage** - 1 call to get folder list
✅ **100% accuracy** - User-controlled, no false positives
✅ **Simple implementation** - Just database mappings
✅ **Full control** - Users decide organization
✅ **Exportable** - Share folder organization
✅ **No inference errors** - Explicit assignments only

## Trade-offs

⚠️ **Manual effort required** - Must tag each bookmark
⚠️ **Time-consuming** - Scales linearly with bookmark count
⚠️ **No automation** - Can't bulk-categorize (yet)
✅ **Can add automation later** - Database schema supports it
✅ **Users prefer accuracy** - Manual is better than wrong

## Future Enhancement

If X adds folder filtering to the API:
```python
# Ideal future API (not currently available)
GET /2/users/{id}/bookmarks?folder_id=abc123
```

We could then validate our inference against actual folder membership and improve our classifier.
