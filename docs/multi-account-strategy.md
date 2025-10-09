# Multi-Account Parallel Collection Strategy

## Overview

X API rate limits apply **per account**, enabling parallel data collection by distributing work across multiple X developer accounts. Each account has independent rate limit quotas.

## Rate Limit Reality (Free Tier)

**Per Account Limits:**
- Total API calls: 1 request per 15 minutes
- All endpoints share this quota (GET, POST, DELETE)
- ~96 API calls per day per account

## Multi-Account Architecture

### Account Roles

**Primary Account (Bookmark Owner)**
- Purpose: Owns the bookmarks to be collected
- Task: Run `collector.py` to fetch and delete bookmarks
- Rate: 1 GET + 100 DELETE = 101 calls per cycle (~25 hours)

**Helper Account #1 (Enrichment)**
- Purpose: Fetch additional context for bookmarks
- Tasks:
  - GET `/tweets/:id` - Full tweet details
  - GET `/tweets/:id/retweeted_by` - Who retweeted
  - GET `/tweets/:id/liking_users` - Who liked
- Rate: Independent 1 call per 15 min

**Helper Account #2 (Thread Context)**
- Purpose: Fetch conversation threads
- Tasks:
  - GET `/tweets/search/recent` with `conversation_id` filter
  - Reconstruct full threads for bookmarked tweets
- Rate: Independent 1 call per 15 min

**Helper Account #3 (Author Profiles)**
- Purpose: Enrich author information
- Tasks:
  - GET `/users/:id` - Author profiles
  - GET `/users/:id/tweets` - Author tweet history
- Rate: Independent 1 call per 15 min

## Implementation Approach

### 1. Multiple .env Configurations

Create separate environment files:

```bash
.env.account1  # Primary - bookmark owner
.env.account2  # Helper - enrichment
.env.account3  # Helper - threads
.env.account4  # Helper - profiles
```

Each contains:
```
CLIENT_ID=<unique_app_client_id>
USER_ACCESS_TOKEN=<account_specific_token>
```

### 2. Parallel Collector Scripts

**collector.py** (Primary Account)
```bash
# Load .env.account1
python3 collector.py --max-cycles 100
```

**enrichment_collector.py** (Helper Account)
```python
# Reads from primary's database
# Fetches additional data using Helper Account #1 credentials
# Stores enriched data back to same database
```

**thread_collector.py** (Helper Account)
```python
# Reads bookmarked tweet IDs from database
# Fetches conversation threads using Helper Account #2
# Stores thread data in related table
```

**profile_collector.py** (Helper Account)
```python
# Reads author IDs from database
# Fetches full profiles using Helper Account #3
# Stores profile data in authors table
```

### 3. Shared Database Architecture

**SQLite Schema:**

```sql
-- Primary table (from collector.py)
CREATE TABLE bookmarks (
    tweet_id TEXT PRIMARY KEY,
    author_id TEXT,
    text TEXT,
    -- ... existing fields
);

-- Enrichment data (from enrichment_collector.py)
CREATE TABLE bookmark_engagement (
    tweet_id TEXT PRIMARY KEY,
    retweet_user_ids TEXT,  -- JSON array
    like_user_ids TEXT,     -- JSON array
    quote_tweets TEXT,      -- JSON array
    collected_at TEXT,
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);

-- Thread data (from thread_collector.py)
CREATE TABLE conversation_threads (
    conversation_id TEXT,
    tweet_id TEXT,
    parent_id TEXT,
    thread_position INTEGER,
    full_text TEXT,
    collected_at TEXT,
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);

-- Author profiles (from profile_collector.py)
CREATE TABLE authors (
    author_id TEXT PRIMARY KEY,
    username TEXT,
    name TEXT,
    bio TEXT,
    followers_count INTEGER,
    profile_data TEXT,  -- Full JSON
    collected_at TEXT
);
```

### 4. Orchestration

**Option A: Manual (Simple)**
```bash
# Terminal 1
python3 collector.py --max-cycles 100

# Terminal 2
python3 enrichment_collector.py --max-cycles 100

# Terminal 3
python3 thread_collector.py --max-cycles 100

# Terminal 4
python3 profile_collector.py --max-cycles 100
```

**Option B: Automated (Advanced)**
```python
# orchestrator.py
import subprocess
import multiprocessing

def run_collector(script, env_file):
    subprocess.run([
        "python3", script,
        "--env-file", env_file,
        "--max-cycles", "100"
    ])

if __name__ == "__main__":
    collectors = [
        ("collector.py", ".env.account1"),
        ("enrichment_collector.py", ".env.account2"),
        ("thread_collector.py", ".env.account3"),
        ("profile_collector.py", ".env.account4"),
    ]

    processes = []
    for script, env in collectors:
        p = multiprocessing.Process(target=run_collector, args=(script, env))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
```

## Timeline Calculations

**Single Account (Baseline)**
- 10,000 bookmarks = ~105 days

**4 Accounts (Parallel)**
- Primary: Collecting 10,000 bookmarks = 105 days
- Helper 1: Enriching 10,000 bookmarks in parallel = 105 days (simultaneous)
- Helper 2: Fetching threads in parallel = 105 days (simultaneous)
- Helper 3: Fetching profiles in parallel = 105 days (simultaneous)

**Result**: Same 105 days wall time, but with 4x more data collected

## Efficiency Optimization

### Smart Work Distribution

**Phase 1: Bookmark Collection** (Days 1-105)
- Account 1: Running `collector.py`
- Accounts 2-4: Idle (waiting for bookmarks to accumulate)

**Phase 2: Enrichment** (Days 1-105, simultaneous)
- Account 1: Still running `collector.py`
- Account 2: Enriching bookmarks as they're collected
- Account 3: Fetching threads for collected bookmarks
- Account 4: Fetching author profiles

### Queue-Based Approach

```python
# Each helper watches the database for new bookmarks
def enrichment_worker():
    while True:
        # Get tweet_ids that don't have enrichment data
        tweets = db.execute("""
            SELECT tweet_id FROM bookmarks
            WHERE tweet_id NOT IN (SELECT tweet_id FROM bookmark_engagement)
            LIMIT 1
        """)

        if tweets:
            enrich_tweet(tweets[0])
            wait_rate_limit()
        else:
            sleep(60)  # Check for new bookmarks every minute
```

## Account Setup Requirements

### For Each Helper Account

1. **Create X Account** (email/phone verification required)
2. **Apply for Developer Access** at developer.x.com
3. **Create App** in developer portal
4. **Configure OAuth 2.0**
   - Callback: http://localhost:8080/callback
   - Scopes: tweet.read, users.read, bookmark.read (if accessing bookmarks)
5. **Run OAuth Flow**
   ```bash
   CLIENT_ID=<helper_client_id> python3 oauth2_pkce.py
   ```
6. **Save Token** to respective .env.accountN file

## Legal & ToS Considerations

✅ **Allowed:**
- Multiple developer accounts for personal projects
- Parallel data collection using own accounts
- Storing data locally for personal use

⚠️ **Be Cautious:**
- Don't violate X API ToS (rate limit circumvention via abuse)
- Keep data private (don't redistribute)
- Use legitimate developer accounts (not throwaway/fake)

## Benefits

1. **4x Data Coverage** - Get engagement, threads, profiles alongside bookmarks
2. **Same Timeline** - All data collected in same time window
3. **Richer Archive** - Complete context for every bookmark
4. **Independent Failure** - One account failing doesn't stop others
5. **Scalable** - Add more accounts = more parallel work

## Limitations

1. **Setup Overhead** - Each account needs developer approval
2. **Token Management** - Multiple OAuth flows to maintain
3. **Still Slow** - Free tier is very restrictive per account
4. **Coordination** - Need to manage multiple processes/scripts

## Future Enhancements

- **Auto-retry** on token expiration
- **Progress dashboard** showing all collectors
- **Smart prioritization** (enrich popular tweets first)
- **Incremental updates** (re-fetch engagement periodically)
- **Export utilities** (full data to JSON/CSV)

## Conclusion

Multi-account strategy doesn't speed up collection time but maximizes data richness. In the same 105 days, you can collect:
- All bookmarks (primary account)
- All engagement data (helper #1)
- All conversation threads (helper #2)
- All author profiles (helper #3)

This creates a **comprehensive archive** of your bookmarked content and its complete context.
