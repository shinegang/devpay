# DevPay

**A pay-per-task desk for Solana Devnet.**

Employers post tasks with a Devnet bounty. Agents claim tasks with a lease,
post results, and get paid with a **real on-chain transfer**. Every payment is
a verifiable Solana Devnet transaction with a Solscan receipt.

No custom programs. No tokens to deploy. DevPay uses Solana's existing
**system program** and plain JSON files for coordination — the pay-per-task
coordination model (think Frantic/Opire), self-hosted on Devnet.

## Why

Coordinating paid work between people (or agents) is manual: someone does the
math, fires N transfers by hand, and nobody has a clean receipt trail.

DevPay makes the desk itself the product:

- **Job board** — tasks with bounties, assignment, status
- **Leases** — claims expire; an expired lease re-opens the job
- **Real payments** — one command pays the bounty with a real Devnet transfer
- **On-chain receipts** — every payment is verifiable on Solscan
- **Journal** — append-only audit trail of every event

## Quickstart

```bash
pip install pynacl
python devpay.py init
```

`init` creates `payer.json` (your employer keypair — keep it local),
`board.json`, and `journal.jsonl`.

Fund the payer with Devnet SOL:

```bash
python devpay.py faucet            # retries are normal: faucet rate-limits per IP
```

or grab SOL from https://faucet.solana.com (paste the pubkey printed by `init`).

Post a task:

```bash
python devpay.py post --title "Write a haiku about devnet" \
  --desc "Post one haiku in the demo thread" --bounty 50000000
```

The agent side (any other machine, wallet, or agent process):

```bash
python devpay.py board
python devpay.py claim 1 --agent <AGENT_PUBKEY> --lease 3600
python devpay.py done 1 --result "lamports fall like rain / a task claimed with one short lease / devnet pays in peace"
```

Pay (employer's machine — real Devnet transfer):

```bash
python devpay.py pay 1
# job 1 PAID: 50000000 lamports -> <AGENT_PUBKEY>
#   tx: https://solscan.io/tx/<SIG>?cluster=devnet
#   err: None
```

Verify any receipt:

```bash
python devpay.py verify <SIG>
```

## Commands

| Command | What it does |
|---|---|
| `init` | create board, journal, payer keypair |
| `post --title T --desc D --bounty LAMPORTS [--assignee PUBKEY] [--ttl SEC]` | post a task |
| `board` | show the job board |
| `claim JOB --agent PUBKEY [--lease SEC]` | claim with a lease |
| `done JOB --result TEXT` | post the result (lease-guarded) |
| `pay JOB` | **real Devnet transfer** + receipt |
| `journal [--last N]` | append-only audit trail |
| `verify SIG` | verify a receipt on-chain |
| `faucet [--pubkey P --amount L]` | request Devnet SOL |
| `export-html` | static board page for GitHub Pages |

## How the Solana integration works

- **Payments** are legacy system-program transfers (`ix 2 = Transfer`), signed
  locally with ed25519 (pynacl) against the Devnet recent blockhash, sent via
  `sendTransaction` (base58), and confirmed with `getTransaction`.
- **No custom programs, no SPL tokens** — the transfer is as plain as Solana gets.
- The payer keypair never leaves your machine; only the pubkey is shared.
- The agent pubkey is provided by the claimer — the agent owns its own keys.

## Deployment

DevPay runs on **Devnet** by default (`DEVPAY_RPC` env switches the RPC).
The payer account and every payment transaction are on Devnet — receipts
resolve at `https://solscan.io/tx/<SIG>?cluster=devnet`.

`devpay.py export-html` renders the live board + journal to a static page —
serve it from GitHub Pages so judges can see the receipts without cloning.

## License

MIT
