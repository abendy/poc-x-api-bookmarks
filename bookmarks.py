import requests
from requests_oauthlib import OAuth1
import json
import sys

# Your X API credentials
API_KEY = "your_api_key_here"
API_SECRET = "your_api_secret_here"
ACCESS_TOKEN = "your_access_token_here"
ACCESS_TOKEN_SECRET = "your_access_token_secret_here"

def get_bookmarks():
    """Fetch user bookmarks from X API"""
    
    # Set up OAuth 1.0a authentication
    auth = OAuth1(
        API_KEY,
        client_secret=API_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET
    )
    
    # API endpoint
    url = "https://api.twitter.com/2/users/me/bookmarks"
    
    # Parameters for the request
    params = {
        "tweet.fields": "created_at,author_id,text,public_metrics,context_annotations",
        "expansions": "author_id",
        "user.fields": "name,username,verified",
        "max_results": 100  # Max is 100 per request
    }
    
    try:
        print("Fetching your X bookmarks...")
        response = requests.get(url, auth=auth, params=params)
        
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
                    print(f"   Text: {bookmark.get('text', 'No text')[:100]}...")
                    print(f"   Metrics: {bookmark.get('public_metrics', {})}")
                    print(f"   Tweet ID: {bookmark.get('id')}")
                
                # Check if there are more pages
                if 'meta' in data and 'next_token' in data['meta']:
                    print(f"\nNote: There are more bookmarks available (next_token: {data['meta']['next_token']})")
                    print("You can fetch more by using the pagination token.")
                
            else:
                print("No bookmarks found or no data returned.")
                
        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Error fetching bookmarks: {e}")

def get_bookmarks_json():
    """Fetch bookmarks and return raw JSON"""
    auth = OAuth1(
        API_KEY,
        client_secret=API_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_TOKEN_SECRET
    )
    
    url = "https://api.twitter.com/2/users/me/bookmarks"
    params = {
        "tweet.fields": "created_at,author_id,text,public_metrics,context_annotations",
        "expansions": "author_id",
        "user.fields": "name,username,verified",
        "max_results": 100
    }
    
    try:
        response = requests.get(url, auth=auth, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        # Return raw JSON
        data = get_bookmarks_json()
        if data:
            print(json.dumps(data, indent=2))
    else:
        # Pretty print bookmarks
        get_bookmarks()

