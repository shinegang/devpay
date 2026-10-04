#!/usr/bin/env python3
"""
DevPay — a pay-per-task desk for Solana Devnet.

Employers post tasks with a Devnet bounty. Agents claim tasks with a lease,
post results, and get paid with a real on-chain transfer. Every payment is
a real Solana Devnet transaction (system program) with a verifiable receipt.

No custom programs, no tokens: DevPay uses Solana's existing system program
and plain JSON files for coordination. This is the Frantic/Opire coordination
model, self-hosted on Devnet.

Usage:
  devpay init                                   # create board, journal, keypair
  devpay post --title T --desc D --bounty LAMPORTS [--assignee PUBKEY] [--ttl SEC]
  devpay board                                  # show the job board
  devpay claim JOB_ID --agent PUBKEY [--lease SEC]
  devpay done JOB_ID --result TEXT
  devpay pay JOB_ID                             # real Devnet transfer + receipt
  devpay journal [--last N]
  devpay verify TX_SIGNATURE                    # verify a receipt on-chain
  devpay export-html [--out PATH]               # static board page for GitHub Pages
"""
import argparse, base64, json, os, struct, sys, time, urllib.error, urllib.request

RPC = os.environ.get('DEVPAY_RPC', 'https://api.devnet.solana.com')
FAUCET = 'https://faucet.solana.com'
UA = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
BOARD = 'board.json'
JOURNAL = 'journal.jsonl'
KEYPAIR = 'payer.json'
SYSTEM_PROGRAM = '11111111111111111111111111111111'

# ---------------------------------------------------------------- base58
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def b58encode(b: bytes) -> str:
    n, out = int.from_bytes(b, 'big'), ''
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    for c in b:
        if c == 0: out = '1' + out
        else: break
    return out or '1'

def b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    pad = 0
    for c in s:
        if c == '1': pad += 1
        else: break
    body = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return b'\x00' * pad + body

# ---------------------------------------------------------------- rpc
def rpc(method, params):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(RPC, data=body, headers=UA)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    except urllib.error.HTTPError as e:
        return {'error': {'code': e.code, 'message': f'HTTP {e.code}'}}
    except Exception as e:
        return {'error': {'message': str(e)[:80]}}

def solscan(sig: str) -> str:
    return f'https://solscan.io/tx/{sig}?cluster=devnet'

# ---------------------------------------------------------------- signing
def load_signing_key():
    if not os.path.exists(KEYPAIR):
        sys.exit(f'no {KEYPAIR} — run: devpay init')
    seed = bytes(json.load(open(KEYPAIR)))
    from nacl.signing import SigningKey
    return SigningKey(seed)

def shortvec(n: int) -> bytes:
    out = b''
    while True:
        b = n & 0x7F
        n >>= 7
        if n: out += bytes([b | 0x80])
        else:
            out += bytes([b]); break
    return out

def build_transfer_tx(sk, to_pub: bytes, lamports: int, blockhash: str) -> bytes:
    """Legacy system-program transfer: VersionedTransaction wire format."""
    from_pub = sk.verify_key.encode()
    header = bytes([1, 0, 1])  # 1 required sig, 0 readonly signed, 1 readonly unsigned
    keys = [from_pub, to_pub, b58decode(SYSTEM_PROGRAM)]
    ix_data = struct.pack('<IQ', 2, lamports)  # ix 2 = transfer, lamports LE
    msg = header + shortvec(len(keys))
    for k in keys:
        msg += k
    msg += b58decode(blockhash)
    msg += shortvec(1) + bytes([2]) + shortvec(2) + bytes([0, 1]) + shortvec(len(ix_data)) + ix_data
    sig = sk.sign(msg).signature
    return shortvec(1) + sig + msg, sig

# ---------------------------------------------------------------- journal
def journal(event: dict):
    event['ts'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with open(JOURNAL, 'a') as f:
        f.write(json.dumps(event) + '\n')

def journal_read(last=20):
    if not os.path.exists(JOURNAL):
        return []
    return [json.loads(l) for l in open(JOURNAL).read().strip().splitlines()][-last:]

# ---------------------------------------------------------------- board
def board_read():
    if os.path.exists(BOARD):
        return json.load(open(BOARD))
    return {'jobs': {}, 'next_id': 1}

def board_write(b):
    with open(BOARD, 'w') as f:
        json.dump(b, f, indent=2)

# ---------------------------------------------------------------- commands
def cmd_init(_):
    if not os.path.exists(KEYPAIR):
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        json.dump(list(bytes(sk)), open(KEYPAIR, 'w'))
        print(f'keypair -> {KEYPAIR} (pubkey: {b58encode(sk.verify_key.encode())})')
    if not os.path.exists(BOARD):
        board_write(board_read())
        print(f'board -> {BOARD}')
    if not os.path.exists(JOURNAL):
        open(JOURNAL, 'w').close()
        print(f'journal -> {JOURNAL}')
    journal({'event': 'init', 'by': b58encode(load_signing_key().verify_key.encode())})
    print('devpay ready. Fund the payer via the devnet faucet, then: devpay post ...')

def cmd_post(a):
    sk = load_signing_key()
    b = board_read()
    jid = str(b['next_id']); b['next_id'] += 1
    job = {
        'id': jid, 'title': a.title, 'desc': a.desc, 'bounty_lamports': a.bounty,
        'assignee': a.assignee, 'ttl_seconds': a.ttl,
        'status': 'open', 'claimed_by': None, 'lease_until': None,
        'result': None, 'payment': None, 'posted_by': b58encode(sk.verify_key.encode()),
        'posted_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    b['jobs'][jid] = job
    board_write(b)
    journal({'event': 'posted', 'job': jid, 'title': a.title, 'bounty_lamports': a.bounty})
    print(f'job {jid} posted: {a.title} ({a.bounty} lamports = {a.bounty/1e9:.4f} SOL)')

def cmd_board(_):
    b = board_read()
    if not b['jobs']:
        print('(empty board)')
        return
    for jid, j in sorted(b['jobs'].items()):
        pay = ''
        if j.get('payment'):
            pay = f" | tx {j['payment']['signature'][:12]}..."
        lease = f" | lease -> {j['lease_until']}" if j.get('lease_until') else ''
        print(f"[{j['status']:>8}] #{jid} {j['bounty_lamports']/1e9:.4f} SOL | {j['title'][:48]}{lease}{pay}")

def cmd_claim(a):
    b = board_read()
    j = b['jobs'].get(a.job)
    if not j: sys.exit(f'no job {a.job}')
    if j['status'] != 'open': sys.exit(f"job {a.job} is {j['status']}, not open")
    if j['assignee'] and j['assignee'] != a.agent:
        sys.exit(f'job {a.job} is assigned to {j["assignee"]}')
    now = time.time()
    j['status'] = 'claimed'
    j['claimed_by'] = a.agent
    j['lease_until'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now + a.lease))
    board_write(b)
    journal({'event': 'claimed', 'job': a.job, 'agent': a.agent, 'lease_until': j['lease_until']})
    print(f"job {a.job} claimed by {a.agent} (lease {a.lease}s -> {j['lease_until']})")

def cmd_done(a):
    b = board_read()
    j = b['jobs'].get(a.job)
    if not j: sys.exit(f'no job {a.job}')
    if j['status'] != 'claimed': sys.exit(f"job {a.job} is {j['status']}, claim first")
    # lease guard: expired lease re-opens the job
    if j.get('lease_until'):
        lu = time.mktime(time.strptime(j['lease_until'], '%Y-%m-%dT%H:%M:%SZ')) - time.timezone
        if time.time() > lu:
            j.update({'status': 'open', 'claimed_by': None, 'lease_until': None})
            board_write(b)
            sys.exit(f"lease expired — job {a.job} re-opened")
    j['status'] = 'done'
    j['result'] = a.result
    board_write(b)
    journal({'event': 'done', 'job': a.job, 'agent': j['claimed_by'], 'result': a.result[:80]})
    print(f"job {a.job} done -> pay with: devpay pay {a.job}")

def cmd_pay(a):
    sk = load_signing_key()
    b = board_read()
    j = b['jobs'].get(a.job)
    if not j: sys.exit(f'no job {a.job}')
    if j['status'] != 'done': sys.exit(f"job {a.job} is {j['status']}, not done")
    if j.get('payment'): sys.exit(f"job {a.job} already paid: {solscan(j['payment']['signature'])}")
    to = j['claimed_by']
    if not to: sys.exit(f"job {a.job} has no claimer")
    payer_b58 = b58encode(sk.verify_key.encode())
    bal = rpc('getBalance', [payer_b58])
    have = bal.get('result', {}).get('value', 0)
    need = j['bounty_lamports'] + 5000
    if have < need:
        sys.exit(f'payer {payer_b58} has {have} lamports, needs {need}. Fund via faucet.')
    bh = rpc('getLatestBlockhash', [{'commitment': 'finalized'}])['result']['value']['blockhash']
    tx, sig = build_transfer_tx(sk, b58decode(to), j['bounty_lamports'], bh)
    r = rpc('sendTransaction', [b58encode(tx), {'encoding': 'base58', 'preflightCommitment': 'confirmed'}])
    if r.get('error'):
        sys.exit(f'send failed: {r["error"].get("message", r["error"])}')
    sig_b58 = b58encode(sig)
    time.sleep(3)
    conf = rpc('getTransaction', [sig_b58, {'encoding': 'json', 'maxSupportedTransactionVersion': 0}])
    err = (conf.get('result') or {}).get('meta', {}).get('err', 'unconfirmed-yet')
    j['payment'] = {'signature': sig_b58, 'err': err if err else None,
                    'lamports': j['bounty_lamports'], 'to': to, 'network': 'devnet',
                    'confirmed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    j['status'] = 'paid'
    board_write(b)
    journal({'event': 'paid', 'job': a.job, 'to': to, 'lamports': j['bounty_lamports'],
             'signature': sig_b58, 'err': err})
    print(f"job {a.job} PAID: {j['bounty_lamports']} lamports -> {to}")
    print(f"  tx: {solscan(sig_b58)}")
    print(f"  err: {err}")

def cmd_journal(a):
    for e in journal_read(a.last):
        print(f"{e['ts']} {e['event']:>8} {json.dumps({k: v for k, v in e.items() if k not in ('ts', 'event')})[:110]}")

def cmd_verify(a):
    conf = rpc('getTransaction', [a.signature, {'encoding': 'json', 'maxSupportedTransactionVersion': 0}])
    res = conf.get('result')
    if not res:
        print(f"tx {a.signature}: NOT FOUND on {RPC}")
        return
    meta = res.get('meta', {})
    block_time = res.get('blockTime')
    when = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(block_time)) if block_time else '?'
    print(f"tx {a.signature}")
    print(f"  err: {meta.get('err')} | block: {when} | fee: {meta.get('fee')} lamports")
    print(f"  link: {solscan(a.signature)}")

def cmd_faucet(a):
    pub = a.pubkey or b58encode(load_signing_key().verify_key.encode())
    body = json.dumps({'wallet': pub, 'amount': a.amount}).encode()
    req = urllib.request.Request(FAUCET, data=body, headers=UA)
    try:
        print(json.loads(urllib.request.urlopen(req, timeout=30).read().decode()))
    except urllib.error.HTTPError as e:
        print(f'HTTP {e.code} — faucet rate-limited, try again in a few minutes')
    except Exception as e:
        print(f'ERR {str(e)[:60]}')

def cmd_export_html(a):
    b = board_read()
    rows = ''
    for jid, j in sorted(b['jobs'].items(), key=lambda x: int(x[0])):
        tx = ''
        if j.get('payment'):
            s = j['payment']['signature']
            tx = f"<a href='{solscan(s)}'>{s[:16]}…</a> ({'OK' if not j['payment'].get('err') else 'ERR: ' + str(j['payment']['err'])})"
        rows += (f"<tr><td>#{jid}</td><td>{j['title']}</td><td>{j['desc'][:80]}</td>"
                 f"<td>{j['bounty_lamports']/1e9:.4f} SOL</td><td>{j['status']}</td>"
                 f"<td>{(j.get('claimed_by') or '')[:12]}</td><td>{tx}</td></tr>\n")
    jrows = ''.join(f"<tr><td>{e['ts']}</td><td>{e['event']}</td><td>{json.dumps({k: v for k, v in e.items() if k not in ('ts', 'event')})[:120]}</td></tr>\n"
                    for e in journal_read(40))
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>DevPay — pay-per-task desk for Solana Devnet</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;max-width:1080px;margin:24px auto;padding:0 16px;color:#e6e6e6;background:#16161e}}
h1{{font-size:1.4em}} a{{color:#7aa2f7}} table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:.88em}}
td,th{{border:1px solid #2a2a3a;padding:6px 8px;text-align:left}} th{{background:#1f1f2e}}
code{{background:#1f1f2e;padding:1px 5px;border-radius:4px}}</style></head><body>
<h1>DevPay — pay-per-task desk for Solana Devnet</h1>
<p>Employers post tasks with a Devnet bounty. Agents claim with a lease, post results,
get paid with a <b>real on-chain transfer</b> (system program — no custom programs).
Every payment has a verifiable Solscan receipt below.</p>
<h2>Job board</h2>
<table><tr><th>ID</th><th>Title</th><th>Desc</th><th>Bounty</th><th>Status</th><th>Claimer</th><th>Payment tx</th></tr>
{rows}</table>
<h2>Journal (audit trail)</h2>
<table><tr><th>Time (UTC)</th><th>Event</th><th>Details</th></tr>
{jrows}</table>
<p>Try it: <code>git clone && pip install pynacl && python devpay.py init</code> — README has the full walkthrough.</p>
</body></html>"""
    out = a.out or 'index.html'
    with open(out, 'w') as f:
        f.write(html)
    print(f'board page -> {out} (serve via GitHub Pages for a live MVP link)')

# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(prog='devpay')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init').set_defaults(fn=cmd_init)
    s = sub.add_parser('post'); s.add_argument('--title', required=True)
    s.add_argument('--desc', required=True); s.add_argument('--bounty', type=int, required=True)
    s.add_argument('--assignee'); s.add_argument('--ttl', type=int, default=86400)
    s.set_defaults(fn=cmd_post)
    sub.add_parser('board').set_defaults(fn=cmd_board)
    s = sub.add_parser('claim'); s.add_argument('job'); s.add_argument('--agent', required=True)
    s.add_argument('--lease', type=int, default=86400)
    s.set_defaults(fn=cmd_claim)
    s = sub.add_parser('done'); s.add_argument('job'); s.add_argument('--result', required=True)
    s.set_defaults(fn=cmd_done)
    s = sub.add_parser('pay'); s.add_argument('job')
    s.set_defaults(fn=cmd_pay)
    s = sub.add_parser('journal'); s.add_argument('--last', type=int, default=20)
    s.set_defaults(fn=cmd_journal)
    s = sub.add_parser('verify'); s.add_argument('signature')
    s.set_defaults(fn=cmd_verify)
    s = sub.add_parser('faucet'); s.add_argument('--pubkey'); s.add_argument('--amount', type=int, default=1_000_000_000)
    s.set_defaults(fn=cmd_faucet)
    s = sub.add_parser('export-html'); s.add_argument('--out')
    s.set_defaults(fn=cmd_export_html)
    a = p.parse_args()
    a.fn(a)

if __name__ == '__main__':
    main()
