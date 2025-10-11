#!/usr/bin/env python3
"""
X API Complete Bookmark Collector.

Systematically collects ALL bookmarks using delete-to-paginate methodology.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

USER_ACCESS_TOKEN = os.environ.get("USER_ACCESS_TOKEN")


class CompleteBookmarkCollector:
    """
    Systematically collects all X (Twitter) bookmarks using a delete-to-paginate methodology,
    storing them in a local SQLite database and supporting test mode for safe operations.
    """  # noqa: D205

    def __init__(self, db_path="complete_bookmarks.db", test_mode=False):
        """
        Initialize the CompleteBookmarkCollector.

        Args:
            db_path (str): Path to the SQLite database file.
            test_mode (bool): If True, bookmarks will not be deleted.
        """
        self.db_path = db_path
        self.user_access_token = USER_ACCESS_TOKEN
        self.user_id = None
        self.test_mode = test_mode
        self.setup_local_storage()

    def setup_local_storage(self):
        """Initialize local SQLite database for bookmark storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                tweet_id TEXT PRIMARY KEY,
                author_id TEXT,
                author_username TEXT,
                author_name TEXT,
                text TEXT,
                created_at TEXT,
                bookmark_url TEXT,
                public_metrics TEXT,
                collected_at TEXT,
                collection_cycle INTEGER,
                full_api_response TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_number INTEGER,
                bookmarks_found INTEGER,
                bookmarks_deleted INTEGER,
                cycle_start_time TEXT,
                cycle_end_time TEXT,
                cycle_duration_hours REAL,
                total_collected INTEGER
            )
        """
        )

        conn.commit()
        conn.close()

    def create_headers(self):
        """Create OAuth 2.0 User Context authentication headers."""
        return {
            "Authorization": f"Bearer {self.user_access_token}",
            "Content-Type": "application/json",
        }

    def get_user_id(self):
        """Get the current user's ID."""
        if self.user_id:
            return self.user_id

        url = "https://api.twitter.com/2/users/me"
        headers = self.create_headers()

        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.user_id = data.get("data", {}).get("id")
                return self.user_id
            else:
                print(f"Error getting user ID: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Error getting user ID: {e}")
            return None

    def get_bookmarks(self, max_results=100):
        """Fetch bookmarks from X API."""
        if not self.user_access_token:
            print("Error: USER_ACCESS_TOKEN not found")
            return None

        user_id = self.get_user_id()
        if not user_id:
            return None

        url = f"https://api.twitter.com/2/users/{user_id}/bookmarks"
        headers = self.create_headers()
        params = {
            # Request all available tweet fields
            "tweet.fields": ",".join(
                [
                    "attachments",
                    "author_id",
                    "context_annotations",
                    "conversation_id",
                    "created_at",
                    "edit_controls",
                    "edit_history_tweet_ids",
                    "entities",
                    "geo",
                    "id",
                    "in_reply_to_user_id",
                    "lang",
                    "possibly_sensitive",
                    "public_metrics",
                    "referenced_tweets",
                    "reply_settings",
                    "source",
                    "text",
                    "withheld",
                ]
            ),
            # Request all available expansions
            "expansions": ",".join(
                [
                    "attachments.media_keys",
                    "attachments.poll_ids",
                    "author_id",
                    "edit_history_tweet_ids",
                    "entities.mentions.username",
                    "geo.place_id",
                    "in_reply_to_user_id",
                    "referenced_tweets.id",
                    "referenced_tweets.id.author_id",
                ]
            ),
            # Request all available user fields
            "user.fields": ",".join(
                [
                    "created_at",
                    "description",
                    "entities",
                    "id",
                    "location",
                    "name",
                    "pinned_tweet_id",
                    "profile_image_url",
                    "protected",
                    "public_metrics",
                    "url",
                    "username",
                    "verified",
                    "verified_type",
                    "withheld",
                ]
            ),
            # Request all available media fields
            "media.fields": ",".join(
                [
                    "alt_text",
                    "duration_ms",
                    "height",
                    "media_key",
                    "preview_image_url",
                    "public_metrics",
                    "type",
                    "url",
                    "variants",
                    "width",
                ]
            ),
            # Request all available place fields
            "place.fields": ",".join(
                [
                    "contained_within",
                    "country",
                    "country_code",
                    "full_name",
                    "geo",
                    "id",
                    "name",
                    "place_type",
                ]
            ),
            # Request all available poll fields
            "poll.fields": ",".join(
                [
                    "duration_minutes",
                    "end_datetime",
                    "id",
                    "options",
                    "voting_status",
                ]
            ),
            "max_results": min(max_results, 100),
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time:
                    print(f"Rate limit hit. Resets at: {time.ctime(int(reset_time))}")
                return None
            else:
                print(f"Error fetching bookmarks: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Error fetching bookmarks: {e}")
            return None

    def delete_bookmark(self, tweet_id):
        """Delete a specific bookmark."""
        user_id = self.get_user_id()
        if not user_id:
            return False

        url = f"https://api.twitter.com/2/users/{user_id}/bookmarks/{tweet_id}"
        headers = self.create_headers()

        try:
            response = requests.delete(url, headers=headers, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Error deleting bookmark {tweet_id}: {e}")
            return False

    def store_bookmark(self, bookmark, cycle, author_info=None):
        """Store bookmark in local database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO bookmarks
            (tweet_id, author_id, author_username, author_name, text, created_at,
             bookmark_url, public_metrics, collected_at, collection_cycle, full_api_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                bookmark["id"],
                bookmark.get("author_id"),
                author_info.get("username") if author_info else "unknown",
                author_info.get("name") if author_info else "Unknown",
                bookmark.get("text"),
                bookmark.get("created_at"),
                f"https://x.com/user/status/{bookmark['id']}",
                json.dumps(bookmark.get("public_metrics", {})),
                datetime.now().isoformat(),
                cycle,
                json.dumps(bookmark),
            ),
        )

        conn.commit()
        conn.close()

    def verify_bookmark_stored(self, tweet_id):
        """Verify that a bookmark exists in local database before deletion."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tweet_id FROM bookmarks WHERE tweet_id = ?", (tweet_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def execute_collection_cycle(self, cycle_number):
        """Execute one complete collection cycle: GET → Store → DELETE."""
        cycle_start = datetime.now()
        print(f"\n{'=' * 60}")
        print(f"Starting Collection Cycle {cycle_number}")
        if self.test_mode:
            print("** TEST MODE - No bookmarks will be deleted **")
        print(f"Time: {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        # Step 1: GET bookmarks
        print("Step 1: Fetching bookmarks...")
        try:
            response = self.get_bookmarks(max_results=100)
            self.wait_rate_limit()
        except Exception as e:
            print(f"Error fetching bookmarks: {e}")
            return {"status": "error", "error": str(e)}

        if not response or not response.get("data"):
            print("No bookmarks found - collection complete!")
            return {"status": "complete", "bookmarks_found": 0}

        bookmarks = response["data"]
        bookmarks_found = len(bookmarks)
        print(f"Found {bookmarks_found} bookmarks")

        # Build author lookup
        users = {}
        if "includes" in response and "users" in response["includes"]:
            users = {user["id"]: user for user in response["includes"]["users"]}

        # Step 2: Store all bookmarks
        print("Step 2: Storing bookmarks locally...")
        for i, bookmark in enumerate(bookmarks, 1):
            author_id = bookmark.get("author_id")
            author_info = users.get(author_id, {})
            self.store_bookmark(bookmark, cycle_number, author_info)
            print(f"Stored bookmark {i}/{bookmarks_found}: {bookmark['id']}")

        # Step 3: Delete all bookmarks (skip in test mode)
        deleted_count = 0
        if self.test_mode:
            print("Step 3: SKIPPED - Test mode enabled (no deletions)")
            deleted_count = 0
        else:
            print("Step 3: Deleting bookmarks to expose next batch...")
            for i, bookmark in enumerate(bookmarks, 1):
                try:
                    tweet_id = bookmark["id"]

                    # FAIL-SAFE: Verify local copy exists before deletion
                    if not self.verify_bookmark_stored(tweet_id):
                        print(f"⚠️  FAIL-SAFE: {tweet_id} not verified in DB, skipping deletion")
                        continue

                    print(f"Deleting bookmark {i}/{bookmarks_found}: {tweet_id} (verified in DB)")
                    success = self.delete_bookmark(tweet_id)
                    if success:
                        deleted_count += 1
                    else:
                        print(f"Failed to delete bookmark {tweet_id}")

                    if i < bookmarks_found:  # Don't wait after last deletion
                        self.wait_rate_limit()

                except Exception as e:
                    print(f"Error deleting bookmark {bookmark['id']}: {e}")
                    break

        cycle_end = datetime.now()
        cycle_duration = cycle_end - cycle_start

        # Log cycle progress
        self.log_cycle_progress(
            cycle_number, bookmarks_found, deleted_count, cycle_start, cycle_end, cycle_duration
        )

        print(f"\nCycle {cycle_number} Complete:")
        print(f"  Bookmarks found: {bookmarks_found}")
        print(f"  Bookmarks deleted: {deleted_count}")
        print(f"  Duration: {cycle_duration}")

        return {
            "status": "continue",
            "bookmarks_found": bookmarks_found,
            "bookmarks_deleted": deleted_count,
            "cycle_duration": cycle_duration,
        }

    def log_cycle_progress(self, cycle, found, deleted, start_time, end_time, duration: timedelta):
        """Log cycle progress to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        total_collected = self.get_total_collected()

        cursor.execute(
            """
            INSERT INTO collection_progress
            (cycle_number, bookmarks_found, bookmarks_deleted, cycle_start_time,
             cycle_end_time, cycle_duration_hours, total_collected)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                cycle,
                found,
                deleted,
                start_time.isoformat(),
                end_time.isoformat(),
                duration.total_seconds() / 3600,
                total_collected,
            ),
        )

        conn.commit()
        conn.close()

    def get_total_collected(self):
        """Get total number of bookmarks collected."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bookmarks")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def wait_rate_limit(self):
        """Wait for rate limit reset (15 minutes)."""
        wait_time = 15 * 60  # 15 minutes in seconds
        print(f"\nWaiting {wait_time // 60} minutes for rate limit reset...")

        # Show countdown every minute
        for remaining in range(wait_time, 0, -60):
            minutes = remaining // 60
            seconds = remaining % 60
            print(f"Time remaining: {minutes:02d}:{seconds:02d}")
            time.sleep(60 if remaining > 60 else remaining)

        print("Rate limit wait complete!\n")

    def run_complete_collection(self, max_cycles=1000):
        """Execute complete bookmark collection process."""
        print("Starting Complete Bookmark Collection")
        if self.test_mode:
            print("** TEST MODE ENABLED - Bookmarks will NOT be deleted **")
        print(f"Maximum cycles: {max_cycles}")
        if not self.test_mode:
            print("Estimated time per cycle: ~25 hours")
        print("=" * 60)

        cycle = 1
        while cycle <= max_cycles:
            result = self.execute_collection_cycle(cycle)

            if result["status"] == "complete":
                print("\n🎉 Collection Complete!")
                break
            elif result["status"] == "error":
                print(f"\n❌ Error in cycle {cycle}: {result['error']}")
                break

            total_collected = self.get_total_collected()
            print("\nProgress Summary:")
            print(f"  Cycles completed: {cycle}")
            print(f"  Total bookmarks collected: {total_collected}")
            print(f"  Average bookmarks per cycle: {total_collected / cycle:.1f}")

            cycle += 1

        # Final summary
        self.print_final_summary()

    def print_final_summary(self):
        """Print final collection summary."""
        total_collected = self.get_total_collected()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*),
                   SUM(cycle_duration_hours),
                   MIN(cycle_start_time),
                   MAX(cycle_end_time)
            FROM collection_progress
        """
        )
        result = cursor.fetchone()
        cycles = result[0] if result[0] else 0
        total_hours = result[1] if result[1] else 0
        start_time = result[2]
        end_time = result[3]
        conn.close()

        print("\n" + "=" * 60)
        print("FINAL COLLECTION SUMMARY")
        print("=" * 60)
        print(f"Total bookmarks collected: {total_collected}")
        print(f"Total cycles completed: {cycles}")
        print(f"Total time invested: {total_hours:.1f} hours ({total_hours / 24:.1f} days)")
        if start_time and end_time:
            print(f"Collection period: {start_time} to {end_time}")
        if cycles > 0:
            print(f"Average bookmarks per cycle: {total_collected / cycles:.1f}")
        print(f"Collection database: {self.db_path}")
        print("=" * 60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Complete X API Bookmark Collector")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=1000,
        help="Maximum number of collection cycles (default: 1000)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="complete_bookmarks.db",
        help="Path to SQLite database (default: complete_bookmarks.db)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Test mode: fetch and store bookmarks but do NOT delete them",
    )

    args = parser.parse_args()

    collector = CompleteBookmarkCollector(db_path=args.db_path, test_mode=args.test_mode)
    collector.run_complete_collection(max_cycles=args.max_cycles)


if __name__ == "__main__":
    main()
