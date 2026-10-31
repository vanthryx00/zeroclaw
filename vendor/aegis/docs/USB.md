# Building and Using the USB

## 1. Build the ISO

Follow `build/cubic/README.md` to produce `AegisOS-*.iso`. Then optionally run
the privacy scripts inside the chroot:

```bash
bash /build/privacy/10-tor.sh
bash /build/privacy/20-network-hardening.sh
bash /build/privacy/30-amnesia.sh
bash /build/privacy/40-whonix.sh      # optional, needs network + ~5 GB
```

## 2. Write it to a USB stick

```bash
sudo bash build/usb/make-usb.sh --list                 # find your device
sudo bash build/usb/make-usb.sh --iso AegisOS.iso --device /dev/sdb
```

The script refuses to touch your system disk and makes you type the device path
to confirm.

### With persistence (survives reboot)

```bash
sudo bash build/usb/make-usb.sh --iso AegisOS.iso --device /dev/sdb --persistence 8G
```

Then add `persistent` to the kernel command line at the boot menu. Files under
`/home` and the Aegis audit log will persist.

### Amnesic (recommended for privacy)

Do **not** add persistence. Add `toram` instead, which loads the whole system
into RAM:

```
linux /casper/vmlinuz ... toram ---
```

Nothing is written to the stick. Shutdown triggers the memory wipe.

## 3. Boot options cheat-sheet

| Option | Effect |
|--------|--------|
| (default) | Live session, USB untouched, changes lost on reboot |
| `toram` | Load entire OS into RAM — fastest, most amnesic |
| `persistent` | Save /home + config to the `casper-rw` partition |
| `toram persistent` | RAM session but persist /home (hybrid) |

## 4. First boot

The `aegis-firstboot` service runs once and:
- starts the Ollama model server,
- verifies or pulls the local model,
- creates `~/aegis-workspace/{scans,notes,reports,payloads}`,
- prints the safety defaults.

Check everything with:

```bash
aegis doctor
aegis privacy status
```

## 5. Two USB sticks?

For rescue work it helps to have:

1. **AegisOS stick** — the live environment with the AI and tools.
2. **A data stick** — for backups you make *before* repairing anything.

Never store the only copy of important data on the same stick you are repairing
a machine with.

## Troubleshooting

- **USB does not appear in the boot menu**: disable Secure Boot, or re-write
  with `--list` to confirm the device, and check the ISO's UEFI support.
- **Boots to a black screen**: try `nomodeset` on the kernel command line.
- **Model will not load**: the machine may lack RAM for a 7B model. Pull the
  1.5B variant: `ollama pull qwen2.5-coder:1.5b`.
- **No network after Tor starts**: that is expected — the firewall drops
  non-Tor traffic. Check `aegis privacy tor` and `systemctl status tor`.
