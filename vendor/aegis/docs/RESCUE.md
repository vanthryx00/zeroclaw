# Rescue Mode

When a machine will not boot, boot AegisOS from USB and let Aegis diagnose it.

## Workflow

```bash
# 1. Find the disks and the broken system
aegis rescue scan

# 2. Mount the target root (pick the probable-system partition)
aegis rescue mount /dev/sda2

# 3. Diagnose the mounted system
aegis rescue diagnose

# 4. See the suggested repairs
aegis rescue plan /dev/sda

# 5. Run a repair, or drop into a chroot
aegis rescue chroot systemctl --failed
aegis rescue chroot update-initramfs -u -k all
aegis rescue chroot grub-install /dev/sda

# 6. Clean up
aegis rescue unmount
```

## What `diagnose` checks

| Category | Detects | Severity |
|----------|---------|----------|
| disk | root filesystem > 85% / > 95% full | warn / critical |
| inodes | inode exhaustion (many small files) | warn |
| filesystem | root remounted read-only after I/O errors | critical |
| bootloader | no GRUB config and no EFI system partition | critical |
| initramfs | kernel present but no initrd | critical |
| fstab | entries pointing at missing devices | warn |
| package | stale apt/dpkg lock files | info |
| services | journal present; suggests `systemctl --failed` | info |

## Common real-world repairs

### Disk full
```
apt clean
journalctl --vacuum-size=100M
find /var/log -type f -name '*.gz' -delete
```

### Bootloader broken (any kind)

The bootloader repair path detects what is installed, builds a plan, and only
writes when you say so. It is a dry run by default:

```
aegis rescue mount /dev/sda2                       # mount the broken root
aegis rescue bootloader /dev/sda --esp /dev/sda1   # detect + plan, changes nothing
aegis rescue bootloader /dev/sda --esp /dev/sda1 --apply   # execute the plan
```

`detect` recognises **GRUB (UEFI)**, **GRUB (BIOS/MBR)**, **systemd-boot**,
**Windows Boot Manager**, and Apple's bootloader, and reports its confidence plus
anything wrong (missing `grub.cfg`, no kernel under `/boot`, no mounted ESP).

Each plan starts with read-only inspection (`lsblk -f`, `efibootmgr -v`) and ends
by verifying the result, so you can see the current state before it changes.
Destructive steps are marked `!`:

```
   7. ! grub-install --target=x86_64-efi --efi-directory=/boot/efi ...
        reinstall the GRUB UEFI bootloader and its modules
```

The per-bootloader commands are:

| Detected | Repair |
|----------|--------|
| GRUB (UEFI) | `grub-install --target=x86_64-efi` → `update-grub` → `update-initramfs -u -k all` → `efibootmgr -c` if the entry was lost |
| GRUB (BIOS) | `grub-install --target=i386-pc /dev/sdX` → `update-grub` → `update-initramfs` |
| systemd-boot | `bootctl install` → `bootctl update` → `update-initramfs` |
| Windows | `bcdboot <root>/Windows /s <ESP> /f UEFI` → `ntfsfix -d` |
| none detected | falls back to a UEFI GRUB install, and says so plainly |

Anything that must run inside the target is wrapped in `chroot` automatically,
after `dev`/`proc`/`sys`/`run` are bind-mounted.

### Bootloader safety gates

Three independent gates protect this path:

1. **Dry run by default.** Without `--apply`, the plan is printed and nothing
   runs.
2. **The live-disk veto.** Writing a bootloader to the disk that hosts the
   *running* system is refused outright — the kernel has the old block mapping
   cached, so the write can land in the wrong place. The veto covers every
   branch of the plan and cannot be overridden with `--apply`.
3. **Normal classification.** `--apply` does not bypass anything: each step is
   classified (all bootloader writes are `RISKY`), confirmed according to the
   safety mode, and audited. Execution **stops at the first denied step**, since
a half-applied bootloader repair is worse than none.

The genuinely catastrophic variants are hard-blocked and can never run:

```
rm -rf /boot/efi          → BLOCKED  delete the EFI system partition contents
dd ... of=/dev/sda count=1 → BLOCKED  zero the disk partition table
wipefs -a /dev/sda        → BLOCKED  wipe filesystem signatures
```

### Missing initramfs
```
aegis rescue chroot update-initramfs -u -k all
```

### Filesystem corruption
```
aegis rescue unmount
aegis rescue fsck /dev/sda2
```
`fsck` must run on an **unmounted** filesystem.

## Safety notes

- All mutating actions (`mount`, `chroot`, `fsck`, `grub-install`) go through
  Aegis's safety classifier and are **confirmed before running** and written to
  the audit log. `fsck -y` and `grub-install` are destructive; read the command
  before you approve it.
- `rescue` assumes you are running as root from the live USB. If you are not
  root, `mount` will fail.
- Always `aegis rescue unmount` (or `umount`) before unplugging.
- Back up data before running `fsck -y` on a filesystem with errors.
