# Infrastructure Setup Guide

**Total time: ~35 minutes**

This guide walks you through the four things you need before AI can deploy Token RugCheck MCP for you: a server, a domain, a Solana wallet, and a filled-in config file.

No coding knowledge required. Just follow each step exactly as written.

---

## Phase 1: Buy a Server

**Estimated time: 10 minutes**

You need a small Linux server (also called a VPS) that will run the service 24/7.

### 1.1 Pick a Provider

Any of these work. Pick whichever is easiest for you:

| Provider | Cheapest plan | Sign-up link |
|---|---|---|
| Vultr | $6/mo (1 vCPU, 1 GB RAM, 25 GB SSD) | https://vultr.com |
| Hetzner | ~$4/mo (1 vCPU, 2 GB RAM, 20 GB SSD) | https://hetzner.com/cloud |
| DigitalOcean | $6/mo (1 vCPU, 1 GB RAM, 25 GB SSD) | https://digitalocean.com |

**Minimum spec:** 1 vCPU, 1 GB RAM, 25 GB SSD, Ubuntu 22.04.

### 1.2 Create Your Account

1. Go to the provider's website.
2. Click **Sign Up** (top-right corner on most sites).
3. Enter your email and create a password.
4. Add a payment method (credit card or PayPal).

### 1.3 Generate an SSH Key

SSH keys let you log into the server securely without a password. Open a terminal on your computer and run:

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

- When it asks **"Enter file in which to save the key"**, press Enter to accept the default (`~/.ssh/id_ed25519`).
- When it asks for a **passphrase**, you can press Enter twice for no passphrase (simpler) or type one for extra security.

Now copy the **public** key to your clipboard:

**Mac:**
```bash
cat ~/.ssh/id_ed25519.pub | pbcopy
```

**Linux:**
```bash
cat ~/.ssh/id_ed25519.pub | xclip -selection clipboard
```

**Windows (PowerShell):**
```powershell
Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard
```

> **Tip:** The file ending in `.pub` is the public key (safe to share). The file *without* `.pub` is the private key (never share this).

### 1.4 Create the Server

The exact steps vary slightly by provider, but the general flow is:

1. Click **Create** or **Deploy New Server**.
2. **Location:** pick the region closest to you (or your users).
3. **Image / OS:** select **Ubuntu 22.04 LTS**.
4. **Plan / Size:** pick the cheapest plan that meets the minimum spec above.
5. **SSH Key:** click **Add SSH Key**, paste the public key you copied, give it a name like "my-laptop".
6. **Hostname:** enter something like `rugcheck` (this is just a label).
7. Click **Deploy** / **Create**.

Wait 30-60 seconds for the server to spin up.

### 1.5 Record the IP Address

Once the server is running, find its **IPv4 address** on the dashboard. It looks like `203.0.113.42`. Write it down -- you will need it in Phase 4.

### 1.6 Completion Test

Open a terminal and run:

```bash
ssh root@<YOUR_SERVER_IP> echo OK
```

Replace `<YOUR_SERVER_IP>` with the actual IP address.

- If you see `OK`, you are connected. Move on to Phase 2.
- If you see a fingerprint prompt ("Are you sure you want to continue connecting?"), type `yes` and press Enter. You should then see `OK`.

> **Common mistake:** If you get "Permission denied", the SSH key was not added correctly. Go back to your provider's dashboard, find the SSH Keys section, and make sure the key is attached to your server. Some providers require you to rebuild the server after adding a key.

> **Common mistake:** If you get "Connection timed out", wait 1-2 minutes -- the server may still be booting. Also check that the IP address is correct.

---

## Phase 2: Domain & Cloudflare

**Estimated time: 15 minutes**

You need a domain name (like `rugcheck.example.com`) and Cloudflare to handle SSL and protect your server.

### 2.1 Get a Domain

**If you already own a domain:** you can create a subdomain (e.g., `rugcheck.yourdomain.com`) and skip buying a new one.

**If you need a new domain:** buy one from any registrar (Namecheap, Cloudflare Registrar, Google Domains, etc.). A `.com` or `.xyz` domain costs $1-10/year.

### 2.2 Create a Cloudflare Account

1. Go to https://cloudflare.com and click **Sign Up**.
2. Enter your email and create a password.
3. Cloudflare's free plan is all you need -- select **Free** when asked.

### 2.3 Add Your Domain to Cloudflare

1. After signing in, click **Add a site** (or **Add site** on the dashboard).
2. Type your domain name (e.g., `example.com` -- the root domain, not a subdomain) and click **Add site**.
3. Select the **Free** plan and click **Continue**.
4. Cloudflare will scan your existing DNS records. Click **Continue**.
5. Cloudflare will show you two **nameservers** (they look like `ada.ns.cloudflare.com` and `hal.ns.cloudflare.com`).

### 2.4 Change Your Nameservers

Go to the registrar where you bought your domain:

1. Find the **Nameservers** or **DNS** section in your domain settings.
2. Replace the existing nameservers with the two Cloudflare nameservers.
3. Save.

> **Tip:** Nameserver changes can take 5 minutes to 24 hours to propagate, but usually take less than 30 minutes.

### 2.5 Create a DNS Record

Back in Cloudflare:

1. Click your domain to open its dashboard.
2. In the left sidebar, click **DNS** then **Records**.
3. Click **Add record**.
4. Fill in:
   - **Type:** `A`
   - **Name:** your subdomain (e.g., `rugcheck`) or `@` for the root domain
   - **IPv4 address:** your server IP from Phase 1
   - **Proxy status:** make sure the orange cloud icon is ON (it should say **Proxied**)
   - **TTL:** leave as **Auto**
5. Click **Save**.

### 2.6 Set SSL Mode

1. In the left sidebar, click **SSL/TLS** then **Overview**.
2. Set encryption mode to **Flexible**.

> **Warning:** Do not choose "Full" or "Full (strict)" unless you know what you are doing. "Flexible" works without any extra server configuration. The AI will handle upgrading this later if needed.

### 2.7 Completion Test

Open a terminal and run:

```bash
dig +short <YOUR_DOMAIN>
```

Replace `<YOUR_DOMAIN>` with your full domain (e.g., `rugcheck.example.com`).

- You should see one or more IP addresses. If Cloudflare proxy is active, these will be Cloudflare IPs (not your server IP) -- that is correct.
- If you see nothing, nameservers have not propagated yet. Wait 10-15 minutes and try again.

> **Common mistake:** If `dig` is not installed, use `nslookup <YOUR_DOMAIN>` instead.

> **Common mistake:** If you created a subdomain record (e.g., `rugcheck`) but are testing the root domain (e.g., `example.com`), you will not see results. Test the full domain including subdomain: `dig +short rugcheck.example.com`.

---

## Phase 3: Solana Wallet

**Estimated time: 5 minutes**

You need a Solana wallet address that will receive payments, and an RPC URL to connect to the Solana network.

### 3.1 Create a Seller Wallet

You have two options. Pick whichever you prefer:

**Option A: Phantom Browser Extension (easiest)**

1. Go to https://phantom.app and install the browser extension.
2. Click **Create a new wallet**.
3. Write down the recovery phrase on paper and store it safely.
4. Click your wallet address at the top to copy it. It looks like `7xKX...3nPm` (a long Base58 string).

**Option B: Solana CLI**

```bash
# Install
sh -c "$(curl -sSfL https://release.anza.xyz/stable/install)"

# Reload your shell
source ~/.profile

# Create a new wallet
solana-keygen new --outfile ~/.config/solana/seller.json

# Show the public address
solana address -k ~/.config/solana/seller.json
```

Write down the wallet address. This is your **seller address** -- it goes in the manifest.

> **Tip:** This wallet receives payment for API queries. You do not need to fund it. Buyers pay into it.

### 3.2 Get an RPC URL

An RPC URL is how the service talks to the Solana blockchain.

1. Go to https://helius.dev and sign up for a free account.
2. After signing in, you will see a dashboard with your API key.
3. Your RPC URL will look like: `https://mainnet.helius-rpc.com/?api-key=YOUR_KEY`
   - For devnet testing: `https://devnet.helius-rpc.com/?api-key=YOUR_KEY`
4. Copy this URL. It goes in the secrets file.

> **Tip:** The free tier gives you 100,000 requests/day, which is more than enough to start.

### 3.3 (Optional) Prepare a Buyer Test Wallet

If you want to test the payment flow end-to-end:

1. Create a second wallet (the "buyer" wallet) using either method above.
2. Export its private key (Base58 format). In Phantom: Settings > Security & Privacy > Export Private Key.
3. Fund it with a small amount of SOL or USDC ($1 is enough).
   - For devnet: use https://faucet.solana.com to get free devnet SOL.

### 3.4 Completion Test

Confirm you have these two pieces of information written down:

- [ ] Seller wallet address (Base58 string, e.g., `7xKXp...`)
- [ ] Solana RPC URL (e.g., `https://devnet.helius-rpc.com/?api-key=...`)

---

## Phase 4: Fill the Manifest

**Estimated time: 5 minutes**

Now you put everything together into two config files.

### 4.1 Copy the Templates

From the project root directory, run:

```bash
cp ops/manifest.yaml.example ops/manifest.yaml
cp ops/.env.secrets.example ops/.env.secrets
```

### 4.2 Fill in `ops/manifest.yaml`

Open `ops/manifest.yaml` in any text editor and fill in the values you collected:

| Field | What to enter | Example |
|---|---|---|
| `project.repo` | Your GitHub org/repo | `myname/Token_RugCheck_MCP` |
| `server.ip` | Server IP from Phase 1 | `203.0.113.42` |
| `server.ssh_user` | Usually `root` for new servers | `root` |
| `domain.name` | Full domain from Phase 2 | `rugcheck.example.com` |
| `blockchain.network` | `devnet` for testing, `mainnet` for production | `devnet` |
| `blockchain.seller_address` | Wallet address from Phase 3 | `7xKXp...3nPm` |

Leave everything else at the default values unless you know what you are doing.

> **Warning:** Do not put any secrets (private keys, RPC URLs, API keys) in this file. It is tracked by git.

### 4.3 Fill in `ops/.env.secrets`

Open `ops/.env.secrets` and fill in:

| Field | What to enter |
|---|---|
| `SOLANA_RPC_URL` | RPC URL from Phase 3 |
| `BUYER_PRIVATE_KEY` | (Only if testing payments) Buyer wallet private key |

Leave the optional fields empty for now. They can be added later.

> **Warning:** Never commit this file to git. It is already in `.gitignore`.

### 4.4 Completion Test

Run this from the project root:

```bash
# Check manifest exists and has no placeholder values left
grep '<YOUR_' ops/manifest.yaml
```

- If the command prints nothing, all placeholders have been replaced. You are done.
- If it prints lines, those fields still need to be filled in.

```bash
# Check secrets file exists
test -f ops/.env.secrets && echo "Secrets file exists" || echo "Missing secrets file"
```

---

## You Are Done

All four phases are complete. Tell the AI:

> "Manifest is ready, please deploy."

The AI will read your manifest and secrets file, connect to your server, and handle everything from here -- installing dependencies, configuring the service, setting up HTTPS, and verifying the deployment.

---

## Quick Reference: What You Should Have

| Item | Where it goes |
|---|---|
| Server IP address | `ops/manifest.yaml` > `server.ip` |
| SSH key | `~/.ssh/id_ed25519` (referenced in manifest) |
| Domain name | `ops/manifest.yaml` > `domain.name` |
| Cloudflare account | Used to manage DNS (not stored in files) |
| Seller wallet address | `ops/manifest.yaml` > `blockchain.seller_address` |
| Solana RPC URL | `ops/.env.secrets` > `SOLANA_RPC_URL` |
| Buyer private key (optional) | `ops/.env.secrets` > `BUYER_PRIVATE_KEY` |
