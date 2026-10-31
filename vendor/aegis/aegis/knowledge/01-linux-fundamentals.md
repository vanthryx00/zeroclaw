# Linux Fundamentals for Security Work

## The filesystem

| Path | Purpose |
|------|---------|
| `/` | root of everything |
| `/etc` | system config (passwd, shadow, sudoers, ssh) |
| `/var/log` | logs — first place to look after "something happened" |
| `/proc` | kernel + process state as files (`/proc/<pid>/`) |
| `/sys` | device and driver state |
| `/dev` | device nodes (`/dev/sda`, `/dev/null`) |
| `/tmp` | world-writable scratch — common staging ground |

## Permissions

`rwx` for user / group / other. The important special bits:

* **setuid** (`chmod u+s`): program runs as the file's owner. A setuid-root
  binary is a privilege-escalation target — list them with:
  `find / -perm -4000 -type f 2>/dev/null`
* **setgid**: runs with the file's group.
* **sticky bit** on a directory: only owners can delete their files (`/tmp`).

Numeric: `r=4 w=2 x=1`, so `755` = `rwxr-xr-x`.

## Processes

* `ps aux` / `ps -ef` — snapshot.
* `top` / `htop` — live.
* `/proc/<pid>/cmdline` — exact command line.
* `lsof -p <pid>` — files and sockets a process holds.
* Signals: `TERM` (15, ask to stop), `KILL` (9, cannot be caught), `HUP` (1).

## Users and privilege

* `/etc/passwd` — accounts (world-readable). `/etc/shadow` — hashes (root only).
* `sudo -l` — what the current user may run as root. A classic privesc check.
* `id`, `groups`, `whoami` — who am I really.

## Useful inspection one-liners

```bash
ss -tulpn                       # listening sockets + owning process
find / -perm -4000 -type f 2>/dev/null   # setuid binaries
getcap -r / 2>/dev/null         # files with Linux capabilities
ls -la /etc/cron*               # scheduled tasks
cat /etc/crontab; crontab -l    # cron entries
```

## Package + service management (Debian/Ubuntu family)

```bash
apt list --installed
systemctl status <svc>          # inspect a service
systemctl list-units --type=service
journalctl -u <svc> -n 50       # service logs
```
