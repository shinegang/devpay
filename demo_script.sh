#!/bin/bash
# DevPay demo script — full flow, paced for 2-3 min
export PATH="/opt/homebrew/bin:$PATH"
DP="/tmp/solvenv/bin/python /tmp/devpay/devpay.py"

clear
echo "DevPay — a pay-per-task desk for Solana Devnet"
echo "post tasks → claim with a lease → get paid with a real on-chain transfer"
echo "========================================================================="
echo ""
sleep 6

echo "# STEP 1: init creates the board, journal, and employer keypair (kept local)"
echo "\$ devpay init"
$DP init 2>&1 | tail -4
echo ""
sleep 6

echo "# STEP 2: the employer posts tasks with Devnet bounties"
echo "\$ devpay post --title \"Write a haiku about devnet\" --bounty 50000000"
$DP post --title "Write a haiku about devnet" --desc "Post one haiku in the demo thread" --bounty 50000000 2>&1 | tail -1
sleep 2
echo "\$ devpay post --title \"Sketch the logo for v2\" --bounty 120000000 --assignee AgentBob..."
$DP post --title "Sketch the logo for v2" --desc "Draw a rough logo concept" --bounty 120000000 --assignee AgentBob1111111111111111111111111111111111 2>&1 | tail -1
echo ""
sleep 6

echo "# STEP 3: the job board — tasks with bounties, status, leases"
echo "\$ devpay board"
$DP board
echo ""
sleep 6

echo "# STEP 4: an agent claims with a time-boxed lease (expired leases re-open the job)"
echo "\$ devpay claim 1 --agent AgentAlice1111... --lease 3600"
$DP claim 1 --agent AgentAlice1111111111111111111111111111111111 --lease 3600
sleep 3
echo "\$ devpay done 1 --result \"lamports fall like rain / ...\""
$DP done 1 --result "lamports fall like rain / a task claimed with one short lease / devnet pays in peace"
echo ""
sleep 6

echo "# STEP 5: the journal — append-only audit trail of every event"
echo "\$ devpay journal --last 8"
$DP journal --last 8
echo ""
sleep 6

echo "# STEP 6: payment — one command, a REAL Devnet transfer (system program, ed25519)"
echo "\$ devpay pay 1"
$DP pay 1 2>&1 | head -4
echo ""
echo "(the payer is funded via the devnet faucet — once funded, every payment lands"
echo " on-chain with a verifiable Solscan receipt: https://solscan.io/tx/<SIG>?cluster=devnet)"
sleep 8

echo "# STEP 7: receipts are verifiable on-chain — here against a REAL mainnet tx"
echo "# (the Streamflow burn tx, 699,994,595 STREAM):"
echo "\$ DEVPAY_RPC=mainnet devpay.py verify <burn tx>"
DEVPAY_RPC=https://api.mainnet-beta.solana.com /tmp/solvenv/bin/python /tmp/devpay/devpay.py verify 4rbViHbmCV35ttMngeC8KBULCMctD7X8mNg3RxfvGwPKyPi7hX8VKpjyJ81AnYuVzzXEsWuNuppcpDY47hnchZNv
echo ""
sleep 7

echo "# STEP 8: the live board — the same state served from GitHub Pages"
echo "https://junkiesolver.github.io/claude-builders-bounty/"
echo "(export-html renders the board + journal to a static page for GitHub Pages)"
echo ""
sleep 7

echo "DevPay: post → claim (lease) → done → pay → receipts."
echo "Real Solana Devnet transfers. No custom programs. Plain JSON coordination."
sleep 5
