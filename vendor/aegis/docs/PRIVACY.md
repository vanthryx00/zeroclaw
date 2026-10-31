# Privacy, Anonymity, and Amnesia

This document is deliberately blunt about what AegisOS does and does **not**
give you. Read it before relying on any of it.

## What AegisOS actually provides

| Mechanism | What it does | Limit |
|-----------|--------------|-------|
| Amnesic root (`toram`) | Loads the OS into RAM; the USB is not written to | RAM is not wiped until shutdown; a crash leaves data in RAM |
| No swap | Prevents memory pages leaking to disk | — |
| Memory wipe on shutdown | Overwrites free RAM (`sdmem`) to defeat cold-boot attacks | Best-effort; power loss skips it entirely |
| MAC randomization | Random MAC per interface per boot | Your AP still sees signal/timing; does not defeat a hostile network |
| IPv6 disabled | Removes a common Tor leak path | Some networks require IPv6 |
| Forced Tor (transparent proxy) | Redirects all TCP + DNS to Tor; drops the rest | Tor does not hide *what you type* or *who you are* to a site |
| DNS through Tor | No public resolver sees your queries | — |
| UTC clock, generic hostname | Removes two easy fingerprints | Many others remain (font, screen, timezone behavior, typing cadence) |
| Whonix Gateway + Workstation | Compartmentalizes Tor from your work VM | Requires KVM; the host itself is still trusted |
| Audit log | Every command Aegis runs is recorded | The log itself is a forensic artifact — see below |

## The honest threat model

### What this defends against

- **Casual forensic recovery** of files you worked on: nothing persists to the
  USB in amnesic mode.
- **Network observers** seeing which sites you visit: traffic goes through Tor.
- **Your ISP / local network** seeing your traffic contents and destinations.
- **MAC-based tracking** across sessions on the same network.
- **Cold-boot RAM attacks** after a clean shutdown.

### What this does NOT defend against

- **A determined global adversary** correlating Tor traffic (Tor is not a
  magic wand; traffic-correlation attacks are real).
- **You logging in to an account that identifies you.** Anonymity is lost the
  moment you authenticate to something tied to your identity.
- **Malicious code running in your session** — it can read what you can read.
- **Compromised firmware / a hardware implant** below the OS.
- **The audit log.** `~/.local/share/aegis/audit.jsonl` records every command
  Aegis ran. In amnesic mode it lives in RAM and dies with the session. On a
  persistent install, it is on disk. If that is a problem, mount the log
  directory as tmpfs or disable it.
- **Metadata you create** (file timestamps, sizes, content) if you persist it.

### Tails vs AegisOS — be clear

Tails is built from the ground up around a single threat model (amnesia +
forced Tor + uniform fingerprint) and is audited for it. AegisOS is a
*security workstation with privacy features*. If your life depends on
anonymity, use Tails or Whonix, not this. If you want an offline AI copilot
that can also repair machines and route through Tor, AegisOS is a good fit.

## Usage recipes

### Maximum-anonymity session

1. Boot the USB with `toram` and **without** `persistent`.
2. `aegis privacy status` — confirm score is high.
3. Start Tor: `sudo systemctl start tor aegis-tor-firewall`.
4. `aegis privacy status` again — Tor should now show `ok`, DNS `ok`.
5. Do your work. Do not log in to anything personal.
6. Shut down cleanly (triggers the memory wipe).

### Compartmentalized (Whonix)

1. `sudo bash build/privacy/40-whonix.sh`
2. `aegis-whonix up`
3. Work inside the **Workstation** VM only. The Gateway forces Tor.

### Persistent (non-amnesic) workstation

Boot with `persistent`. Your files, config, and audit log survive. Convenient,
but every trace stays on the stick — treat it as evidence.

## Verifying Tor is actually working

```bash
curl https://check.torproject.org/        # should say "Congratulations"
aegis privacy tor                          # shows which Tor ports are open
aegis privacy status                       # DNS + Tor + IPv6 + MAC checks
```

If `check.torproject.org` does **not** confirm Tor, assume you are leaking and
stop. The transparent-proxy firewall drops non-Tor traffic, but a misconfigured
boot can bypass it.

## Where the settings live

- Runtime config: `[privacy]` in `/etc/aegis/config.toml` or
  `~/.config/aegis/config.toml`.
- Environment: `AEGIS_AMNESIC`, `AEGIS_FORCE_TOR`, `AEGIS_PROXY`.
- Build-time scripts: `build/privacy/10-tor.sh` … `40-whonix.sh`.
