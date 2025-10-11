# Database Schema Improvements

## Current State

The collector stores all bookmark data in a single `full_api_response` TEXT column as JSON. While this preserves everything, it makes querying and analysis difficult.

## Proposed Enhancements

### Extract Key Fields to Dedicated Columns

**Benefits:**
- Faster queries (indexed columns vs JSON parsing)
- Easier analytics (SQL aggregations)
- Better data integrity (typed columns)
- Simpler exports (direct column access)

### Recommended Schema Additions

#### Bookmarks Table Enhancement

```sql
CREATE TABLE bookmarks (
    -- Existing columns
    tweet_id TEXT PRIMARY KEY,
    author_id TEXT,
    author_username TEXT,
    author_name TEXT,
    text TEXT,
    created_at TEXT,
    bookmark_url TEXT,
    public_metrics TEXT,  -- Keep as JSON for now
    collected_at TEXT,
    collection_cycle INTEGER,
    full_api_response TEXT,  -- Keep for reference

    -- New extracted fields
    conversation_id TEXT,           -- Thread identification
    in_reply_to_user_id TEXT,       -- Reply context
    lang TEXT,                       -- Tweet language
    possibly_sensitive BOOLEAN,     -- Content warning
    reply_settings TEXT,            -- Who can reply
    source TEXT,                    -- App/platform used

    -- Public metrics (extracted from JSON)
    like_count INTEGER,
    retweet_count INTEGER,
    reply_count INTEGER,
    quote_count INTEGER,
    bookmark_count INTEGER,
    impression_count INTEGER,

    -- Flags
    has_media BOOLEAN,
    has_poll BOOLEAN,
    has_geo BOOLEAN,
    is_quote BOOLEAN,
    is_retweet BOOLEAN,
    is_reply BOOLEAN,

    -- Edit tracking
    edit_history_tweet_ids TEXT,   -- JSON array

    -- Indices for common queries
    INDEX idx_author_id (author_id),
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at),
    INDEX idx_lang (lang),
    INDEX idx_like_count (like_count)
);
```

#### Media Table (New)

```sql
CREATE TABLE media (
    media_key TEXT PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    type TEXT,                      -- photo, video, animated_gif
    url TEXT,
    preview_image_url TEXT,
    alt_text TEXT,
    width INTEGER,
    height INTEGER,
    duration_ms INTEGER,            -- For videos
    variants TEXT,                  -- JSON array of video formats
    public_metrics TEXT,            -- JSON: view_count for videos

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);
```

#### Polls Table (New)

```sql
CREATE TABLE polls (
    poll_id TEXT PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    duration_minutes INTEGER,
    end_datetime TEXT,
    voting_status TEXT,             -- open, closed
    options TEXT,                   -- JSON array: [{position, label, votes}]
    total_votes INTEGER,            -- Calculated from options

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);
```

#### Places Table (New)

```sql
CREATE TABLE places (
    place_id TEXT PRIMARY KEY,
    full_name TEXT,
    name TEXT,
    country TEXT,
    country_code TEXT,
    place_type TEXT,                -- city, admin, country, poi
    geo_bbox TEXT,                  -- JSON array: [lon1, lat1, lon2, lat2]
    geo_coordinates TEXT,           -- JSON: {type: "Point", coordinates: [lon, lat]}
    contained_within TEXT,          -- JSON array of parent place IDs
);

CREATE TABLE bookmark_places (
    tweet_id TEXT,
    place_id TEXT,
    PRIMARY KEY (tweet_id, place_id),
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    FOREIGN KEY (place_id) REFERENCES places(place_id)
);
```

#### Referenced Tweets Table (New)

```sql
CREATE TABLE referenced_tweets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,         -- The bookmark
    referenced_tweet_id TEXT NOT NULL,  -- The quoted/retweeted tweet
    reference_type TEXT NOT NULL,   -- retweeted, quoted, replied_to

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_tweet_id (tweet_id),
    INDEX idx_referenced_id (referenced_tweet_id),
    INDEX idx_type (reference_type)
);
```

#### Mentions Table (New)

```sql
CREATE TABLE mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    mentioned_user_id TEXT NOT NULL,
    mentioned_username TEXT,
    start_position INTEGER,
    end_position INTEGER,

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_tweet_id (tweet_id),
    INDEX idx_mentioned_user (mentioned_user_id)
);
```

#### Hashtags Table (New)

```sql
CREATE TABLE hashtags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    start_position INTEGER,
    end_position INTEGER,

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_tweet_id (tweet_id),
    INDEX idx_tag (tag)
);
```

#### URLs Table (New)

```sql
CREATE TABLE urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    url TEXT NOT NULL,              -- Shortened URL
    expanded_url TEXT,              -- Full URL
    display_url TEXT,               -- Display text
    unwound_url TEXT,               -- Final destination
    start_position INTEGER,
    end_position INTEGER,

    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_tweet_id (tweet_id),
    INDEX idx_domain (unwound_url)
);
```

#### Authors Table Enhancement

```sql
CREATE TABLE authors (
    author_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    name TEXT,
    description TEXT,
    location TEXT,
    url TEXT,
    profile_image_url TEXT,
    created_at TEXT,
    protected BOOLEAN,
    verified BOOLEAN,
    verified_type TEXT,             -- blue, business, government, none

    -- Public metrics
    followers_count INTEGER,
    following_count INTEGER,
    tweet_count INTEGER,
    listed_count INTEGER,
    like_count INTEGER,

    -- Metadata
    last_updated TEXT,
    full_profile_data TEXT,         -- Complete JSON

    INDEX idx_username (username),
    INDEX idx_verified (verified),
    INDEX idx_followers (followers_count)
);
```

## Implementation Approach

### Phase 1: Add New Tables

Create migration script to add new tables without modifying existing data:

```python
def migrate_schema():
    conn = sqlite3.connect("complete_bookmarks.db")
    cursor = conn.cursor()

    # Add new tables
    cursor.execute(CREATE_MEDIA_TABLE)
    cursor.execute(CREATE_POLLS_TABLE)
    # ... etc

    conn.commit()
    conn.close()
```

### Phase 2: Extract Data from Existing Bookmarks

```python
def extract_and_populate():
    """Extract data from full_api_response JSON into new columns"""
    conn = sqlite3.connect("complete_bookmarks.db")
    cursor = conn.cursor()

    cursor.execute("SELECT tweet_id, full_api_response FROM bookmarks")
    for tweet_id, json_data in cursor.fetchall():
        data = json.loads(json_data)

        # Extract and insert media
        if "attachments" in data and "media_keys" in data["attachments"]:
            extract_media(tweet_id, data, conn)

        # Extract and insert polls
        if "attachments" in data and "poll_ids" in data["attachments"]:
            extract_polls(tweet_id, data, conn)

        # Extract entities
        if "entities" in data:
            extract_hashtags(tweet_id, data["entities"], conn)
            extract_mentions(tweet_id, data["entities"], conn)
            extract_urls(tweet_id, data["entities"], conn)

        # Update bookmark with extracted fields
        update_bookmark_fields(tweet_id, data, conn)

    conn.commit()
    conn.close()
```

### Phase 3: Update Collector

Modify `store_bookmark()` to populate new columns immediately:

```python
def store_bookmark(self, bookmark, cycle, author_info=None, includes=None):
    # Store main bookmark
    cursor.execute("""INSERT OR REPLACE INTO bookmarks (...) VALUES (...)""")

    # Extract and store media
    if includes and "media" in includes:
        for media in includes["media"]:
            if media["media_key"] in bookmark.get("attachments", {}).get("media_keys", []):
                self.store_media(bookmark["id"], media)

    # Extract and store polls
    if includes and "polls" in includes:
        for poll in includes["polls"]:
            if poll["id"] in bookmark.get("attachments", {}).get("poll_ids", []):
                self.store_poll(bookmark["id"], poll)

    # Extract entities
    if "entities" in bookmark:
        self.store_entities(bookmark["id"], bookmark["entities"])
```

## Query Examples (After Implementation)

### Find tweets with videos
```sql
SELECT tweet_id, text, author_username
FROM bookmarks
WHERE has_media = 1
  AND EXISTS (SELECT 1 FROM media WHERE media.tweet_id = bookmarks.tweet_id AND type = 'video')
ORDER BY like_count DESC;
```

### Find most popular tweets by language
```sql
SELECT lang, COUNT(*) as count, AVG(like_count) as avg_likes
FROM bookmarks
GROUP BY lang
ORDER BY count DESC;
```

### Find threads (conversations)
```sql
SELECT conversation_id, COUNT(*) as tweet_count
FROM bookmarks
WHERE conversation_id IS NOT NULL
GROUP BY conversation_id
HAVING tweet_count > 1
ORDER BY tweet_count DESC;
```

### Find tweets with polls
```sql
SELECT b.tweet_id, b.text, p.voting_status, p.total_votes
FROM bookmarks b
JOIN polls p ON b.tweet_id = p.tweet_id
WHERE p.voting_status = 'closed'
ORDER BY p.total_votes DESC;
```

### Find most mentioned users
```sql
SELECT mentioned_username, COUNT(*) as mention_count
FROM mentions
GROUP BY mentioned_username
ORDER BY mention_count DESC
LIMIT 20;
```

### Find most common domains
```sql
SELECT
    SUBSTR(unwound_url,
           INSTR(unwound_url, '://') + 3,
           INSTR(SUBSTR(unwound_url, INSTR(unwound_url, '://') + 3), '/') - 1
    ) as domain,
    COUNT(*) as link_count
FROM urls
WHERE unwound_url IS NOT NULL
GROUP BY domain
ORDER BY link_count DESC
LIMIT 20;
```

## Migration Timeline

1. **Immediate**: Keep collecting with current schema
2. **Phase 1** (1-2 days): Add new tables, test extraction logic
3. **Phase 2** (1 week): Backfill data from existing `full_api_response` JSON
4. **Phase 3** (ongoing): Update collector to populate new schema directly

## Benefits Summary

✅ **Performance**: 10-100x faster queries with indexed columns
✅ **Analytics**: Direct SQL analysis without JSON parsing
✅ **Exports**: Easy CSV/JSON exports per entity type
✅ **Relationships**: Proper foreign keys for data integrity
✅ **Flexibility**: Keep `full_api_response` as backup
✅ **Growth**: Easy to add new extracted fields later

## Considerations

⚠️ **Storage**: ~2-3x more disk space (normalized data)
⚠️ **Complexity**: More tables to maintain
⚠️ **Migration time**: Backfilling existing data takes time
✅ **Worth it**: Better queries and analytics far outweigh costs
