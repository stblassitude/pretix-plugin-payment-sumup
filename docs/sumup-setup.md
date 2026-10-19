# SumUp account setup

There is **no URL, domain or webhook to register** in the SumUp dashboard. The plugin tells SumUp
where to send the customer and the webhook separately for every checkout it creates. On the SumUp
side you only need:

1. a merchant account that is allowed to take **online payments**,
2. a **secret API key**,
3. your **merchant code**,
4. optionally, a **sandbox merchant account** with its own API key and merchant code, for testing,
5. optionally, your **branding**, so the payment page looks like your business.

## 1. Merchant account with online payments

You need a verified SumUp merchant account. Card terminal and online payments are separate
features, and having a card terminal does not mean online payments are enabled.

If online payments are not enabled, creating a checkout fails with HTTP 403 and the error
`checkout_payments_not_allowed`. In pretix, the customer sees "We could not start the payment
with SumUp", and the failed payment in the backend shows the SumUp error. In that case, contact
SumUp support and ask them to enable online payments (the Checkout API / Hosted Checkout) for your
account.

The account's **currency** must be the same as your pretix event's currency. A EUR merchant
account cannot accept GBP checkouts.

## 2. Create an API key

1. Log in to [me.sumup.com](https://me.sumup.com).
2. Open your profile menu and go to **Settings**.
3. Go to **For Developers → Toolkit → API Keys**.
4. Click **Create** and give the key a name that tells you where it is used, for example
   `pretix tickets.example.com`.
5. Copy the key right away. It starts with `sup_sk_`, and SumUp shows it **only once**.

!!! danger "Use the secret key, not the public key"
    The API keys page also lists a **public key** (`sup_pk_…`). That key is for browser widgets
    and **will not work** with this plugin. You need a secret key starting with `sup_sk_`.

!!! tip "One key per installation"
    Create a separate API key for every pretix installation (production, staging, …). Then you can
    revoke one of them without affecting the others.

An API key gives full access to the merchant account. Treat it like a password. pretix stores it
in the event's payment settings and never shows it again in the form.

## 3. Find your merchant code

The merchant code (also called merchant ID) is a short code of upper case letters and digits,
for example `MH4H92C7`. You can find it in the SumUp dashboard:

- in the account menu at the top, below your business name, or
- under **Settings → Business profile** / **Account**.

When you save the payment settings in pretix, the plugin calls the SumUp API with your key and
checks that it belongs to the merchant code you entered.

## 4. Optional: sandbox merchant account

SumUp offers sandbox merchant accounts that never move real money. The plugin uses them for
orders placed while your pretix event is in **test mode**.

1. Open [Developer Settings → Sandboxes](https://me.sumup.com/settings/developer?tab=sandboxes)
   in the SumUp dashboard.
2. Create a sandbox merchant account.
3. Switch to the sandbox account with the account selector at the top of the dashboard. The
   dashboard shows a warning banner while you are in the sandbox.
4. In the sandbox account, create an API key exactly as described above, and note the sandbox
   account's merchant code. It is different from your live merchant code.

!!! note "Testing failed payments"
    In the sandbox, any checkout over an amount of **11** (in any currency, for example 11.00 EUR)
    always fails. Use this to test what your customers see when a payment fails.

## 5. Optional: branding

The Hosted Checkout page shows your business name, logo and icon:

- **Logo and icon**: [Settings → Branding](https://me.sumup.com/settings/branding)
- **Business name and customer-facing details**:
  [Settings → Business profile](https://me.sumup.com/settings/business-profile/information)

## What the plugin sends to SumUp

For reference, a checkout created by the plugin looks like this:

```json
{
  "checkout_reference": "pretix-myevent-ABC12-P1-3f9a1c",
  "amount": 42.0,
  "currency": "EUR",
  "merchant_code": "MH4H92C7",
  "description": "My Event 2026 – ABC12",
  "hosted_checkout": { "enabled": true },
  "return_url": "https://tickets.example.com/org/myevent/sumup/webhook/1234/",
  "redirect_url": "https://tickets.example.com/org/myevent/sumup/return/ABC12/<secret>/1234/"
}
```

- `checkout_reference` shows up in the SumUp dashboard. It is made of the configurable prefix, the
  event slug, the order code, the payment number and a random suffix.
- `return_url` is the **webhook** URL. SumUp calls it whenever the checkout status changes.
- `redirect_url` is where the button on SumUp's success page takes the customer.

Next: [configure the payment method in pretix](configuration.md).
