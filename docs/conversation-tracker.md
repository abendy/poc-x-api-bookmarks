# Conversation Tracker

## Overview

Track the full context and evolution of important bookmarked tweets by monitoring:
- Popular replies and quotes
- Replies/quotes from people you follow
- Keyword-based related tweets
- Conversation evolution over time

## Use Cases

1. **Breaking News** - Track a developing story through replies and quotes
2. **Viral Threads** - Monitor engagement and community response
3. **Research Topics** - Build comprehensive view of discussions
4. **Network Analysis** - See how your network engages with content
5. **Content Discovery** - Find valuable additions to original bookmark

## Architecture

### Flagging System

```sql
-- Add to bookmarks table
ALTER TABLE bookmarks ADD COLUMN tracked BOOLEAN DEFAULT 0;
ALTER TABLE bookmarks ADD COLUMN tracking_config TEXT;  -- JSON config

-- Tracking configuration example
{
    "track_popular_replies": true,
    "popularity_threshold": 100,        -- Min likes for reply
    "track_following_replies": true,
    "track_quotes": true,
    "keywords": ["AI", "LLM", "GPT"],   -- Optional keyword filter
    "max_depth": 2,                     -- Reply chain depth
    "check_frequency_hours": 24,        -- How often to check
    "last_checked": "2025-10-09T10:00:00Z"
}
```

### Conversation Data Model

```sql
-- Tracked conversations
CREATE TABLE tracked_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_tweet_id TEXT NOT NULL,        -- The flagged bookmark
    conversation_id TEXT,                -- X API conversation_id
    tracking_started_at TEXT,
    last_updated_at TEXT,
    total_replies_tracked INTEGER DEFAULT 0,
    total_quotes_tracked INTEGER DEFAULT 0,

    FOREIGN KEY (root_tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_root_tweet (root_tweet_id),
    INDEX idx_conversation_id (conversation_id)
);

-- Reply/quote tweets related to tracked conversation
CREATE TABLE conversation_tweets (
    tweet_id TEXT PRIMARY KEY,
    root_tweet_id TEXT NOT NULL,        -- Links back to flagged bookmark
    parent_tweet_id TEXT,                -- Direct parent (for reply chains)
    conversation_id TEXT,
    author_id TEXT,
    author_username TEXT,
    author_name TEXT,
    author_is_following BOOLEAN,        -- Is user following this author?

    text TEXT,
    created_at TEXT,

    -- Type
    relationship_type TEXT,              -- reply, quote, retweet
    depth_level INTEGER,                 -- How many replies deep

    -- Metrics
    like_count INTEGER,
    retweet_count INTEGER,
    reply_count INTEGER,
    quote_count INTEGER,

    -- Tracking metadata
    discovered_at TEXT,
    discovery_method TEXT,               -- popular_reply, following_reply, keyword_search, quote
    matched_keywords TEXT,               -- JSON array if found via keywords

    -- Full data
    full_api_response TEXT,

    FOREIGN KEY (root_tweet_id) REFERENCES bookmarks(tweet_id),
    INDEX idx_root (root_tweet_id),
    INDEX idx_author (author_id),
    INDEX idx_relationship (relationship_type),
    INDEX idx_following (author_is_following),
    INDEX idx_likes (like_count)
);

-- Keyword matches for conversation tracking
CREATE TABLE conversation_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_tweet_id TEXT NOT NULL,
    tweet_id TEXT NOT NULL,              -- The reply/quote that matched
    keyword TEXT NOT NULL,
    matched_at TEXT,

    FOREIGN KEY (root_tweet_id) REFERENCES bookmarks(tweet_id),
    FOREIGN KEY (tweet_id) REFERENCES conversation_tweets(tweet_id),
    INDEX idx_keyword (keyword),
    INDEX idx_root (root_tweet_id)
);
```

## Implementation

### Conversation Tracker Class

```python
class ConversationTracker:
    def __init__(self, db_path="complete_bookmarks.db", account_tokens=None):
        """
        Args:
            account_tokens: Dict of helper account tokens for parallel fetching
                           {"helper1": "token1", "helper2": "token2"}
        """
        self.db_path = db_path
        self.account_tokens = account_tokens or {}
        self.primary_token = os.environ.get("USER_ACCESS_TOKEN")

    def flag_for_tracking(self, tweet_id, config=None):
        """Flag a bookmark for conversation tracking"""
        default_config = {
            "track_popular_replies": True,
            "popularity_threshold": 100,
            "track_following_replies": True,
            "track_quotes": True,
            "keywords": [],
            "max_depth": 2,
            "check_frequency_hours": 24,
            "last_checked": None
        }

        tracking_config = {**default_config, **(config or {})}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Update bookmark
        cursor.execute(
            "UPDATE bookmarks SET tracked = 1, tracking_config = ? WHERE tweet_id = ?",
            (json.dumps(tracking_config), tweet_id)
        )

        # Get conversation_id from bookmark
        cursor.execute(
            "SELECT full_api_response FROM bookmarks WHERE tweet_id = ?",
            (tweet_id,)
        )
        result = cursor.fetchone()
        if result:
            data = json.loads(result[0])
            conversation_id = data.get("conversation_id", tweet_id)

            # Create tracked conversation
            cursor.execute("""
                INSERT OR REPLACE INTO tracked_conversations
                (root_tweet_id, conversation_id, tracking_started_at)
                VALUES (?, ?, ?)
            """, (tweet_id, conversation_id, datetime.now().isoformat()))

        conn.commit()
        conn.close()

        print(f"✓ Tweet {tweet_id} flagged for conversation tracking")

    def get_following_list(self):
        """Get list of users the main account follows"""
        # GET /2/users/:id/following
        # Cache this as it's expensive (75 reqs per user for large lists)
        # Store in a separate table: user_following(user_id, following_user_id)
        pass

    def search_conversation_replies(self, conversation_id, token):
        """Search for replies in a conversation"""
        # GET /2/tweets/search/recent
        # query: conversation_id:{conversation_id}
        # Returns tweets in the conversation thread
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "query": f"conversation_id:{conversation_id}",
            "tweet.fields": "author_id,created_at,conversation_id,public_metrics,referenced_tweets",
            "expansions": "author_id,referenced_tweets.id",
            "max_results": 100,
        }

        response = requests.get(url, headers=headers, params=params)
        return response.json() if response.status_code == 200 else None

    def get_quote_tweets(self, tweet_id, token):
        """Get quote tweets of a specific tweet"""
        # GET /2/tweets/:id/quote_tweets
        url = f"https://api.twitter.com/2/tweets/{tweet_id}/quote_tweets"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "tweet.fields": "author_id,created_at,public_metrics",
            "expansions": "author_id",
            "max_results": 100,
        }

        response = requests.get(url, headers=headers, params=params)
        return response.json() if response.status_code == 200 else None

    def keyword_search(self, keywords, since_id=None, token=None):
        """Search for tweets matching keywords"""
        # GET /2/tweets/search/recent
        # query: (keyword1 OR keyword2 OR keyword3)
        # Can combine with conversation_id or from:username
        query = " OR ".join(keywords)

        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {token or self.primary_token}"}
        params = {
            "query": query,
            "tweet.fields": "author_id,created_at,conversation_id,public_metrics,referenced_tweets",
            "expansions": "author_id,referenced_tweets.id",
            "max_results": 100,
        }

        if since_id:
            params["since_id"] = since_id

        response = requests.get(url, headers=headers, params=params)
        return response.json() if response.status_code == 200 else None

    def track_conversation(self, root_tweet_id):
        """Execute tracking for a flagged conversation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get tracking config
        cursor.execute(
            "SELECT tracking_config, full_api_response FROM bookmarks WHERE tweet_id = ?",
            (root_tweet_id,)
        )
        result = cursor.fetchone()
        if not result:
            print(f"Tweet {root_tweet_id} not found")
            return

        config = json.loads(result[0])
        bookmark_data = json.loads(result[1])
        conversation_id = bookmark_data.get("conversation_id", root_tweet_id)

        print(f"Tracking conversation for tweet {root_tweet_id}")
        print(f"Config: {config}")

        # 1. Get replies in conversation
        if config.get("track_popular_replies") or config.get("track_following_replies"):
            print("Fetching conversation replies...")
            replies = self.search_conversation_replies(
                conversation_id,
                self.account_tokens.get("helper1", self.primary_token)
            )

            if replies and "data" in replies:
                self.process_replies(
                    root_tweet_id,
                    replies["data"],
                    config,
                    replies.get("includes", {})
                )

        # 2. Get quote tweets
        if config.get("track_quotes"):
            print("Fetching quote tweets...")
            quotes = self.get_quote_tweets(
                root_tweet_id,
                self.account_tokens.get("helper2", self.primary_token)
            )

            if quotes and "data" in quotes:
                self.process_quotes(
                    root_tweet_id,
                    quotes["data"],
                    config,
                    quotes.get("includes", {})
                )

        # 3. Keyword search (if configured)
        if config.get("keywords"):
            print(f"Searching for keywords: {config['keywords']}")
            keyword_results = self.keyword_search(
                config["keywords"],
                token=self.account_tokens.get("helper3", self.primary_token)
            )

            if keyword_results and "data" in keyword_results:
                self.process_keyword_matches(
                    root_tweet_id,
                    keyword_results["data"],
                    config["keywords"],
                    keyword_results.get("includes", {})
                )

        # Update last checked time
        config["last_checked"] = datetime.now().isoformat()
        cursor.execute(
            "UPDATE bookmarks SET tracking_config = ? WHERE tweet_id = ?",
            (json.dumps(config), root_tweet_id)
        )

        conn.commit()
        conn.close()

        print(f"✓ Conversation tracking complete for {root_tweet_id}")

    def process_replies(self, root_tweet_id, replies, config, includes):
        """Filter and store relevant replies"""
        following_list = self.get_following_list()  # Cached
        popularity_threshold = config.get("popularity_threshold", 100)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for reply in replies:
            author_id = reply.get("author_id")
            likes = reply.get("public_metrics", {}).get("like_count", 0)

            # Determine if we should track this reply
            is_following = author_id in following_list
            is_popular = likes >= popularity_threshold

            should_track = (
                (config.get("track_following_replies") and is_following) or
                (config.get("track_popular_replies") and is_popular)
            )

            if should_track:
                discovery_method = []
                if is_popular:
                    discovery_method.append("popular_reply")
                if is_following:
                    discovery_method.append("following_reply")

                self.store_conversation_tweet(
                    reply,
                    root_tweet_id,
                    "reply",
                    ",".join(discovery_method),
                    is_following,
                    includes
                )

        conn.commit()
        conn.close()

    def process_quotes(self, root_tweet_id, quotes, config, includes):
        """Store quote tweets"""
        following_list = self.get_following_list()

        for quote in quotes:
            author_id = quote.get("author_id")
            is_following = author_id in following_list

            self.store_conversation_tweet(
                quote,
                root_tweet_id,
                "quote",
                "quote_tweet",
                is_following,
                includes
            )

    def process_keyword_matches(self, root_tweet_id, tweets, keywords, includes):
        """Store tweets that match keywords"""
        following_list = self.get_following_list()

        for tweet in tweets:
            text = tweet.get("text", "").lower()
            matched = [kw for kw in keywords if kw.lower() in text]

            if matched:
                author_id = tweet.get("author_id")
                is_following = author_id in following_list

                tweet_id = self.store_conversation_tweet(
                    tweet,
                    root_tweet_id,
                    "keyword_match",
                    "keyword_search",
                    is_following,
                    includes,
                    matched_keywords=matched
                )

                # Store keyword matches
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                for kw in matched:
                    cursor.execute("""
                        INSERT INTO conversation_keywords
                        (root_tweet_id, tweet_id, keyword, matched_at)
                        VALUES (?, ?, ?, ?)
                    """, (root_tweet_id, tweet_id, kw, datetime.now().isoformat()))
                conn.commit()
                conn.close()

    def store_conversation_tweet(self, tweet, root_tweet_id, rel_type,
                                   discovery_method, is_following, includes,
                                   matched_keywords=None):
        """Store a conversation tweet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get author info from includes
        author_id = tweet.get("author_id")
        author = {}
        if includes and "users" in includes:
            author = next((u for u in includes["users"] if u["id"] == author_id), {})

        cursor.execute("""
            INSERT OR REPLACE INTO conversation_tweets
            (tweet_id, root_tweet_id, conversation_id, author_id, author_username,
             author_name, author_is_following, text, created_at, relationship_type,
             like_count, retweet_count, reply_count, quote_count,
             discovered_at, discovery_method, matched_keywords, full_api_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tweet["id"],
            root_tweet_id,
            tweet.get("conversation_id"),
            author_id,
            author.get("username"),
            author.get("name"),
            is_following,
            tweet.get("text"),
            tweet.get("created_at"),
            rel_type,
            tweet.get("public_metrics", {}).get("like_count", 0),
            tweet.get("public_metrics", {}).get("retweet_count", 0),
            tweet.get("public_metrics", {}).get("reply_count", 0),
            tweet.get("public_metrics", {}).get("quote_count", 0),
            datetime.now().isoformat(),
            discovery_method,
            json.dumps(matched_keywords) if matched_keywords else None,
            json.dumps(tweet)
        ))

        conn.commit()
        conn.close()

        return tweet["id"]

    def run_tracking_cycle(self):
        """Check all tracked conversations and update if needed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all tracked bookmarks that need checking
        cursor.execute("""
            SELECT tweet_id, tracking_config
            FROM bookmarks
            WHERE tracked = 1
        """)

        tracked = cursor.fetchall()
        conn.close()

        print(f"Found {len(tracked)} tracked conversations")

        for tweet_id, config_json in tracked:
            config = json.loads(config_json)

            # Check if it's time to update
            last_checked = config.get("last_checked")
            check_frequency = config.get("check_frequency_hours", 24)

            if last_checked:
                last_check_time = datetime.fromisoformat(last_checked)
                hours_since = (datetime.now() - last_check_time).total_seconds() / 3600

                if hours_since < check_frequency:
                    print(f"Skipping {tweet_id} (checked {hours_since:.1f}h ago)")
                    continue

            print(f"\nTracking conversation: {tweet_id}")
            self.track_conversation(tweet_id)

            # Rate limit between conversations
            time.sleep(15 * 60)  # 15 minutes
```

## Usage Examples

### Flag a Breaking News Tweet

```python
tracker = ConversationTracker(account_tokens={
    "helper1": os.environ.get("HELPER1_TOKEN"),
    "helper2": os.environ.get("HELPER2_TOKEN"),
    "helper3": os.environ.get("HELPER3_TOKEN"),
})

# Flag important breaking news
tracker.flag_for_tracking(
    "1234567890",
    config={
        "track_popular_replies": True,
        "popularity_threshold": 500,  # High threshold for viral content
        "track_following_replies": True,
        "track_quotes": True,
        "keywords": ["breaking", "confirmed", "update"],
        "check_frequency_hours": 2,  # Check every 2 hours
    }
)

# Run tracking
tracker.track_conversation("1234567890")
```

### Research Topic Tracking

```python
# Flag a key paper/article
tracker.flag_for_tracking(
    "0987654321",
    config={
        "track_popular_replies": True,
        "popularity_threshold": 50,
        "track_following_replies": True,
        "track_quotes": True,
        "keywords": ["LLM", "GPT", "transformer", "attention"],
        "check_frequency_hours": 24,
    }
)
```

### Automated Background Tracking

```python
# Run as background job (cron/systemd)
def main():
    tracker = ConversationTracker(account_tokens={...})
    tracker.run_tracking_cycle()

if __name__ == "__main__":
    while True:
        main()
        time.sleep(3600)  # Check every hour
```

## Query Examples

### Find Most Active Conversations

```sql
SELECT
    b.tweet_id,
    b.text,
    COUNT(ct.tweet_id) as response_count,
    SUM(ct.like_count) as total_engagement
FROM bookmarks b
JOIN conversation_tweets ct ON b.tweet_id = ct.root_tweet_id
WHERE b.tracked = 1
GROUP BY b.tweet_id
ORDER BY response_count DESC
LIMIT 20;
```

### Popular Replies from Network

```sql
SELECT
    ct.author_username,
    ct.text,
    ct.like_count,
    b.text as original_tweet
FROM conversation_tweets ct
JOIN bookmarks b ON ct.root_tweet_id = b.tweet_id
WHERE ct.author_is_following = 1
  AND ct.relationship_type = 'reply'
ORDER BY ct.like_count DESC
LIMIT 50;
```

### Keyword Match Analysis

```sql
SELECT
    ck.keyword,
    COUNT(DISTINCT ck.tweet_id) as match_count,
    COUNT(DISTINCT ck.root_tweet_id) as conversations
FROM conversation_keywords ck
GROUP BY ck.keyword
ORDER BY match_count DESC;
```

### Find Related Discussions

```sql
-- Find tweets that quote multiple tracked bookmarks (related discussions)
SELECT
    ct.tweet_id,
    ct.text,
    COUNT(DISTINCT ct.root_tweet_id) as references_count
FROM conversation_tweets ct
WHERE ct.relationship_type = 'quote'
GROUP BY ct.tweet_id
HAVING references_count > 1
ORDER BY references_count DESC;
```

## Multi-Account Optimization

Use helper accounts to parallelize tracking:

- **Helper 1**: Fetch conversation replies
- **Helper 2**: Fetch quote tweets
- **Helper 3**: Keyword searches
- **Primary**: Flag management and coordination

This allows 4x faster tracking (4 conversations in parallel) within rate limits.

## CLI Tool

```bash
# Flag a tweet for tracking
python3 tracker.py flag 1234567890 --popular --following --keywords "AI,LLM"

# Track all flagged conversations
python3 tracker.py track-all

# Get conversation report
python3 tracker.py report 1234567890

# List all tracked conversations
python3 tracker.py list
```

## Benefits

✅ **Context Preservation** - Complete conversation history
✅ **Network Insights** - See how your network engages
✅ **Trend Detection** - Keyword tracking finds related discussions
✅ **Research Tool** - Build comprehensive view of topics
✅ **Automated** - Background monitoring without manual work
✅ **Scalable** - Multi-account support for parallel tracking

## Future Enhancements

- **Sentiment analysis** on replies
- **Author clustering** (find common participants)
- **Timeline visualization** of conversation evolution
- **Alert system** for high-engagement replies
- **Export to thread readers** (Twitter/X thread unrollers)
