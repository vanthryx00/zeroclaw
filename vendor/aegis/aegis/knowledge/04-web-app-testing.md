# Web Application Testing Primer

> Authorized targets only. For practice, use deliberately vulnerable apps:
> OWASP Juice Shop, DVWA, bWAPP, or a PortSwigger Web Security Academy lab.

## The OWASP Top 10 (2021) in plain language

1. **Broken Access Control** — can I reach another user's data or an admin page
   by changing a URL/ID? (`/user/1` → `/user/2`)
2. **Cryptographic Failures** — plaintext transport, weak hashing, exposed keys.
3. **Injection** — SQL, command, LDAP: untrusted input interpreted as code.
4. **Insecure Design** — flaws in the concept, not the code (no rate limits,
   no workflow checks).
5. **Security Misconfiguration** — default creds, directory listing, verbose errors.
6. **Vulnerable Components** — outdated libraries with known CVEs.
7. **Auth Failures** — weak sessions, credential stuffing, no lockout.
8. **Integrity Failures** — unsigned updates, insecure deserialization.
9. **Logging Failures** — attacks go unnoticed; no alerting.
10. **SSRF** — server fetches a URL you control, reaching internal services.

## A methodical pass

```bash
# 1. Fingerprint
whatweb http://target
curl -sI http://target

# 2. Crawl / discover
gobuster dir -u http://target -w /usr/share/wordlists/SecLists/Discovery/Web-Content/common.txt
ffuf -u http://target/FUZZ -w /usr/share/wordlists/SecLists/Discovery/Web-Content/common.txt

# 3. Check common files
for f in robots.txt sitemap.xml .git/HEAD .env backup.zip; do
    curl -s -o /dev/null -w "%{http_code} $f\n" http://target/$f
done
```

## Manual checks that find real bugs

- **Auth**: register two accounts, swap session cookies/IDs between them.
- **Access control**: change IDs, force-browse to `/admin`, remove parameters.
- **Input handling**: `'`, `"`, `;`, `$()`, `../../` in every field.
- **Business logic**: negative quantities, replay a payment step, skip a step.
- **Error messages**: verbose stack traces often leak paths and versions.

## Tools

| Task | Tool |
|------|------|
| Intercept / replay | Burp Suite Community, OWASP ZAP, mitmproxy |
| Fuzzing | ffuf, wfuzz, gobuster |
| SQL injection | sqlmap (only after manual confirmation) |
| CMS scanning | wpscan, joomscan |

## Reporting a finding

Every finding should state: **what**, **where** (exact request), **impact**,
**reproduction steps**, **evidence** (screenshot / response), and **fix**.
