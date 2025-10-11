# X API Bookmarks Fetcher

A Python script to fetch your X (Twitter) bookmarks using the X API v2 with proper rate limiting and OAuth 2.0 User Context authentication.

## Features

- ✅ OAuth 2.0 User Context authentication
- ✅ Rate limit monitoring and handling
- ✅ Environment variable configuration
- ✅ Conservative defaults to avoid hitting API limits
- ✅ JSON and pretty-print output options
- ✅ Flexible batch size control
- ✅ Comprehensive error handling

## Prerequisites

### X Developer Account Setup

1. **Create a X Developer Account** at [developer.x.com](https://developer.x.com)
2. **Create a new App** in your developer dashboard
3. **Configure OAuth 2.0 settings:**
   - Type: Web App, Automated App or Bot
   - Callback URI: `http://localhost:8080/callback`
   - Scopes: Read permissions (bookmark.read, tweet.read, users.read)
4. **Get your Client ID** from the app settings

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd x-api
```

### 2. Set Up Python Environment

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows

# Install runtime dependencies
uv pip install python-dotenv requests

# For development (includes linting, testing, type checking)
uv pip install mypy pre-commit pytest pytest-asyncio pytest-cov \
    pytest-mock pytest-xdist pyright ruff factory-boy ipdb
```

### 3. Configure Environment Variables

```bash
# Copy the template
cp .env.template .env

# Edit .env and add your CLIENT_ID
# CLIENT_ID=your_client_id_here
```

### 4. Authenticate with X API

Run the OAuth 2.0 flow to get your user access token:

```bash
python3 oauth2_pkce.py
```

This will:
- Open your browser for authorization
- Start a local server to capture the callback
- Save your `USER_ACCESS_TOKEN` to `.env` automatically

### 5. (Optional) Set Up Pre-Commit Hooks

```bash
pre-commit install
```

This enables automatic code formatting and linting before each commit.

## Usage

### Basic Usage

```bash
# Fetch 25 bookmarks with pretty output (default)
python3 bookmarks.py

# Fetch specific number of bookmarks
python3 bookmarks.py --max-results 10

# Get raw JSON output
python3 bookmarks.py --json

# Quiet mode (no rate limit info)
python3 bookmarks.py --quiet

# Show help
python3 bookmarks.py --help
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--json` | Output raw JSON instead of pretty print | Pretty print |
| `--max-results N` | Fetch N bookmarks (1-100) | 25 |
| `--quiet` | Don't show rate limit information | Show rate info |
| `--help` | Show usage instructions | - |

### Example Output

```text
Fetching your X bookmarks (max 25)...
Rate limit: 75 requests per 15 minutes for bookmarks endpoint
Rate limit remaining: 74/75 (resets at Mon Jan 29 14:30:00 2024)

Found 25 bookmarks:
============================================================

1. Tweet by @username (Display Name)
   Created: 2024-01-29T13:45:00.000Z
   Text: This is an example tweet that was bookmarked...
   Likes: 42, Retweets: 7
   Tweet ID: 1234567890123456789

2. Tweet by @another_user (Another User)
   Created: 2024-01-29T12:30:00.000Z
   Text: Another bookmarked tweet with interesting content...
   Likes: 156, Retweets: 23
   Tweet ID: 9876543210987654321

Note: There are more bookmarks available.
Next token: abc123xyz789
Run again with --paginate to fetch more (uses additional API calls)
```

## Rate Limiting

### Important Rate Limit Information

- **Bookmarks endpoint**: 75 requests per 15 minutes
- **Conservative approach**: Script defaults to 25 bookmarks per request
- **Maximum per request**: 100 bookmarks
- **Rate limit monitoring**: Shows remaining requests and reset time

### Rate Limiting Strategy

1. **Start small**: Begin with 10-25 bookmarks to test
2. **Monitor usage**: Check rate limit info in output
3. **Plan requests**: You can fetch ~7,500 bookmarks per 15 minutes (75 requests × 100 bookmarks)
4. **Handle limits**: Script automatically detects and reports rate limit hits

### Rate Limit Best Practices

```bash
# Conservative testing
python3 bookmarks.py --max-results 10

# Monitor your usage
python3 bookmarks.py --max-results 25  # Uses 1 request

# If you hit the limit, wait 15 minutes
# The script will tell you exactly when the limit resets
```

## Error Handling

The script handles common errors gracefully:

- **Missing credentials**: Validates environment variables
- **Rate limiting**: Detects 429 responses and shows reset time
- **API errors**: Displays error codes and messages
- **Network issues**: Catches and reports connection errors

## Troubleshooting

### Common Issues

1. **"Missing required environment variables"**
   - Check that your `.env` file exists and has the BEARER_TOKEN
   - Verify there are no extra spaces or quotes around values
   - Ensure you're using OAuth 2.0 User Context Bearer Token, not OAuth 2.0 Application-Only

2. **"Rate limit exceeded"**
   - Wait for the reset time shown in the error message
   - Use smaller `--max-results` values to conserve requests

3. **"Error: 401 Unauthorized"**
   - Verify your OAuth 2.0 User Context Bearer Token is correct
   - Check that your X app has read permissions
   - Ensure OAuth 2.0 User Context is enabled for your app
   - Your access token may have expired - get a new one

4. **"Error: 403 Forbidden"**
   - Your app may not have the required permissions
   - Check your X Developer Portal app settings
   - Ensure you're using OAuth 2.0 User Context authentication, not Application-Only

### Debug Steps

1. **Verify credentials:**

   ```bash
   # Check environment variables are loaded
   python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Bearer Token:', os.environ.get('BEARER_TOKEN', 'NOT FOUND')[:10] + '...')"
   ```

2. **Test with minimal request:**

   ```bash
   python3 bookmarks.py --max-results 5
   ```

3. **Check JSON output:**

   ```bash
   python3 bookmarks.py --json --max-results 5
   ```

## About Non-Folder Bookmarks

**Important Note**: The X API v2 does not currently provide a way to distinguish between bookmarks that are in folders versus those that are not. This script will return ALL your bookmarks.

To filter non-folder bookmarks, you would need to:

1. Get all bookmarks using this script
2. Use the X web interface to identify which bookmarks are in folders
3. Filter the results manually or programmatically

## Security Notes

- **Never commit your `.env` file** to version control
- **Keep your API credentials secure** and don't share them
- **Regenerate credentials** if you suspect they've been compromised
- **Use environment variables** in production environments

## API Reference

This script uses the following X API v2 endpoint:

- **Endpoint**: `GET /2/users/me/bookmarks`
- **Authentication**: OAuth 2.0 User Context (Bearer Token)
- **Rate Limit**: 75 requests per 15 minutes
- **Documentation**: [X API v2 Bookmarks](https://developer.x.com/en/docs/twitter-api/tweets/bookmarks/api-reference/get-users-id-bookmarks)

## License

This script is provided as-is for educational and personal use. Please comply with X's API Terms of Service and rate limiting guidelines.
