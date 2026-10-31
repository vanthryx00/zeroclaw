# Networking Basics

## Layers you will actually touch

| Layer | Examples | Tools |
|-------|----------|-------|
| L2 (Ethernet/ARP) | MAC addresses, ARP | `arp`, `arping`, `bettercap` |
| L3 (IP) | IPv4/IPv6, routing | `ip a`, `ip r`, `ping`, `traceroute` |
| L4 (TCP/UDP) | ports, handshakes | `ss`, `nmap`, `netcat` |
| L7 (application) | HTTP, DNS, SMB, SSH | `curl`, `dig`, `smbclient`, `ssh` |

## TCP vs UDP

* **TCP** is connection-oriented: 3-way handshake (SYN, SYN-ACK, ACK), reliable,
  ordered. Services: HTTP 80, HTTPS 443, SSH 22, SMB 445, RDP 3389.
* **UDP** is connectionless: fire-and-forget, faster, no guarantee. Services:
  DNS 53, DHCP 67/68, SNMP 161, NTP 123.

## The three-way handshake and why scans differ

* **Connect scan** (`nmap -sT`): full handshake. Noisy but needs no privilege.
* **SYN scan** (`nmap -sS`): sends SYN, reads SYN-ACK, then resets. "Half-open",
  stealthier, needs root.
* **UDP scan** (`nmap -sU`): slow; interprets ICMP port-unreachable vs silence.

## Port states

* **open** — a service is listening.
* **closed** — reachable but nothing listening (host replied).
* **filtered** — no reply; a firewall dropped it.

## DNS

Resolution path: stub resolver → recursive resolver → root → TLD → authoritative.

```bash
dig example.com            # A record
dig MX example.com         # mail
dig +short TXT example.com # SPF, verification tokens
dig axfr @ns.example.com example.com   # zone transfer (usually refused)
```

## Routing and interfaces

```bash
ip a          # addresses
ip r          # routes; default gateway is the path off-subnet
ip neigh      # ARP/neighbour cache
```

## Packet capture

```bash
tcpdump -i eth0 -nn port 80          # live, no name resolution
tcpdump -i eth0 -w cap.pcap          # write to file
tshark -r cap.pcap -Y http           # filter after the fact
```
