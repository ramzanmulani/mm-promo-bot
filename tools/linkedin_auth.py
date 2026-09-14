"""One-command LinkedIn login. Run on your own PC:

    python tools/linkedin_auth.py --client-id XXX --client-secret YYY

It opens your browser, you press Allow, and it prints the three values you
paste into GitHub Secrets. Nothing is stored on disk.

In your LinkedIn app (Auth tab) add this redirect URL first:
    http://localhost:8731/callback
"""
import argparse, http.server, secrets, threading, urllib.parse, webbrowser, sys
import requests

REDIRECT = "http://localhost:8731/callback"
SCOPES = "openid profile w_member_social"
_result = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _result.update({k: v[0] for k, v in q.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "code" in _result
        self.wfile.write(
            (f"<body style='background:#0E0E11;color:#F4F1EA;font:18px system-ui;"
             f"padding:60px'><h2>{'Done - go back to your terminal.' if ok else 'Login failed.'}"
             f"</h2></body>").encode())

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--json", default="",
                    help="write the results to this file instead of only "
                         "printing them (used by deploy.ps1 so you never "
                         "have to copy-paste a token)")
    a = ap.parse_args()

    stateval = secrets.token_urlsafe(16)
    url = ("https://www.linkedin.com/oauth/v2/authorization?"
           + urllib.parse.urlencode({
               "response_type": "code", "client_id": a.client_id,
               "redirect_uri": REDIRECT, "state": stateval, "scope": SCOPES}))

    srv = http.server.HTTPServer(("localhost", 8731), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    print("Opening browser...\nIf it does not open, paste this:\n" + url + "\n")
    webbrowser.open(url)

    for _ in range(180):
        if _result:
            break
        threading.Event().wait(1)
    if _result.get("state") != stateval or "code" not in _result:
        err = (_result or {}).get("error_description") or str(_result or "timed out")
        if "scope" in err.lower() or "unauthorized_scope" in str(_result):
            sys.exit(
                "LinkedIn ne scopes reject kiye.\n"
                "App ke Products tab me ye DO add karo, phir dobara chalao:\n"
                "  1. Share on LinkedIn            (w_member_social - post karne ke liye)\n"
                "  2. Sign In with LinkedIn using OpenID Connect\n"
                "     (openid + profile - aapka person URN padhne ke liye)\n"
                f"\nLinkedIn ka message: {err}")
        sys.exit(f"Login failed: {err}")

    tok = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "authorization_code", "code": _result["code"],
        "redirect_uri": REDIRECT, "client_id": a.client_id,
        "client_secret": a.client_secret}, timeout=30)
    tok.raise_for_status()
    access = tok.json()["access_token"]

    me = requests.get("https://api.linkedin.com/v2/userinfo",
                      headers={"Authorization": f"Bearer {access}"}, timeout=30)
    if me.status_code == 403:
        sys.exit("Token mil gaya par profile padh nahi paye. App ke Products "
                 "tab me 'Sign In with LinkedIn using OpenID Connect' add "
                 "karke dobara chalao.")
    me.raise_for_status()
    sub = me.json()["sub"]

    import datetime, json
    issued = datetime.date.today().isoformat()
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"access_token": access,
                       "person_urn": f"urn:li:person:{sub}",
                       "issued": issued}, fh)
        print(f"\nLinkedIn connected as {me.json().get('name', '')}. "
              f"Token handed to the deploy script.")
        return

    print("\n" + "=" * 66)
    print("Paste these into GitHub > Settings > Secrets and variables > Actions")
    print("=" * 66)
    print(f"LINKEDIN_ACCESS_TOKEN = {access}")
    print(f"LINKEDIN_PERSON_URN   = urn:li:person:{sub}")
    print(f"LINKEDIN_TOKEN_ISSUED = {issued}")
    print("=" * 66)
    print("This token lasts ~60 days. The bot will warn you on Discord before it expires.")


if __name__ == "__main__":
    main()
