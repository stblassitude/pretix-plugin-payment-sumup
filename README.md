# pretix SumUp Hosted Checkout

A [pretix](https://pretix.eu) payment provider plugin that lets customers pay through
[SumUp Hosted Checkout](https://developer.sumup.com/online-payments/checkouts/hosted-checkout):
card, Apple Pay and Google Pay on a payment page hosted by SumUp.

- Payments are confirmed through the return redirect, SumUp webhooks **and** the pretix cronjob,
  so customers who close the browser after paying are covered too.
- Full and partial refunds from the pretix backend.
- Separate SumUp sandbox account for orders placed in pretix test mode.

**Documentation:** <https://stblassitude.github.io/pretix-plugin-payment-sumup/>

## Installation

```bash
pip install pretix-payment-sumup
```

Note: the PyPI package `pretix-sumup` is a different project.

Then enable **SumUp Hosted Checkout** in your event's plugin settings and enter your SumUp API key
and merchant code under **Settings → Payment**. See the documentation for the
[SumUp account setup](https://stblassitude.github.io/pretix-plugin-payment-sumup/sumup-setup/)
and [notes and gotchas](https://stblassitude.github.io/pretix-plugin-payment-sumup/gotchas/).

## Trying it out

```bash
cd sandbox
cp .env.example .env
docker compose up --build -d
# http://localhost:8345/control/  admin@localhost / admin
```

See [Docker sandbox](https://stblassitude.github.io/pretix-plugin-payment-sumup/sandbox/).

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pretix -e '.[dev]'
pytest
```

## License

MIT License, see [LICENSE](LICENSE).
