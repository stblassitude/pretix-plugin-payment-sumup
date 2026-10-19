# Configuration in pretix

## Enable the plugin for your event

1. Open your event in the pretix backend.
2. Go to **Settings → Plugins**, open the **Payment providers** tab and enable
   **SumUp Hosted Checkout**.
3. Go to **Settings → Payment**. A new entry **SumUp Hosted Checkout** appears in the list of
   payment providers. Click **Settings** next to it.

!!! tip "Organizer-wide defaults"
    Like all pretix payment settings, these are per event. If you copy an existing event when you
    create a new one, the SumUp settings (including the API keys) are copied too.

## Settings

| Setting | Description |
| --- | --- |
| **Enable payment method** | Turns SumUp on for this event. pretix refuses to enable it without credentials. |
| **API key** | Your live secret API key (`sup_sk_…`). |
| **Merchant code** | The merchant code of the live account, e.g. `MH4H92C7`. |
| **Sandbox API key** | Optional. Secret API key of a SumUp sandbox account. |
| **Sandbox merchant code** | Optional. Merchant code of the sandbox account. |
| **Checkout reference prefix** | Put in front of every checkout reference that appears in the SumUp dashboard. Default `pretix-`. |
| **Payment method name** | What customers see in the list of payment methods. Default "Credit card, Apple Pay, Google Pay". Can be translated. |

Below these, pretix shows its standard settings for every payment provider: fees, availability
dates, minimum and maximum order totals, restricting the method to some countries or sales
channels, and text for the confirmation email.

When you save, the plugin calls SumUp with each API key you entered and checks that:

- SumUp accepts the key, and
- the key belongs to the merchant code you entered.

If SumUp can't be reached, the settings are saved anyway, without the check.

## Live mode and test mode

pretix events have a **test mode**. The plugin picks the SumUp account from the order:

| Order placed in | SumUp account used | If not configured |
| --- | --- | --- |
| Live mode | API key + merchant code | SumUp is not offered |
| Test mode | Sandbox API key + sandbox merchant code | SumUp is not offered |

The plugin never sends test-mode orders to your live account. If you have no sandbox credentials,
SumUp simply doesn't show up as a payment method while the event is in test mode.

Each payment remembers which account it was created with. Refunds and status checks always use
the account the payment was made with, even if you change the event's mode later.

## Fees

SumUp charges a fee for online payments. To pass it on to customers, use pretix's standard
**Additional fee** fields in the payment provider settings. The fee is added to the order total
before the checkout is created, so SumUp charges the right amount.

## Refunds

Payments made with SumUp can be refunded from the pretix backend, in full or in part:

1. Open the order and click **Refund** (or cancel the order and choose to refund).
2. Pick the SumUp payment as the refund source and enter the amount.
3. pretix calls the SumUp refund API right away. If SumUp accepts the refund, it is marked as done.

If SumUp refuses the refund, pretix shows the SumUp error message and marks the refund as failed.
For example, this happens when the original transaction has not been settled yet, or when the
amount is higher than what is left to refund.

!!! note
    A refund you start in the SumUp dashboard instead of pretix is **not** synced back to pretix.
    In that case, record it in pretix by hand as a manual refund.

## What customers see

1. In the checkout, customers pick the payment method and see a note that they'll be sent to
   SumUp to pay.
2. After confirming the order, they go to the SumUp Hosted Checkout page and pay there.
3. After paying, SumUp shows a success page with a button back to the shop. The button takes
   them to their order page in pretix, where the order shows as paid.
4. If they close the SumUp page before paying, their order page shows a **Continue to payment**
   button for as long as the SumUp page is still valid (30 minutes). After that, they can start a
   new payment from the order page as usual.

## Where to see SumUp details in pretix

Open an order and expand the payment. The plugin shows:

- the SumUp checkout ID and checkout reference,
- the checkout status (`PENDING`, `PAID`, `FAILED`, `EXPIRED`),
- the transaction code. This is the code shown in the SumUp dashboard and on SumUp payout
  reports, and you can use it to match the two systems.
- the payment type,
- a **SumUp sandbox** label if the payment went through the sandbox account.

The REST API exposes the same details in the payment's `details` field, and the transaction code
is used as the payment's matching ID.
