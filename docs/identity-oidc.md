# Identity: OpenID Connect login (UAE PASS and Microsoft Entra ID)

Silsila can sign people in through any standards-compliant OpenID Connect (OIDC) provider, using the authorization code flow with PKCE. Families use UAE PASS; counsellors use the provider's identity system (for example Microsoft Entra ID with MFA). Which provider is used is set by environment variables only. When no provider is configured the feature is off: `GET /api/auth/oidc/providers` returns an empty list and the other endpoints return 404. The demo password login is unchanged.

Code: `backend/src/silsila/api/oidc.py`. Tests: `backend/tests/test_oidc.py`.

## What is tested and what is not

Tested (automated, against a local mock identity provider that follows the OIDC standard): the redirect carries `state`, `nonce` and an S256 PKCE challenge; the happy path ends with a Silsila token that the API accepts; ID tokens with a wrong nonce, audience, issuer, an expired token, a bad signature or an HS256 token are rejected; a tampered, missing or wrong-provider state cookie is rejected; an unknown signing key id triggers one key refresh (and no more than one per 10 seconds); a counsellor not on the allowlist gets 403; the provider list contains no secrets; nothing is active when unconfigured.

Not tested: **we have not tested against UAE PASS itself, nor against a real Entra ID tenant.** Behaviour against the real services (their exact scope names, claim names, token endpoint authentication method, logout, error pages) is unverified. Do not describe this as "UAE PASS integrated" until a staging login has worked end to end.

## How a login works

1. The web app sends the browser to `/api/auth/oidc/<provider>/start`.
2. The API redirects to the provider's authorization endpoint (found through `<issuer>/.well-known/openid-configuration`) with `state`, `nonce` and a PKCE challenge. The login state goes into a signed, HttpOnly, SameSite=Lax cookie (Secure unless the redirect URI is localhost), valid 10 minutes. Nothing is kept in server memory, so any replica can finish the login.
3. The provider redirects back to `/api/auth/oidc/<provider>/callback`. The API checks the state cookie, exchanges the code for tokens, and fully validates the ID token (signature RS256 or ES256 from the provider's published keys, `iss`, `aud`, `exp`, `iat`, `nonce`).
4. The API maps the person to a Silsila user (below), issues the normal Silsila token, and redirects to `SILSILA_OIDC_POST_LOGIN_URL#token=<jwt>`. The token is in the URL fragment so it is not sent to any server and does not appear in server logs. The web app's `/signed-in` page (`web/src/app/signed-in/page.tsx`) reads it from `location.hash`, clears the hash, checks it with `/api/me` and stores the session as a password sign-in does.

User mapping:
- A user is looked up by `oidc_sub` = `<issuer>|<sub>`.
- Role `family`: if no user exists, a minimal one is created (`role`, `oidc_sub`, `lang` = `en`, a generic display name). No name, email or Emirates ID is stored.
- Role `counsellor`: the email in the token must be in `SILSILA_OIDC_STAFF_ALLOWLIST` on every login (removing an address revokes access at the next login; existing tokens last up to 8 hours). Otherwise 403. A user created as one role cannot sign in through a provider of the other role.

## Configuration

Provider ids are the middle part of the variable name (`FAMILY`, `STAFF` below). Any id works; a provider is active only when issuer, client id, role and redirect URI are all set and the issuer is https.

| Variable | Meaning |
|---|---|
| `SILSILA_OIDC_<ID>_ISSUER` | Issuer URL. Discovery is read from `<issuer>/.well-known/openid-configuration`; the `issuer` it returns must match exactly. |
| `SILSILA_OIDC_<ID>_CLIENT_ID` | Client id registered with the provider. |
| `SILSILA_OIDC_<ID>_CLIENT_SECRET` | Optional. If set, the client is confidential. Keep it in the secret store, not in git. |
| `SILSILA_OIDC_<ID>_SCOPES` | Default `openid profile email`. Set what the provider requires. |
| `SILSILA_OIDC_<ID>_ROLE` | `family` or `counsellor`. |
| `SILSILA_OIDC_<ID>_REDIRECT_URI` | Public URL of `/api/auth/oidc/<id>/callback`, registered with the provider exactly. |
| `SILSILA_OIDC_<ID>_TOKEN_AUTH` | `basic` (default, client_secret_basic) or `post` (client_secret_post). |
| `SILSILA_OIDC_POST_LOGIN_URL` | Web URL to return to after login: the web app's `/signed-in` page, e.g. `https://silsila.example.ae/signed-in`. |
| `SILSILA_OIDC_STAFF_ALLOWLIST` | Comma-separated emails allowed to sign in as counsellors. |
| `SILSILA_SECRET` | Required in production already; also signs the state cookie. |

## UAE PASS (families)

1. UAE PASS onboarding through TDRA is required before any of this works. They issue staging client credentials first, then production after review. Start with staging.
2. Set `SILSILA_OIDC_FAMILY_ISSUER` to the issuer UAE PASS gives you for staging, and register the redirect URI.
3. UAE PASS uses its own scope names, not only `openid profile email`. Set `SILSILA_OIDC_FAMILY_SCOPES` to what your onboarding approves. We deliberately do not hardcode them.
4. UAE PASS may require a particular token endpoint authentication method and may return identity data (including an Emirates ID number) in the ID token or at a userinfo endpoint. Silsila uses only `sub` and does not store or log any other claim. If your approved scopes return the Emirates ID, that is personal data in transit; ask for the minimum scopes that still return a stable `sub`. Check with the UAE PASS integration guide whether `sub` is stable per relying party; the mapping depends on it.
5. Verify with a staging account before anything else; record the results here.

## Microsoft Entra ID with MFA (counsellors)

1. Register an application in the tenant (web platform), add the redirect URI, create a client secret, and note the tenant id.
2. `SILSILA_OIDC_STAFF_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0`, role `counsellor`, scopes `openid profile email`.
3. Enforce MFA with a Conditional Access policy on this application (require multifactor authentication for the assigned users). Silsila relies on Entra to do this; it does not check authentication strength itself. Assign only the counsellor group to the app.
4. Entra often omits `email` and gives `preferred_username` or `upn`; Silsila falls back to those if they contain an `@`. Put the same address in `SILSILA_OIDC_STAFF_ALLOWLIST`.

## Security notes

- Allowed signing algorithms are RS256 and ES256 only. Tokens signed with HS256 or `none` are rejected.
- PKCE is always used. The PKCE verifier is derived from `SILSILA_SECRET` and is not placed in the cookie.
- The state cookie is signed, not encrypted, and is not single-use on the server (no server state). Replay is limited by the one-time authorization code, the nonce check and the 10-minute lifetime.
- Failures return a generic message to the user. The audit trail records the provider and an error code (for example `id_token_nonce`, `not_allowlisted`) and never tokens, emails, subject ids or codes. Neither the code nor the tokens are logged.
- Key refresh: an unknown `kid` causes one refresh of the provider's key set, at most once per 10 seconds, so bad tokens cannot make us hammer the provider. Discovery and keys are cached in memory per process.
- Not implemented: logout at the provider (single logout), refresh tokens, userinfo calls, back-channel logout, and server-side session revocation beyond the 8-hour token life.
- Outbound calls use the Python standard library and a 10-second timeout; the provider must be reachable from the API host.
- PyJWT needs the `cryptography` package for RS256/ES256; it must be a main dependency in production.
