# Development and releases

## Local development

```bash
git clone https://github.com/stblassitude/pretix-plugin-payment-sumup.git
cd pretix-plugin-payment-sumup
python3 -m venv .venv
. .venv/bin/activate
pip install pretix -e '.[dev]'
```

Run the tests and linters:

```bash
pytest
flake8 pretix_payment_sumup tests
isort -c pretix_payment_sumup tests
```

The tests use pretix' own test settings (an SQLite database) and mock the SumUp API with
[`responses`](https://github.com/getsentry/responses). They don't need network access or SumUp
credentials. To test against SumUp for real, use the [Docker sandbox](sandbox.md).

## Code layout

| File | Purpose |
| --- | --- |
| `pretix_payment_sumup/client.py` | Small wrapper around the SumUp REST API |
| `pretix_payment_sumup/payment.py` | The pretix payment provider: settings, checkout creation, status sync, refunds |
| `pretix_payment_sumup/views.py` | Return URL (customer) and webhook (SumUp) |
| `pretix_payment_sumup/signals.py` | Provider registration and the periodic poller |
| `pretix_payment_sumup/templates/` | Customer- and backend-facing HTML snippets |
| `pretix_payment_sumup/locale/` | Translations |

All three status sources (return, webhook, cron) call `SumUpHostedCheckout.sync_payment()`. That
method is the only place where payments are confirmed or failed.

## Translations

Update the message catalog after changing translatable strings:

```bash
cd pretix_payment_sumup
DJANGO_SETTINGS_MODULE=pretix.testutils.settings django-admin makemessages -l de --no-location
```

Translate the new entries in `locale/de/LC_MESSAGES/django.po`. The `.mo` files are not committed.
They are compiled automatically during the package build (`setup.py`, needs GNU gettext's
`msgfmt`) and when the sandbox container starts.

## Documentation

The documentation is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/):

```bash
pip install -e '.[docs]'
mkdocs serve
```

The `docs` workflow publishes it to GitHub Pages on every push to `main`. Enable it once under
**Repository → Settings → Pages → Source: GitHub Actions**.

## Releasing

Releases are made by pushing a version tag. The `release` GitHub Actions workflow then:

1. runs the tests (the same jobs as `ci`),
2. takes the version from the tag (`v1.2.3` → `1.2.3`). The tag must be a normalized
   [PEP 440](https://peps.python.org/pep-0440/) version, so `v1.2.3`, `v1.3.0rc1` or `v2.0.0b2`,
3. writes that version into `pyproject.toml` and builds the sdist and wheel, including the compiled
   translations,
4. uploads both to PyPI with [trusted publishing](https://docs.pypi.org/trusted-publishers/), so
   no API token is stored in GitHub,
5. creates a GitHub release for the tag. The release notes list the summaries of all commits since
   the previous `v*` tag, and the built files are attached. Tags with `a`, `b`, `rc` or `dev`
   versions are marked as pre-releases.

!!! note "Version number"
    The version in `pyproject.toml` is always the placeholder `0.0.0.dev0`, and there is no
    version number anywhere else in the source tree. Don't change it by hand; the git tag is the
    only source of the version. At runtime the plugin reads its version from the installed package
    metadata, so pretix shows the released version.

### One-time setup

1. On PyPI, go to **Your account → Publishing → Add a new pending publisher** (or, once the
   project exists, **Project → Settings → Publishing**) and enter:

    | Field | Value |
    | --- | --- |
    | PyPI project name | `pretix-payment-sumup` |
    | Owner | `stblassitude` |
    | Repository name | `pretix-plugin-payment-sumup` |
    | Workflow name | `release.yml` |
    | Environment name | `pypi` |

2. In GitHub, create an environment named **`pypi`** under **Repository → Settings →
   Environments**. Add required reviewers if you want to approve every upload by hand. You can also
   restrict the environment to tags matching `v*`.

### Making a release

Write commit messages with a meaningful first line, because those summaries become the release
notes. Then tag the commit you want to release and push the tag:

```bash
git tag v1.0.1
git push origin v1.0.1
```

If the workflow fails before uploading to PyPI (for example because a test fails), fix the
problem, then delete and recreate the tag:

```bash
git tag -d v1.0.1 && git push origin :refs/tags/v1.0.1
git tag v1.0.1 && git push origin v1.0.1
```

Once a version is on PyPI it can't be uploaded again. In that case, release a new version.
