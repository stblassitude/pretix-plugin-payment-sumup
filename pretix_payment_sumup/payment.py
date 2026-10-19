import logging
import secrets
from collections import OrderedDict
from decimal import Decimal

from django import forms
from django.core.validators import RegexValidator
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextInput
from i18nfield.strings import LazyI18nString
from pretix.base.forms import SECRET_REDACTED, SecretKeySettingsField
from pretix.base.models import Order, OrderPayment, OrderRefund, Quota
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.helpers import OF_SELF

try:
    from pretix.multidomain.urlreverse import eventreverse_absolute
except ImportError:  # older pretix releases
    from pretix.multidomain.urlreverse import build_absolute_uri as eventreverse_absolute

from .client import CHECKOUT_EXPIRED, CHECKOUT_FAILED, CHECKOUT_PAID, SUPPORTED_CURRENCIES, SumUpClient, SumUpError

logger = logging.getLogger(__name__)

IDENTIFIER = "sumup_hosted"
SECRET_TAG = "plugins:pretix_payment_sumup"

# Fields from the SumUp checkout object we keep in OrderPayment.info. Everything here is
# non-personal data and safe to retain when personal data is shredded.
CHECKOUT_FIELDS = (
    "id", "checkout_reference", "status", "amount", "currency", "merchant_code", "date",
    "valid_until", "transaction_id", "transaction_code", "hosted_checkout_url",
)
TRANSACTION_FIELDS = (
    "id", "transaction_code", "status", "amount", "currency", "timestamp", "payment_type",
    "entry_mode", "auth_code",
)

merchant_code_validator = RegexValidator(
    r"^[A-Z0-9]{4,20}$",
    _("A SumUp merchant code consists of upper case letters and digits, e.g. MCXXXXXX."),
)


class SumUpHostedCheckout(BasePaymentProvider):
    identifier = IDENTIFIER
    verbose_name = _("SumUp Hosted Checkout")
    abort_pending_allowed = False
    execute_payment_needs_user = True

    # -- presentation ------------------------------------------------------------------------

    @property
    def public_name(self):
        return str(self.settings.get("public_name", as_type=LazyI18nString) or _("Credit card, Apple Pay, Google Pay"))

    @property
    def test_mode_message(self):
        if self._has_credentials(sandbox=True):
            return _(
                "The SumUp sandbox merchant account will be used for orders placed in test mode. "
                "No real money will be transferred."
            )
        return None

    @property
    def settings_form_fields(self):
        fields = [
            ("api_key", SecretKeySettingsField(
                label=_("API key"),
                help_text=_("Secret API key of your SumUp merchant account (starts with sup_sk_). "
                            "Create it in the SumUp dashboard under Settings > For Developers > Toolkit > API keys."),
                required=False,
            )),
            ("merchant_code", forms.CharField(
                label=_("Merchant code"),
                help_text=_("The merchant code (merchant ID) of your SumUp account, e.g. MCXXXXXX."),
                validators=[merchant_code_validator],
                required=False,
            )),
            ("sandbox_api_key", SecretKeySettingsField(
                label=_("Sandbox API key"),
                help_text=_("Optional. API key of a SumUp sandbox merchant account. It is used for orders "
                            "placed while the event is in test mode. Without sandbox credentials, SumUp is not "
                            "offered in test mode."),
                required=False,
            )),
            ("sandbox_merchant_code", forms.CharField(
                label=_("Sandbox merchant code"),
                validators=[merchant_code_validator],
                required=False,
            )),
            ("reference_prefix", forms.CharField(
                label=_("Checkout reference prefix"),
                help_text=_("Prepended to the checkout reference shown in the SumUp dashboard. Use a different "
                            "prefix for every pretix installation that shares a SumUp account."),
                initial="pretix-",
                max_length=16,
                validators=[RegexValidator(r"^[A-Za-z0-9_.-]*$")],
                required=False,
            )),
            ("public_name", I18nFormField(
                label=_("Payment method name"),
                help_text=_("Shown to customers when they choose a payment method."),
                widget=I18nTextInput,
                required=False,
            )),
        ]
        d = OrderedDict(fields + list(super().settings_form_fields.items()))
        d.move_to_end("_enabled", last=False)
        return d

    def settings_form_clean(self, cleaned_data):
        cleaned_data = super().settings_form_clean(cleaned_data)
        for prefix, label in (("", _("live")), ("sandbox_", _("sandbox"))):
            key = cleaned_data.get(f"payment_{self.identifier}_{prefix}api_key")
            code = cleaned_data.get(f"payment_{self.identifier}_{prefix}merchant_code")
            if bool(key) != bool(code):
                raise forms.ValidationError(
                    _("Please enter both the API key and the merchant code for the %(account)s account.")
                    % {"account": label}
                )
            if key == SECRET_REDACTED:
                key = self.settings.get(f"{prefix}api_key")
            if key and code:
                self._verify_credentials(key, code)
        if cleaned_data.get(f"payment_{self.identifier}__enabled") and not (
            cleaned_data.get(f"payment_{self.identifier}_api_key")
            or cleaned_data.get(f"payment_{self.identifier}_sandbox_api_key")
        ):
            raise forms.ValidationError(_("Please enter SumUp credentials before enabling this payment method."))
        return cleaned_data

    def _verify_credentials(self, api_key, merchant_code):
        try:
            profile = SumUpClient(api_key, merchant_code).me()
        except SumUpError as e:
            if e.status_code in (401, 403):
                raise forms.ValidationError(_("SumUp rejected the API key: %(error)s") % {"error": e.message})
            # Network problems or unexpected errors should not prevent saving the settings.
            logger.warning("Could not verify SumUp credentials: %s", e)
            return
        actual = (profile.get("merchant_profile") or {}).get("merchant_code")
        if actual and actual != merchant_code:
            raise forms.ValidationError(
                _("The API key belongs to merchant code %(actual)s, not %(configured)s.")
                % {"actual": actual, "configured": merchant_code}
            )

    def settings_content_render(self, request):
        template = get_template("pretix_payment_sumup/settings.html")
        return template.render({
            "webhook_example": eventreverse_absolute(self.event, "plugins:pretix_payment_sumup:webhook",
                                                     kwargs={"payment": 0}),
            "is_https": eventreverse_absolute(self.event, "presale:event.index").startswith("https://"),
        })

    def payment_form_render(self, request, total, order=None):
        template = get_template("pretix_payment_sumup/checkout_payment_form.html")
        return template.render({"request": request, "event": self.event, "settings": self.settings})

    def checkout_confirm_render(self, request, order=None, info_data=None):
        template = get_template("pretix_payment_sumup/checkout_payment_confirm.html")
        return template.render({"request": request, "event": self.event, "settings": self.settings})

    def payment_pending_render(self, request, payment):
        template = get_template("pretix_payment_sumup/pending.html")
        info = payment.info_data
        return template.render({
            "request": request,
            "event": self.event,
            "payment": payment,
            "checkout_status": info.get("checkout", {}).get("status"),
            "hosted_checkout_url": info.get("checkout", {}).get("hosted_checkout_url"),
            "return_url": self._return_url(payment) if info.get("checkout") else None,
        })

    def payment_control_render(self, request, payment):
        template = get_template("pretix_payment_sumup/control.html")
        info = payment.info_data
        return template.render({
            "request": request,
            "event": self.event,
            "payment": payment,
            "checkout": info.get("checkout", {}),
            "transaction": info.get("transaction", {}),
            "sandbox": info.get("sandbox", False),
            "error": info.get("error"),
        })

    def refund_control_render(self, request, refund):
        template = get_template("pretix_payment_sumup/refund_control.html")
        return template.render({"request": request, "refund": refund, "info": refund.info_data})

    def payment_control_render_short(self, payment):
        return payment.info_data.get("transaction", {}).get("transaction_code") or self.public_name

    def api_payment_details(self, payment):
        info = payment.info_data
        return {
            "checkout_id": info.get("checkout", {}).get("id"),
            "checkout_reference": info.get("checkout", {}).get("checkout_reference"),
            "status": info.get("checkout", {}).get("status"),
            "transaction_id": info.get("transaction", {}).get("id"),
            "transaction_code": info.get("transaction", {}).get("transaction_code"),
            "sandbox": info.get("sandbox", False),
        }

    def matching_id(self, payment):
        return payment.info_data.get("transaction", {}).get("transaction_code")

    def refund_matching_id(self, refund):
        return refund.payment.info_data.get("transaction", {}).get("transaction_code") if refund.payment else None

    def shred_payment_info(self, obj):
        if isinstance(obj, OrderPayment):
            info = obj.info_data
            obj.info_data = {
                "checkout": {k: info.get("checkout", {}).get(k) for k in ("id", "checkout_reference", "status")},
                "transaction": {k: info.get("transaction", {}).get(k) for k in ("id", "transaction_code")},
                "sandbox": info.get("sandbox", False),
                "_shredded": True,
            }
            obj.save(update_fields=["info"])
        else:
            super().shred_payment_info(obj)

    # -- availability ------------------------------------------------------------------------

    def _has_credentials(self, sandbox):
        prefix = "sandbox_" if sandbox else ""
        return bool(self.settings.get(f"{prefix}api_key") and self.settings.get(f"{prefix}merchant_code"))

    def _client(self, sandbox) -> SumUpClient:
        prefix = "sandbox_" if sandbox else ""
        if not self._has_credentials(sandbox):
            raise PaymentException(_("SumUp is not configured correctly. Please contact the event organizer."))
        return SumUpClient(self.settings.get(f"{prefix}api_key"), self.settings.get(f"{prefix}merchant_code"))

    def _available(self, testmode):
        return self.event.currency in SUPPORTED_CURRENCIES and self._has_credentials(sandbox=testmode)

    def is_allowed(self, request: HttpRequest, total: Decimal = None) -> bool:
        return super().is_allowed(request, total) and self._available(self.event.testmode)

    def order_change_allowed(self, order: Order, request: HttpRequest = None) -> bool:
        return super().order_change_allowed(order, request) and self._available(order.testmode)

    # -- checkout flow -----------------------------------------------------------------------

    def checkout_prepare(self, request, cart):
        return True

    def payment_prepare(self, request, payment):
        return True

    def payment_is_valid_session(self, request):
        return True

    def _checkout_reference(self, payment):
        prefix = self.settings.get("reference_prefix", default="pretix-") or ""
        suffix = f"-{payment.order.code}-P{payment.local_id}-{secrets.token_hex(3)}"
        return (prefix + self.event.slug)[:64 - len(suffix)] + suffix

    def _return_url(self, payment):
        return eventreverse_absolute(self.event, "plugins:pretix_payment_sumup:return", kwargs={
            "order": payment.order.code,
            "hash": payment.order.tagged_secret(SECRET_TAG),
            "payment": payment.pk,
        })

    def _webhook_url(self, payment):
        return eventreverse_absolute(self.event, "plugins:pretix_payment_sumup:webhook", kwargs={
            "payment": payment.pk,
        })

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        sandbox = payment.order.testmode
        client = self._client(sandbox)
        description = f"{self.event.name} – {payment.order.code}"[:128]
        try:
            checkout = client.create_checkout(
                amount=payment.amount,
                currency=self.event.currency,
                reference=self._checkout_reference(payment),
                description=description,
                return_url=self._webhook_url(payment),
                redirect_url=self._return_url(payment),
            )
        except SumUpError as e:
            payment.fail(info={"error": e.message, "sandbox": sandbox}, send_mail=False)
            raise PaymentException(
                _("We could not start the payment with SumUp. Please try again or choose another payment method.")
            )

        if not checkout.get("hosted_checkout_url"):
            logger.error("SumUp checkout %s has no hosted_checkout_url: %s", checkout.get("id"), checkout)
            payment.fail(info={"error": "no hosted_checkout_url", "sandbox": sandbox}, send_mail=False)
            raise PaymentException(
                _("Hosted Checkout seems not to be enabled for this SumUp account. Please contact the event organizer.")
            )

        payment.info_data = {
            "checkout": {k: checkout.get(k) for k in CHECKOUT_FIELDS},
            "sandbox": sandbox,
        }
        payment.save(update_fields=["info"])
        return checkout["hosted_checkout_url"]

    def sync_payment(self, payment: OrderPayment, checkout: dict = None):
        """
        Fetch the checkout from SumUp and update the payment state accordingly. This is the only
        place where payments are confirmed or failed, so that redirects, webhooks and polling all
        behave the same. Returns the SumUp checkout status.

        Raises ``SumUpError`` if the SumUp API cannot be reached.
        """
        info = payment.info_data
        checkout_id = info.get("checkout", {}).get("id")
        if not checkout_id:
            return None
        if checkout is None:
            checkout = self._client(info.get("sandbox", False)).get_checkout(checkout_id)
        if checkout.get("id") != checkout_id:
            raise SumUpError("Checkout ID mismatch")

        status = checkout.get("status")
        transactions = checkout.get("transactions") or []
        successful = [t for t in transactions if t.get("status") == "SUCCESSFUL"]
        txn = (successful or transactions or [{}])[-1]

        with transaction.atomic():
            payment = OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=payment.pk)
            info = payment.info_data
            updated = {k: checkout.get(k) for k in CHECKOUT_FIELDS if checkout.get(k) is not None}
            info["checkout"] = {**info.get("checkout", {}), **updated}
            if txn:
                info["transaction"] = {k: txn.get(k) for k in TRANSACTION_FIELDS}
            payment.info_data = info
            payment.save(update_fields=["info"])

        if status == CHECKOUT_PAID and payment.state in (
            OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING,
            OrderPayment.PAYMENT_STATE_FAILED, OrderPayment.PAYMENT_STATE_CANCELED,
        ):
            paid_amount = Decimal(str(checkout.get("amount", "0")))
            if paid_amount != payment.amount or checkout.get("currency") != self.event.currency:
                # Never confirm a payment whose amount differs from what we asked for.
                logger.error("SumUp checkout %s amount %s %s does not match payment %s (%s %s)",
                             checkout_id, paid_amount, checkout.get("currency"), payment.full_id,
                             payment.amount, self.event.currency)
                payment.order.log_action("pretix_payment_sumup.amount_mismatch", data={
                    "checkout_id": checkout_id, "paid": str(paid_amount), "expected": str(payment.amount),
                })
                return status
            try:
                payment.confirm()
            except Quota.QuotaExceededException:
                # pretix has logged this on the order; the organizer needs to decide what to do.
                pass
        elif status == CHECKOUT_FAILED and payment.state in (
            OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING,
        ):
            payment.fail(log_data={"checkout_id": checkout_id, "status": status})
        elif status == CHECKOUT_EXPIRED and payment.state in (
            OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING,
        ):
            # The customer abandoned the Hosted Checkout page, no need to send them an email.
            payment.fail(log_data={"checkout_id": checkout_id, "status": status}, send_mail=False)
        return status

    def cancel_payment(self, payment: OrderPayment):
        checkout_id = payment.info_data.get("checkout", {}).get("id")
        if checkout_id and payment.state in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
            try:
                client = self._client(payment.info_data.get("sandbox", False))
                status = self.sync_payment(payment)
                payment.refresh_from_db()
                if status == CHECKOUT_PAID:
                    raise PaymentException(_("This payment has already been completed at SumUp."))
                if status not in (CHECKOUT_FAILED, CHECKOUT_EXPIRED):
                    client.deactivate_checkout(checkout_id)
            except SumUpError as e:
                logger.warning("Could not deactivate SumUp checkout %s: %s", checkout_id, e)
        if payment.state in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
            super().cancel_payment(payment)

    # -- refunds -----------------------------------------------------------------------------

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return bool(payment.info_data.get("transaction", {}).get("id"))

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return self.payment_refund_supported(payment)

    def execute_refund(self, refund: OrderRefund):
        payment = refund.payment
        transaction_id = payment.info_data.get("transaction", {}).get("id")
        if not transaction_id:
            raise PaymentException(_("No SumUp transaction is known for this payment."))
        client = self._client(payment.info_data.get("sandbox", False))
        try:
            client.refund(transaction_id, refund.amount)
        except SumUpError as e:
            refund.info_data = {"error": e.message, "status_code": e.status_code}
            refund.save(update_fields=["info"])
            raise PaymentException(_("SumUp refused the refund: %(error)s") % {"error": e.message})
        refund.info_data = {"transaction_id": transaction_id, "amount": str(refund.amount)}
        refund.save(update_fields=["info"])
        refund.done()
