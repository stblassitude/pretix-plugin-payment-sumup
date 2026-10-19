# Notes and gotchas

## Customers are not sent back automatically

After a successful payment, the SumUp Hosted Checkout page shows a **success page with a
button** back to your shop. SumUp does **not** redirect automatically. Many customers close the
tab at that point.

That is fine. The payment is still confirmed through the webhook or, if the webhook can't reach
you, the next time the cronjob runs. The customer gets the usual pretix "payment received" email
once the payment is confirmed.

## Webhooks need a public HTTPS URL

SumUp sends status changes to the webhook URL of each checkout. For that to work:

- your pretix must be reachable from the internet,
- over **HTTPS** with a valid certificate,
- and the URL configured in `pretix.cfg` (`[pretix] url=`) must be the public URL. pretix uses it
  to build the webhook and return URLs it sends to SumUp.

If pretix runs behind a reverse proxy, check that `url` is the external `https://` address, not
the internal `http://` one. The SumUp settings page in pretix shows an example webhook URL and
warns you if it isn't HTTPS.

**Firewalls and IP allowlists:** SumUp does not publish a fixed list of IP addresses for
webhooks. If you restrict access to `/…/sumup/webhook/`, payments still go through, but only the
return redirect and the cronjob will confirm them.

Webhooks from SumUp are **not signed**. The plugin therefore treats a webhook only as a hint to
check the status: it always fetches the checkout from the SumUp API before it changes anything.
A forged webhook can't mark an order as paid.

## The cronjob matters

The cronjob is the safety net for every case where neither the webhook nor the customer reaches
pretix. If the cronjob doesn't run, those payments stay open until the order expires, even
though the customer has paid.

The plugin checks payments that are still open and less than 24 hours old every time the
cronjob runs. With the pretix default of twice an hour, a "lost" payment can take up to 30 minutes
to be confirmed. Consider running the cronjob [every few minutes](installation.md#check-the-cronjob).

## Payment pages expire after 30 minutes

A SumUp Hosted Checkout session is valid for 30 minutes. After that, SumUp marks the checkout as
`EXPIRED` and the plugin marks the pretix payment as failed, without sending the customer an
email. The order itself stays open until its normal payment deadline, and the customer can start
a new payment from the order page.

Keep this in mind if your pretix **reservation period** is shorter than 30 minutes. pretix can
let an order expire while the customer is still on the SumUp page. If they pay anyway, the plugin
still confirms the payment. If quota is left, pretix marks the order as paid. If the event sold
out in the meantime, pretix keeps the payment but can't mark the order as paid, and you have to
decide in the backend (accept or refund). This is the same as with every other pretix payment
provider.

## Currency must match the SumUp account

SumUp only accepts checkouts in the currency of the merchant account. The plugin hides SumUp for
events whose currency SumUp doesn't support at all. It can't know your account's currency,
though. If the event currency doesn't match your account, checkout creation fails and the
customer sees an error.

Supported currencies: BRL, CHF, CLP, COP, CZK, DKK, EUR, GBP, HUF, NOK, PLN, RON, SEK, USD.

## Checkout references must be unique per SumUp account

SumUp rejects a second checkout with the same `checkout_reference` (HTTP 409,
`DUPLICATED_CHECKOUT`). The plugin adds a random suffix to every reference, so this can't happen
by accident. To keep the SumUp dashboard readable, still give each pretix installation that shares
a SumUp account (production, staging, a test instance) its own **checkout reference prefix**.

## Online payments must be enabled at SumUp

If creating a checkout fails with HTTP 403 and `checkout_payments_not_allowed`, your SumUp account
isn't enabled for online payments. Only SumUp can change that. See
[SumUp account setup](sumup-setup.md#1-merchant-account-with-online-payments).

## Test mode never touches the live account

Orders placed while the event is in test mode always use the sandbox credentials. If none are
configured, SumUp is not offered in test mode. This means you **cannot** make a real payment
through a test-mode order. For a real end-to-end test with real money, take the event out of
test mode (or create a separate live test event) and refund afterwards.

## Payment method name

pretix shows the "Payment method name" in the shop and in emails. The default lists card, Apple
Pay and Google Pay. Which wallets SumUp actually shows depends on your SumUp account and the
customer's device. Change the name if it doesn't match what your customers will see.

## Refunds started in the SumUp dashboard

Refunds made in the SumUp dashboard are not synced to pretix. Refund from pretix where possible,
or record dashboard refunds in pretix by hand.

## Several payments on one order

If a customer starts a SumUp payment, abandons it and then picks another payment method, pretix
cancels the first payment. The plugin then also deactivates the SumUp checkout, so the old payment
page can't be paid any more. If the old checkout had already been paid in the meantime, the
cancellation is refused and the payment is confirmed instead.

## Disabling the plugin

If you disable the plugin for an event while SumUp payments are still open, SumUp's webhooks and
returning customers get a "not found" page for that event, and SumUp retries the webhook a few
times. Wait at least half an hour after the last SumUp payment was started before you disable the
plugin.

## Data protection

The plugin stores the SumUp checkout ID, checkout reference, status and transaction details
(transaction code, payment type, amounts) on the pretix payment. It does not store card numbers or
cardholder names; SumUp doesn't send them. When you use pretix's data shredder, the plugin keeps
only the IDs needed to match the payment with SumUp.
