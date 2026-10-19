# Sandbox image: the official pretix image plus this plugin, installed in editable mode so that
# the source mounted by docker-compose.yml is used directly.
ARG PRETIX_VERSION=stable
FROM pretix/standalone:${PRETIX_VERSION}

USER root
COPY pyproject.toml setup.py README.md LICENSE MANIFEST.in /plugin-src/
COPY pretix_payment_sumup /plugin-src/pretix_payment_sumup
RUN pip3 install --no-cache-dir -e /plugin-src
COPY sandbox/entrypoint.sh /usr/local/bin/sandbox-entrypoint
RUN chmod 755 /usr/local/bin/sandbox-entrypoint
USER pretixuser

ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint"]
CMD ["all"]
