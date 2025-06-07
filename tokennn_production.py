import os
from flask import Flask, request, redirect
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)

# SET THESE with your actual credentials
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "your-client-id")
SPOTIFY_SECRET = os.environ.get("SPOTIFY_SECRET", "your-client-secret")
# Use your ACTUAL production redirect URI
SPOTIFY_REDIRECT_URI = "https://waha-gemini-assistant.onrender.com/callback"

SCOPE = "user-read-playback-state user-modify-playback-state"

auth_manager = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE
)

@app.route('/')
def login():
    auth_url = auth_manager.get_authorize_url()
    return f'''
    <h2>Spotify Authorization for Production</h2>
    <p>Redirect URI: {SPOTIFY_REDIRECT_URI}</p>
    <a href="{auth_url}" style="padding: 10px; background: #1db954; color: white; text-decoration: none; border-radius: 5px;">Click here to authorize</a>
    <br><br>
    <p><strong>After authorization:</strong></p>
    <ol>
        <li>You'll be redirected to: <code>{SPOTIFY_REDIRECT_URI}?code=...</code></li>
        <li>Copy the authorization code from the URL</li>
        <li>Visit: <code>http://localhost:8888/callback?code=PASTE_CODE_HERE</code></li>
        <li>Get your refresh token</li>
    </ol>
    '''

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        try:
            token_info = auth_manager.get_access_token(code)
            return f"""
            <h2>✅ Success! Token Generated</h2>
            <div style="background: #f0f0f0; padding: 10px; margin: 10px 0; border-radius: 5px;">
                <p><strong>Refresh Token:</strong></p>
                <textarea style="width: 100%; height: 100px; font-family: monospace;">{token_info['refresh_token']}</textarea>
            </div>
            <p><strong>Access Token:</strong> {token_info['access_token'][:50]}...</p>
            <p><strong>Expires In:</strong> {token_info['expires_in']} seconds</p>
            <br>
            <p style="background: #e7f3ff; padding: 10px; border-radius: 5px;">
                <strong>Next Step:</strong> Copy the refresh token above and set it as 
                <code>SPOTIFY_REFRESH_TOKEN</code> in your Render environment variables.
            </p>
            """
        except Exception as e:
            return f"<h2>❌ Error getting token:</h2><p>{str(e)}</p>"
    else:
        return "<h2>❌ Authorization failed</h2><p>No authorization code received.</p>"

if __name__ == '__main__':
    print(f"Starting server for production token generation...")
    print(f"Production redirect URI: {SPOTIFY_REDIRECT_URI}")
    print(f"Visit: http://localhost:8888/")
    app.run(host='0.0.0.0', port=8888, debug=True)