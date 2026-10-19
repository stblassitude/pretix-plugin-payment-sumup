import json
import logging

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pretix.base.models import Order, OrderPayment
from pretix.base.payment import PaymentException
from pretix.multidomain.urlreverse import eventreverse

from .client import CHECKOUT_EXPIRED, CHECKOUT_FAILED, CHECKOUT_PAID, SumUpError
from .payment import IDENTIFIER, SECRET_TAG

logger = logging.getLogger(__name__)


@method_decorator(xframe_options_exempt, "dispatch")
class ReturnView(View):
    """
    The customer is sent here from the SumUp Hosted Checkout page (``redirect_url``). Reaching
    this URL proves nothing, so we always ask the SumUp API for the checkout status.
    """

    def get(self, request, *args, **kwargs):
        try:
            order = request.event.orders.get_with_secret_check(
                code=kwargs["order"], received_secret=kwargs["hash"].lower(), tag=SECRET_TAG,
            )
        except Order.DoesNotExist:
            raise Http404("Unknown order")
        payment = get_object_or_404(order.payments, pk=kwargs["payment"], provider=IDENTIFIER)

        try:
            status = payment.payment_provider.sync_payment(payment)
        except (SumUpError, PaymentException) as e:
            logger.warning("Could not fetch SumUp checkout for payment %s: %s", payment.full_id, e)
            messages.error(request, _("We could not check the status of your payment with SumUp. If you paid, "
                                      "your order will be updated automatically within a few minutes."))
            status = None

        order.refresh_from_db()
        if status == CHECKOUT_FAILED:
            messages.error(request, _("Your payment was not successful. Please try again or choose another "
                                      "payment method."))
        elif status == CHECKOUT_EXPIRED:
            messages.error(request, _("Your payment session at SumUp has expired. Please start the payment again."))
        elif status and status != CHECKOUT_PAID:
            messages.info(request, _("Your payment has not been completed yet. If you already paid, your order "
                                     "will be updated automatically within a few minutes."))

        url = eventreverse(request.event, "presale:event.order", kwargs={
            "order": order.code,
            "secret": order.secret,
        })
        return redirect(url + ("?paid=yes" if order.status == Order.STATUS_PAID else ""))


@csrf_exempt
@require_POST
def webhook(request, *args, **kwargs):
    """
    SumUp posts ``{"event_type": "CHECKOUT_STATUS_CHANGED", "id": "<checkout id>"}`` to the
    ``return_url`` of a checkout. The request is not signed, so we never trust its content and
    fetch the checkout from the API instead. Any non-2xx answer makes SumUp retry the delivery.
    """
    try:
        event_json = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    if not isinstance(event_json, dict):
        return HttpResponse(status=400)

    if event_json.get("event_type") != "CHECKOUT_STATUS_CHANGED":
        # SumUp may introduce new event types without notice, ignore those.
        return HttpResponse(status=204)

    try:
        payment = OrderPayment.objects.select_related("order").get(
            pk=kwargs["payment"], order__event=request.event, provider=IDENTIFIER,
        )
    except OrderPayment.DoesNotExist:
        logger.info("SumUp webhook for unknown payment %s", kwargs["payment"])
        return HttpResponse(status=204)

    if event_json.get("id") != payment.info_data.get("checkout", {}).get("id"):
        logger.warning("SumUp webhook for payment %s references unexpected checkout %s",
                       payment.full_id, event_json.get("id"))
        return HttpResponse(status=204)

    try:
        payment.payment_provider.sync_payment(payment)
    except (SumUpError, PaymentException) as e:
        logger.warning("Could not process SumUp webhook for payment %s: %s", payment.full_id, e)
        return HttpResponse(status=503)
    return HttpResponse(status=204)
