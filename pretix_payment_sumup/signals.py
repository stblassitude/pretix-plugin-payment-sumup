import logging
from datetime import timedelta

from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled
from pretix.base.models import OrderPayment
from pretix.base.payment import PaymentException
from pretix.base.signals import logentry_display, periodic_task, register_payment_providers

from .client import SumUpError
from .payment import IDENTIFIER

logger = logging.getLogger(__name__)

# Hosted Checkout sessions are valid for 30 minutes. We keep polling a bit longer than that so a
# payment completed at the last second (or a short SumUp outage) is still picked up.
POLL_WINDOW = timedelta(hours=24)


@receiver(register_payment_providers, dispatch_uid="payment_sumup_hosted")
def register_payment_provider(sender, **kwargs):
    from .payment import SumUpHostedCheckout
    return SumUpHostedCheckout


@receiver(periodic_task, dispatch_uid="payment_sumup_hosted_poll")
@scopes_disabled()
def poll_open_checkouts(sender, **kwargs):
    """
    Safety net for lost webhooks and customers who never return from SumUp: ask SumUp for the
    status of every recent payment that is still open.
    """
    payments = OrderPayment.objects.filter(
        provider=IDENTIFIER,
        state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
        created__gte=now() - POLL_WINDOW,
    ).select_related("order", "order__event")
    for payment in list(payments):
        if not payment.info_data.get("checkout", {}).get("id"):
            continue
        try:
            payment.payment_provider.sync_payment(payment)
        except (SumUpError, PaymentException) as e:
            logger.warning("Could not poll SumUp checkout for payment %s: %s", payment.full_id, e)


@receiver(signal=logentry_display, dispatch_uid="payment_sumup_hosted_logentry_display")
def logentry_display_sumup(sender, logentry, **kwargs):
    if logentry.action_type == "pretix_payment_sumup.amount_mismatch":
        data = logentry.parsed_data
        return _("SumUp reported a paid amount of %(paid)s, but %(expected)s was expected. The payment "
                 "was not confirmed automatically.") % {"paid": data.get("paid"), "expected": data.get("expected")}
