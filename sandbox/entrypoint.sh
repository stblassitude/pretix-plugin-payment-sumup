#!/bin/bash
# Compile the plugin's translations from the mounted source, then hand over to pretix.
set -e
for po in /plugin-src/pretix_payment_sumup/locale/*/LC_MESSAGES/*.po; do
    [ -e "$po" ] && msgfmt -o "${po%.po}.mo" "$po" 2>/dev/null || true
done
exec /usr/local/bin/pretix "$@"
