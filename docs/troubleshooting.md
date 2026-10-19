# Troubleshooting

## SumUp is not offered in the shop

Check these, in order:

1. The plugin is enabled for the event (**Settings → Plugins**).
2. The payment method is enabled (**Settings → Payment → SumUp Hosted Checkout**).
3. **Test mode:** if the event is in test mode, sandbox credentials must be set. Without them,
   SumUp is hidden in test mode on purpose.
4. **Currency:** the event currency must be one SumUp supports (see
   [gotchas](gotchas.md#currency-must-match-the-sumup-account)).
5. The standard pretix restrictions: availability dates, minimum/maximum totals, countries, sales
   channels, "hidden" payment method links.

## Saving the settings fails with "SumUp rejected the API key"

- You may have used the public key (`sup_pk_…`). You need a secret key (`sup_sk_…`).
- The key may have been revoked in the SumUp dashboard.
- A sandbox key doesn't work in the live fields and vice versa.

## Saving the settings fails with "The API key belongs to merchant code …"

The key and the merchant code belong to different SumUp accounts. This often happens with
sandbox accounts: switch to the sandbox account in the SumUp dashboard to see its merchant code.

## Customers see "We could not start the payment with SumUp"

Open the order in the pretix backend and expand the failed payment. The SumUp error message is
shown there. Common causes:

| Error | Cause |
| --- | --- |
| `checkout_payments_not_allowed` / HTTP 403 | Online payments are not enabled for the SumUp account. Contact SumUp. |
| `Unauthorized` / HTTP 401 | API key revoked or wrong. |
| Validation error on `currency` | Event currency doesn't match the SumUp account currency. |
| `DUPLICATED_CHECKOUT` / HTTP 409 | Should not happen because references are randomized. Please report a bug. |
| `Could not connect to SumUp` | pretix can't reach `api.sumup.com`. Check outgoing HTTPS from the pretix server. |

## The customer paid but the order is still unpaid

1. Expand the payment in the backend. If the checkout status shows `PAID`, the plugin has seen the
   payment. Look at the order log for a message about **quota** (event sold out after the order
   expired) or an **amount mismatch**.
2. If the status still shows `PENDING`, the plugin hasn't heard back yet:
    - Is the cronjob running? (`docker exec pretix.service pretix cron` should run without errors.)
    - Is the webhook URL reachable? Try
      `curl -X POST https://<your-pretix>/<org>/<event>/sumup/webhook/1/ -d '{}'` from outside
      your network. You should get HTTP 204 (or 400 for the invalid body), not a timeout or 403.
3. The customer can also click **Check status** on their order page, which asks SumUp right away.

## Logs

The plugin logs to the Python loggers `pretix_payment_sumup.*`. In the pretix Docker image, these
messages end up in `/data/logs/pretix.log` and in the container output. Failed SumUp API calls are
logged at level `WARNING`, together with the SumUp error response.
