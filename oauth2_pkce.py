#!/usr/bin/env python3
"""
OAuth 2.0 Authorization Code Flow with PKCE for X API.

This script will help you get a user access token for bookmarks.
"""

import base64
import hashlib
import os
import secrets
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Your app credentials from X Developer Portal
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")  # Only for confidential clients
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8080/callback")


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return code_verifier, code_challenge


def create_authorization_url():
    """Create the authorization URL for OAuth 2.0 flow."""
    code_verifier, code_challenge = generate_pkce_pair()

    # Store code_verifier for later use
    with open(".code_verifier", "w") as f:
        f.write(code_verifier)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "bookmark.read tweet.read users.read",  # Add other scopes as needed
        "state": secrets.token_urlsafe(32),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"https://x.com/i/oauth2/authorize?{urlencode(params)}"
    return auth_url, code_verifier


def exchange_code_for_token(authorization_code, code_verifier):
    """Exchange authorization code for access token."""
    token_url = "https://api.x.com/2/oauth2/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": authorization_code,
        "code_verifier": code_verifier,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # For confidential clients (with client secret), use Basic Auth
    if CLIENT_SECRET:
        import base64

        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_credentials}"
    # For public clients (no client secret), client_id goes in the body (already there)

    response = requests.post(token_url, data=data, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error exchanging code for token: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def start_local_server():
    """Start a simple local server to capture the callback."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Parse the callback URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Check if this is the OAuth callback
            if "code" in query_params:
                authorization_code = query_params["code"][0]

                # Store the authorization code
                with open(".auth_code", "w") as f:
                    f.write(authorization_code)

                # Send success response
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                response = """
                <html>
                <body>
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to your terminal.</p>
                </body>
                </html>
                """
                self.wfile.write(response.encode())
            else:
                # Send error response
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                response = """
                <html>
                <body>
                    <h1>Authorization Failed</h1>
                    <p>No authorization code received.</p>
                </body>
                </html>
                """
                self.wfile.write(response.encode())

        def log_message(self, format, *args):
            # Suppress server logs
            pass

    # Start server
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    return server


def main():
    """Main OAuth 2.0 flow."""
    print("X API OAuth 2.0 Authorization Code Flow with PKCE")
    print("=" * 50)

    # Check credentials
    if not CLIENT_ID:
        print("Error: CLIENT_ID not found in environment variables")
        print("Please add CLIENT_ID to your .env file")
        return

    print(f"Client ID: {CLIENT_ID}")
    print(f"Redirect URI: {REDIRECT_URI}")
    print()

    # Create authorization URL
    auth_url, code_verifier = create_authorization_url()

    print("Step 1: Opening browser for authorization...")
    print(f"URL: {auth_url}")
    print()

    # Start local server to capture callback
    server = start_local_server()

    # Open browser
    webbrowser.open(auth_url)

    print("Step 2: Please authorize the application in your browser")
    print("Waiting for callback...")

    # Wait for authorization code
    auth_code_file = ".auth_code"
    while not os.path.exists(auth_code_file):
        import time

        time.sleep(1)

    # Read authorization code
    with open(auth_code_file) as f:
        authorization_code = f.read().strip()

    # Clean up
    os.remove(auth_code_file)
    server.shutdown()

    print("Step 3: Exchanging authorization code for access token...")

    # Exchange code for token
    token_data = exchange_code_for_token(authorization_code, code_verifier)

    if token_data:
        print("Success! Here are your tokens:")
        print()
        print(f"Access Token: {token_data.get('access_token')}")
        if "refresh_token" in token_data:
            print(f"Refresh Token: {token_data.get('refresh_token')}")
        print(f"Token Type: {token_data.get('token_type')}")
        print(f"Expires In: {token_data.get('expires_in')} seconds")
        print()

        # Save to .env file
        with open(".env", "a") as f:
            f.write("\n# OAuth 2.0 User Context Token\n")
            f.write(f"USER_ACCESS_TOKEN={token_data.get('access_token')}\n")
            if "refresh_token" in token_data:
                f.write(f"USER_REFRESH_TOKEN={token_data.get('refresh_token')}\n")

        print("Tokens have been saved to your .env file")
        print("You can now use USER_ACCESS_TOKEN as your Bearer token for bookmarks!")

    else:
        print("Failed to exchange authorization code for token")

    # Clean up code verifier
    if os.path.exists(".code_verifier"):
        os.remove(".code_verifier")


if __name__ == "__main__":
    main()
