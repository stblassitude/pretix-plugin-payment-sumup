# Installation

The plugin is published on PyPI as
[`pretix-payment-sumup`](https://pypi.org/project/pretix-payment-sumup/).

!!! warning "Not `pretix-sumup`"
    The PyPI package `pretix-sumup` is a different, unrelated project. Make sure you install
    **`pretix-payment-sumup`**. This plugin uses the module name `pretix_payment_sumup` and the
    payment provider identifier `sumup_hosted`.

## Requirements

- pretix 2025.1 or newer (tested with 2025.1 and 2026.8)
- Python 3.11 or newer
- The pretix cronjob must run (`pretix cron` / `python -m pretix runperiodic`). The plugin uses it
  to pick up payments whose webhook got lost.
- For webhooks: your pretix must be reachable from the internet over HTTPS. Without that, payments
  are still confirmed through the return redirect and the cronjob, just later.

## Docker installation (`pretix/standalone`)

If you run the official Docker image, as described in the
[pretix Docker installation guide](https://docs.pretix.eu/self-hosting/installation/docker_smallscale/),
build your own image on top of it:

```dockerfile title="Dockerfile"
FROM pretix/standalone:stable
USER root
RUN pip3 install pretix-payment-sumup
USER pretixuser
RUN cd /pretix/src && make production
```

Build the image and restart pretix with it:

```bash
docker build . -t mypretix
# change your systemd unit / compose file to use "mypretix" instead of "pretix/standalone"
systemctl restart pretix
```

If you use docker compose, put the Dockerfile next to your `docker-compose.yml` and replace
`image: pretix/standalone:stable` with `build: .`.

## Manual installation (virtualenv)

If you followed the
[manual installation guide](https://docs.pretix.eu/self-hosting/installation/manual_smallscale/),
install the plugin into the same virtualenv as pretix and rebuild the assets:

```bash
sudo -u pretix -s
source /var/pretix/venv/bin/activate
pip3 install pretix-payment-sumup
python -m pretix migrate
python -m pretix rebuild
exit
sudo systemctl restart pretix-web pretix-worker
```

The plugin has no database migrations of its own, but running `migrate` after installing a
plugin is a good habit.

## Upgrading

Upgrade like any other pretix plugin: rebuild your Docker image, or run
`pip3 install -U pretix-payment-sumup` in the virtualenv, and then restart pretix.

## Check the cronjob

Many pretix features rely on the cronjob, and this plugin does too. With Docker, the pretix
documentation recommends a host cron entry like this:

```cron
15,45 * * * * /usr/bin/docker exec pretix.service pretix cron
```

The plugin checks open SumUp payments every time the cronjob runs. SumUp payment pages expire
after 30 minutes, so running the cronjob more often than twice an hour makes "lost webhook" cases
resolve faster. Every 5 minutes is a good value:

```cron
*/5 * * * * /usr/bin/docker exec pretix.service pretix cron
```

## Enable the plugin

After installing, the plugin is available to all organizers on your pretix instance. Enable it
per event: go to **Event → Settings → Plugins → Payment providers** and enable
**SumUp Hosted Checkout**. Then continue with the [SumUp account setup](sumup-setup.md).
