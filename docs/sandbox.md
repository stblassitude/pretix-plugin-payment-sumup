# Docker sandbox

The `sandbox/` directory contains a Docker Compose setup with everything you need to try the
plugin against a SumUp **sandbox merchant account**:

| Service | Purpose | URL |
| --- | --- | --- |
| `pretix` | pretix (official `pretix/standalone` image) with the plugin installed from your working copy | <http://localhost:8345/control/> |
| `cron` | Runs `pretix cron` every minute | – |
| `postgres` | Database | – |
| `redis` | Cache, sessions, task queue | – |
| `mailpit` | Catches all emails pretix sends | <http://localhost:8025/> |
| `tunnel` | *Optional* Cloudflare quick tunnel, so that SumUp can deliver webhooks | – |

## Start

```bash
git clone https://github.com/stblassitude/pretix-plugin-payment-sumup.git
cd pretix-plugin-payment-sumup/sandbox
cp .env.example .env
docker compose up --build -d
```

The first start takes a few minutes while pretix creates its database. On Apple Silicon Macs the
pretix image runs under amd64 emulation, which makes it noticeably slower. Wait until
`docker compose ps` shows `pretix` as `healthy`.

Log in at <http://localhost:8345/control/> with **`admin@localhost`** / **`admin`**. pretix asks
you to change the password.

## Set up a test event

1. Create an organizer and an event (any currency SumUp supports, e.g. EUR).
2. Add a product and a quota so that there is something to buy.
3. In the event, go to **Settings → Plugins → Payment providers** and enable
   **SumUp Hosted Checkout**.
4. Go to **Settings → Payment → SumUp Hosted Checkout**, enter the API key and merchant code of
   your **SumUp sandbox merchant account** in the *Sandbox* fields, and enable the payment
   method. See [SumUp account setup](sumup-setup.md#4-optional-sandbox-merchant-account) for how
   to get them.
5. Put the event into **test mode** (event dashboard → *Shop status*) and open the shop.

Buy a ticket and pick SumUp. You are sent to the real SumUp Hosted Checkout page of your sandbox
account.

- Pay any amount other than 11.00 to test a successful payment.
- Pay **11.00** to test a failed payment.

## Without a tunnel: localhost

On `http://localhost:8345` SumUp can't reach your webhook URL. The flow still works:

- Click the **back to shop** button on SumUp's success page, and the payment is confirmed right
  away; or
- close the SumUp tab, and the `cron` service confirms the payment within about a minute.

This is also a good test for the "customer never returns" case.

## With a tunnel: webhooks

To test webhooks, pretix has to be reachable over public HTTPS. The `tunnel` profile starts a
[Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
(no account needed):

```bash
docker compose --profile tunnel up -d tunnel
docker compose logs tunnel | grep trycloudflare.com
```

Copy the `https://<random-words>.trycloudflare.com` URL into `.env`:

```bash title=".env"
PRETIX_URL=https://random-words.trycloudflare.com
```

Then recreate the pretix containers so that pretix uses the new URL:

```bash
docker compose up -d
```

From now on, open pretix **through the tunnel URL**, not through localhost. pretix's CSRF
protection rejects forms sent from an address other than the configured one. Every time the tunnel
restarts it gets a new random URL, and you have to repeat this step.

Any other HTTPS tunnel (ngrok, Tailscale Funnel, your own reverse proxy) works the same way: point
it at port 8345 and set `PRETIX_URL`.

## Working on the plugin

The plugin source (`pretix_payment_sumup/`) is mounted into the containers and installed in
editable mode. After changing Python code or templates, restart pretix:

```bash
docker compose restart pretix cron
```

You only need `docker compose up --build` again after changing `pyproject.toml` or
`setup.py`. Translations (`.po` files) are compiled every time the container starts.

To use a specific pretix release instead of `stable`, set `PRETIX_VERSION` in `.env` (e.g.
`PRETIX_VERSION=2026.8.0`) and rebuild.

Useful commands:

```bash
docker compose logs -f pretix cron          # follow logs
docker compose exec pretix pretix shell     # Django shell
docker compose down                         # stop
docker compose down -v                      # stop and delete all data
```
