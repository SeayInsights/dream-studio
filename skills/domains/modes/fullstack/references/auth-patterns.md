# Auth Patterns Reference

## Auth Method Selection

| Method | Best For | Token Location | Expiry | Refresh |
|--------|----------|----------------|--------|---------|
| JWT (stateless) | SPAs, mobile, microservices | httpOnly cookie or Auth header | 15min-1hr | Refresh token (long-lived) |
| Session (stateful) | Traditional web apps, SSR | httpOnly cookie (session ID) | 24hr-7d | Sliding window |
| API Key | Service-to-service, public APIs | Header (X-API-Key) | None (revocable) | Re-issue |
| OAuth 2.0 | Social login, third-party access | Provider tokens → local JWT/session | Varies | Provider refresh token |

---

## JWT Implementation Pattern

- **Access token:** short-lived (15min), httpOnly cookie (preferred) or Authorization header
- **Refresh token:** long-lived (7d), httpOnly cookie, stored server-side for revocation
- **Flow:** login → issue access+refresh → access expires → use refresh to get new access → refresh expires → re-login
- **DO** store in httpOnly Secure cookies
- **DON'T** store in localStorage (XSS vulnerable)

```ts
// Issue tokens on login
const accessToken = jwt.sign({ userId, role }, SECRET, { expiresIn: '15m' });
const refreshToken = jwt.sign({ userId }, REFRESH_SECRET, { expiresIn: '7d' });

res.cookie('access_token', accessToken, { httpOnly: true, secure: true, sameSite: 'lax' });
res.cookie('refresh_token', refreshToken, { httpOnly: true, secure: true, sameSite: 'lax' });

// Refresh endpoint
const payload = jwt.verify(req.cookies.refresh_token, REFRESH_SECRET);
const newAccess = jwt.sign({ userId: payload.userId, role: payload.role }, SECRET, { expiresIn: '15m' });
```

---

## Password Handling

| Action | Use | Never Use |
|--------|-----|-----------|
| Hashing | bcrypt (cost 12) or argon2id | MD5, SHA-256 without salt, plaintext |
| Reset | Time-limited token (1hr) via email | Security questions, predictable tokens |

**Reset flow:** email → generate signed time-limited token → store hash server-side → user submits new password → verify token → hash new password → invalidate token

```ts
// bcrypt example
const hash = await bcrypt.hash(password, 12);
const valid = await bcrypt.compare(input, hash);

// argon2id example
const hash = await argon2.hash(password, { type: argon2.argon2id });
```

---

## RBAC Pattern

| Role | Permissions |
|------|-------------|
| admin | read, write, delete, manage_users |
| editor | read, write |
| viewer | read |

**Middleware pattern:** extract role from verified JWT → compare against route's required permissions

```ts
const requireRole = (...roles: string[]) => (req, res, next) => {
  const payload = jwt.verify(req.cookies.access_token, SECRET);
  if (!roles.includes(payload.role)) return res.status(403).json({ error: 'Forbidden' });
  req.user = payload;
  next();
};

// Usage
router.delete('/post/:id', requireRole('admin', 'editor'), deletePost);
router.get('/admin/users', requireRole('admin'), listUsers);
```

---

## OAuth 2.0 — Authorization Code + PKCE

1. Generate `code_verifier` (random 43-128 char string) + `code_challenge` (SHA-256 of verifier, base64url)
2. Redirect user to provider `/authorize` with `code_challenge`, `client_id`, `redirect_uri`, `scope`
3. User authenticates at provider; provider redirects back with `code`
4. Exchange `code` + `code_verifier` for provider access/refresh tokens (server-side POST)
5. Fetch user profile from provider using access token; create or update local user record
6. Issue local session/JWT; store provider refresh token encrypted for ongoing API access

```ts
// Step 1 — PKCE challenge
const verifier = crypto.randomBytes(64).toString('base64url');
const challenge = crypto.createHash('sha256').update(verifier).digest('base64url');

// Step 4 — Token exchange
const { data } = await axios.post(provider.tokenUrl, {
  grant_type: 'authorization_code', code, code_verifier: verifier,
  client_id, redirect_uri
});
```

---

## Security DO / DON'T

| DO | DON'T |
|----|-------|
| Use `httpOnly + Secure + SameSite=Lax` cookies for tokens | Store JWTs in `localStorage` or `sessionStorage` |
| Validate JWT signature AND expiry on every request | Trust client-side role claims without server verification |
| Rate-limit login endpoints (5 attempts/min per IP) | Return different errors for "user not found" vs "wrong password" (enumeration) |
| Rotate refresh tokens on each use (one-time use) | Log or expose tokens in error messages or URLs |
| Use constant-time comparison for token validation | Roll your own crypto — use vetted libraries |
| Invalidate all sessions on password change | Leave refresh tokens valid after logout |
