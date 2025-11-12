import os
from urllib.parse import urlparse, parse_qs
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes


CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/callback")
ENVIRONMENT = os.getenv("INTUIT_ENVIRONMENT", "sandbox")



auth_client = AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    environment=ENVIRONMENT,
)

scopes = [Scopes.ACCOUNTING, Scopes.OPENID, Scopes.EMAIL, Scopes.PROFILE]
url = auth_client.get_authorization_url(scopes)
print(url)




from urllib.parse import urlencode, urlparse, parse_qs
redirected = input("Paste the full redirect URL here: ").strip()
parsed = urlparse(redirected)
query = parse_qs(parsed.query)

auth_code = query["code"][0]           # only the code
realm_id = query["realmId"][0]
auth_client.get_bearer_token(auth_code, realm_id=realm_id)

print("Access token:", auth_client.access_token)
print("Refresh token:", auth_client.refresh_token)






