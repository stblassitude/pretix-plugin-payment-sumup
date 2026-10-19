"""
Minimal client for the parts of the SumUp REST API used by this plugin.

API reference: https://developer.sumup.com/api
"""
import logging
from decimal import Decimal

import requests

from . import __version__

logger = logging.getLogger(__name__)

API_BASE = "https://api.sumup.com"
TIMEOUT = 15

CHECKOUT_PENDING = "PENDING"
CHECKOUT_PAID = "PAID"
CHECKOUT_FAILED = "FAILED"
CHECKOUT_EXPIRED = "EXPIRED"

# Currencies SumUp accepts for online checkouts. The checkout currency must also match the
# currency of the merchant account, which SumUp enforces on its side.
SUPPORTED_CURRENCIES = {
    "BRL", "CHF", "CLP", "COP", "CZK", "DKK", "EUR", "GBP", "HUF", "NOK", "PLN", "RON", "SEK", "USD",
}


class SumUpError(Exception):
    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body


def _error_message(body, fallback):
    # SumUp returns errors either as an object or as a list of objects, depending on the endpoint.
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        for key in ("message", "detail", "title", "error_message", "error_code"):
            if body.get(key):
                return str(body[key])
    return fallback


class SumUpClient:
    def __init__(self, api_key: str, merchant_code: str, base_url: str = API_BASE, timeout: int = TIMEOUT):
        self.api_key = api_key
        self.merchant_code = merchant_code
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        url = self.base_url + path
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": f"pretix-payment-sumup/{__version__}",
        }
        try:
            r = requests.request(method, url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            logger.warning("SumUp request %s %s failed: %s", method, path, e)
            raise SumUpError(f"Could not connect to SumUp: {e}")

        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {"raw": r.text[:1000]}

        if r.status_code >= 400:
            message = _error_message(body, f"HTTP {r.status_code}")
            logger.warning("SumUp request %s %s returned %s: %s", method, path, r.status_code, body)
            raise SumUpError(message, status_code=r.status_code, body=body)
        return body

    def create_checkout(self, *, amount: Decimal, currency: str, reference: str, description: str,
                        return_url: str = None, redirect_url: str = None) -> dict:
        payload = {
            "checkout_reference": reference,
            "amount": float(amount),
            "currency": currency,
            "merchant_code": self.merchant_code,
            "description": description,
            "hosted_checkout": {"enabled": True},
        }
        if return_url:
            payload["return_url"] = return_url
        if redirect_url:
            payload["redirect_url"] = redirect_url
        return self._request("POST", "/v0.1/checkouts", payload)

    def get_checkout(self, checkout_id: str) -> dict:
        return self._request("GET", f"/v0.1/checkouts/{checkout_id}")

    def deactivate_checkout(self, checkout_id: str) -> dict:
        return self._request("DELETE", f"/v0.1/checkouts/{checkout_id}")

    def refund(self, transaction_id: str, amount: Decimal = None) -> dict:
        payload = {"amount": float(amount)} if amount is not None else None
        return self._request("POST", f"/v0.1/me/refund/{transaction_id}", payload)

    def me(self) -> dict:
        return self._request("GET", "/v0.1/me")
