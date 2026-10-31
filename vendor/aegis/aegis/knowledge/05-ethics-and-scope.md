# Ethics, Authorization, and Scope

Security skills are dual-use. The line between a professional and a criminal is
**authorization**, not intent or tooling.

## The rule

> Do not test any system you do not own or lack **explicit written permission**
> to test. "It was on the internet" is not permission.

## What counts as authorization

- A signed contract / statement of work, or a bug-bounty program's published
  scope (respect its exclusions and rate limits).
- Your own lab: VMs, containers, hardware you own.
- Purpose-built practice targets: TryHackMe, Hack The Box, PortSwigger Academy,
  OWASP Juice Shop, DVWA.

## What does NOT count

- A friend saying "sure, poke at my site" with no written scope.
- A company's public website being reachable.
- "I was just curious / testing my skills."

## Rules of engagement (get these in writing)

1. **Scope** — exact IPs, domains, and out-of-scope systems.
2. **Window** — dates and times testing is allowed.
3. **Techniques** — is DoS testing allowed? Social engineering? Physical?
4. **Contacts** — who to call if you take something down.
5. **Data handling** — how to store, encrypt, and delete any data you touch.
6. **Reporting** — format, deadline, severity scale.

## Legal backdrop (informal, not legal advice)

- **US**: Computer Fraud and Abuse Act (CFAA), 18 U.S.C. § 1030.
- **UK**: Computer Misuse Act 1990.
- **EU**: national implementations of the Budapest Convention.

Penalties can be severe even for "harmless" access. When in doubt, stop and ask.

## Aegis's guardrails

- Offensive tools are refused unless the target is in your declared scope
  (`aegis scope add 10.0.0.0/24`).
- Genuinely catastrophic commands are hard-blocked in every mode.
- Every command is written to an append-only audit log you can review.

These are guardrails, not a license. You are responsible for staying legal.
