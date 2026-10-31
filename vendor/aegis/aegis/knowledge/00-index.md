# AegisOS Offline Knowledge Base

These notes are bundled into the image at `/usr/share/aegis/knowledge/`. Aegis
reads the index and can pull a topic into its context so it can teach even with
no network connection.

## Index

| File | Topic |
|------|-------|
| `01-linux-fundamentals.md` | Shell, permissions, processes, filesystem |
| `02-networking-basics.md` | TCP/IP, ports, DNS, packet flow |
| `03-recon-methodology.md` | Structured enumeration workflow |
| `04-web-app-testing.md` | OWASP-style web testing primer |
| `05-ethics-and-scope.md` | Authorization, rules of engagement, reporting |

## How Aegis uses this

* `/knowledge` in the CLI lists topics.
* Asking "teach me X" makes Aegis pull the matching file into context.
* You can add your own `.md` files to `~/.local/share/aegis/knowledge/` and they
  are indexed too.
