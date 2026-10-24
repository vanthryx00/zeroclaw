# Verify Skill — PhantomSwarm Python Package

Cold-start recipe for verifying changes to `python/` in this repo.

## Build / Install

```bash
cd /home/user/mega-zero/python
python3 -m venv /tmp/phantom-venv
source /tmp/phantom-venv/bin/activate
pip install -q python-dotenv
```

No compilation step — pure Python.

## Launch / Drive

All four CLIs are verifiable with `--help` and functional subcommands:

```bash
# phantom_graph
python phantom_graph.py scope --target example.com --org "TestOrg" --defender smb
python phantom_graph.py graph --engagement-id <ENG-ID>
python phantom_graph.py paths --engagement-id <ENG-ID> --top 3
python phantom_graph.py lotl --os linux --priv user

# phantom_swarm
python phantom_swarm.py deploy --target example.com --operator-id TEST --defender smb
python phantom_swarm.py status --mission-id <MSN-ID>
python phantom_swarm.py watermark
python phantom_swarm.py evolve --record T1059:smb:0:1
python phantom_swarm.py evolve --shifts

# phantom_bounty
python phantom_bounty.py new --program "Test Corp" --paste /tmp/scope.txt
python phantom_bounty.py approve --bounty-id <BNT-ID> --check-all
python phantom_bounty.py finding --bounty-id <BNT-ID> --title "XSS" --severity HIGH \
    --target "https://app.example.com" --description "reflected"
python phantom_bounty.py proof --bounty-id <BNT-ID>

# phantom_hud
python phantom_hud.py --once          # single snapshot; no loop
python phantom_hud.py --once --db ./phantom_swarm.db
```

## Key Gotchas

- `phantom_hud.py`: `global DB_PATH` must be the FIRST line inside `main()` — before any `argparse` call that references `DB_PATH` as a default. Python raises `SyntaxError: name used prior to global declaration` otherwise.
- `phantom_swarm.py` imports `phantom_graph as _pg` — both files must be in the same directory.
- DB path defaults to `./phantom_swarm.db`; set `PHANTOM_DB` env var to override.
- `PHANTOM_SECRET` env var drives HMAC watermark signing. If unset, defaults to a placeholder.

## Flows Worth Driving

1. Full graph chain: `scope` → `graph` → `paths` → `narrative` (phantom_graph)
2. Full swarm loop: `deploy` → `status` → `approve` → `report` → `evolve` (phantom_swarm)
3. Bounty flow: `new` → `read` → `approve --check-all` → `finding` → `proof` (phantom_bounty)
4. HUD snapshot: `--once` with a pre-populated DB (phantom_hud)

## Edge Cases to Probe

- Nonexistent IDs: should return clean `[-] Not found` messages, not stack traces
- Missing scope text: `phantom_bounty.py new` without `--paste` → `[-] No scope text provided.`
- Empty DB: HUD with no missions → `No missions found. Run: python phantom_swarm.py deploy ...`
