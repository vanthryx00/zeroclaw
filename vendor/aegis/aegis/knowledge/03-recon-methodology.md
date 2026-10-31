# Recon Methodology

> Only run this against systems you own or have **written authorization** to test.
> Aegis refuses offensive tools whose target is not in your declared scope
> (`aegis scope add <target>`).

## 1. Scope and rules of engagement

Before touching anything:

- [ ] Written authorization on file, with the exact IP ranges / domains.
- [ ] Time window agreed (some orgs forbid scans during business hours).
- [ ] Emergency contact if something breaks.
- [ ] Explicit exclusions (e.g. don't touch the production DB host).

## 2. Passive recon (no packets to the target)

- Public DNS records, certificate transparency (`crt.sh`), WHOIS.
- Search engines, job postings, GitHub for leaked credentials.
- Wayback Machine for old endpoints.

## 3. Active recon (packets to the target)

```bash
# Host discovery on a subnet
nmap -sn 10.0.0.0/24

# Port + service + version
nmap -sV -sC -p- 10.0.0.5 -oA scans/host-10.0.0.5

# Fast top-1000 first
nmap -sV --top-ports 1000 10.0.0.5
```

Key `nmap` flags: `-sV` versions, `-sC` default scripts, `-O` OS guess,
`-p-` all 65535 ports, `-oA` write all formats, `-T4` faster timing.

## 4. Service enumeration

For every open port, ask "what is it, what version, what can it tell me?"

```bash
# SMB
smbclient -L //10.0.0.5 -N
enum4linux -a 10.0.0.5

# HTTP
whatweb http://10.0.0.5
nikto -h http://10.0.0.5
gobuster dir -u http://10.0.0.5 -w /usr/share/wordlists/SecLists/Discovery/Web-Content/common.txt

# DNS zone transfer
dig axfr @10.0.0.5 example.com
```

## 5. Organize findings

Keep a running note per host: IP, hostname, OS, open ports, service versions,
credentials found, screenshots. Store under `~/aegis-workspace/scans/`.

## 6. Then and only then: exploitation

Match a finding to a known vulnerability, verify it safely, document the exact
steps to reproduce. Prefer the least-invasive proof that the issue is real.

## Common beginner mistakes

- Scanning the whole internet by accident — always double-check the target range.
- Chasing every open port instead of the interesting services.
- Forgetting to save output — always use `-oA` / redirect to a file.
- No notes — you will not remember which host had the vulnerable version.
