import requests
from requests_oauthlib import OAuth1
import json
import sys
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Your X API credentials from environment variables
API_KEY = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")

def check_credentials():
    """Verify all required credentials are available"""
    required_vars = ["API_KEY", "API_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Please create a .env file with:")
        for var in required_vars:
            print(f"  {var}=your_value_here")
        return False
    return True

def handle_rate_limit_response(response):
    """Handle rate limit responses and provide helpful information"""
    if response.status_code == 429:
        reset_time = response.headers.get('x-rate-limit-reset')
        if reset_time:
            reset_timestamp = int(reset_time)
            current_time = int(time.time())
            wait_time = reset_timestamp - current_time
            print(f"Rate limit exceeded. Reset in {wait_time} seconds ({time.ctime(reset_timestamp)})")
        else:
            print("Rate limit exceeded. Please wait 15 minutes before trying again.")
        return True
    return False

def get_bookmarks(max_results=25, show_rate_limit_info=True):
    """Fetch user bookmarks from X API with rate limiting considerations"""
    
    if not check_credentials():
        return None
    
    # Set up OAuth 1.0a authentication
    auth = OAuth1(
        API_KEY,
        client_secret=API_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET
    )
    
    # API endpoint
    url = "https://api.twitter.com/2/users/me/bookmarks"
    
    # Parameters for the request - being conservative with max_results
    params = {
        "tweet.fields": "created_at,author_id,text,public_metrics",
        "expansions": "author_id",
        "user.fields": "name,username,verified",
        "max_results": min(max_results, 100)  # API max is 100, but we default to 25
    }
    
    try:
        print(f"Fetching your X bookmarks (max {max_results})...")
        if show_rate_limit_info:
            print("Rate limit: 75 requests per 15 minutes for bookmarks endpoint")
        
        response = requests.get(url, auth=auth, params=params)
        
        # Handle rate limiting
        if handle_rate_limit_response(response):
            return None
        
        # Show rate limit info
        if show_rate_limit_info:
            remaining = response.headers.get('x-rate-limit-remaining')
            reset_time = response.headers.get('x-rate-limit-reset')
            if remaining and reset_time:
                print(f"Rate limit remaining: {remaining}/75 (resets at {time.ctime(int(reset_time))})")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if there are bookmarks
            if 'data' in data and data['data']:
                bookmarks = data['data']
                users = {user['id']: user for user in data.get('includes', {}).get('users', [])}
                
                print(f"\nFound {len(bookmarks)} bookmarks:")
                print("=" * 60)
                
                for i, bookmark in enumerate(bookmarks, 1):
                    author_id = bookmark.get('author_id')
                    author = users.get(author_id, {})
                    author_name = author.get('name', 'Unknown')
                    author_username = author.get('username', 'unknown')
                    
                    print(f"\n{i}. Tweet by @{author_username} ({author_name})")
                    print(f"   Created: {bookmark.get('created_at', 'Unknown')}")
                    
                    # Handle text display more carefully
                    text = bookmark.get('text', 'No text')
                    if len(text) > 100:
                        print(f"   Text: {text[:100]}...")
                    else:
                        print(f"   Text: {text}")
                    
                    metrics = bookmark.get('public_metrics', {})
                    if metrics:
                        print(f"   Likes: {metrics.get('like_count', 0)}, Retweets: {metrics.get('retweet_count', 0)}")
                    
                    print(f"   Tweet ID: {bookmark.get('id')}")
                
                # Check if there are more pages
                if 'meta' in data and 'next_token' in data['meta']:
                    print("\nNote: There are more bookmarks available.")
                    print(f"Next token: {data['meta']['next_token']}")
                    print("Run again with --paginate to fetch more (uses additional API calls)")
                
                return data
                
            else:
                print("No bookmarks found or no data returned.")
                return data
                
        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error fetching bookmarks: {e}")
        return None

def get_bookmarks_json(max_results=25):
    """Fetch bookmarks and return raw JSON"""
    if not check_credentials():
        return None
        
    auth = OAuth1(
        API_KEY,
        client_secret=API_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET
    )
    
    url = "https://api.twitter.com/2/users/me/bookmarks"
    params = {
        "tweet.fields": "created_at,author_id,text,public_metrics",
        "expansions": "author_id",
        "user.fields": "name,username,verified",
        "max_results": min(max_results, 100)
    }
    
    try:
        response = requests.get(url, auth=auth, params=params)
        
        if handle_rate_limit_response(response):
            return None
            
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def show_usage():
    """Show usage instructions"""
    print("""
Usage: python3 bookmarks.py [options]

Options:
  --json                 Output raw JSON
  --max-results N        Fetch N bookmarks (default: 25, max: 100)
  --quiet               Don't show rate limit info
  --help                Show this help

Examples:
  python3 bookmarks.py                    # Fetch 25 bookmarks with pretty output
  python3 bookmarks.py --max-results 50   # Fetch 50 bookmarks
  python3 bookmarks.py --json             # Get raw JSON output
  python3 bookmarks.py --json --quiet     # JSON output without rate limit info

Rate Limits:
  - Bookmarks endpoint: 75 requests per 15 minutes
  - Be conservative with requests to avoid hitting limits
  - Use --max-results to control how many bookmarks to fetch
    """)

if __name__ == "__main__":
    # Parse command line arguments
    args = sys.argv[1:]
    
    # Default values
    output_json = False
    max_results = 25
    show_rate_info = True
    
    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            output_json = True
        elif arg == "--max-results":
            if i + 1 < len(args):
                try:
                    max_results = int(args[i + 1])
                    i += 1  # Skip the next argument
                except ValueError:
                    print("Error: --max-results requires a number")
                    sys.exit(1)
            else:
                print("Error: --max-results requires a number")
                sys.exit(1)
        elif arg == "--quiet":
            show_rate_info = False
        elif arg == "--help":
            show_usage()
            sys.exit(0)
        else:
            print(f"Unknown argument: {arg}")
            show_usage()
            sys.exit(1)
        i += 1
    
    # Validate max_results
    if max_results < 1 or max_results > 100:
        print("Error: max-results must be between 1 and 100")
        sys.exit(1)
    
    if output_json:
        # Return raw JSON
        data = get_bookmarks_json(max_results)
        if data:
            print(json.dumps(data, indent=2))
    else:
        # Pretty print bookmarks
        get_bookmarks(max_results, show_rate_info)

