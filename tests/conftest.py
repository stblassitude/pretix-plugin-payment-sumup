import datetime
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pretix.base.models import Event, Order, OrderPayment, Organizer

CHECKOUT_ID = "4e425463-3e1b-431d-83fa-1e51c2925e99"
TRANSACTION_ID = "410fc44a-5956-44e1-b5cc-19c6f8d727a4"


@pytest.fixture
@scopes_disabled()
def event():
    o = Organizer.objects.create(name="Dummy", slug="dummy")
    event = Event.objects.create(
        organizer=o, name="Dummy", slug="dummy", currency="EUR",
        date_from=now() + datetime.timedelta(days=10), live=True,
        plugins="pretix_payment_sumup",
    )
    event.settings.set("payment_sumup_hosted__enabled", True)
    event.settings.set("payment_sumup_hosted_api_key", "sup_sk_live")
    event.settings.set("payment_sumup_hosted_merchant_code", "MCLIVE01")
    event.settings.set("payment_sumup_hosted_sandbox_api_key", "sup_sk_sandbox")
    event.settings.set("payment_sumup_hosted_sandbox_merchant_code", "MCSANDB1")
    return event


@pytest.fixture
@scopes_disabled()
def order(event):
    return Order.objects.create(
        code="FOOBAR", event=event, email="dummy@dummy.test", status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + datetime.timedelta(days=10), total=Decimal("23.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )


@pytest.fixture
@scopes_disabled()
def payment(order):
    return order.payments.create(
        provider="sumup_hosted", amount=order.total, state=OrderPayment.PAYMENT_STATE_CREATED,
    )


def checkout_response(status="PENDING", amount=23.0, transactions=None, **kwargs):
    d = {
        "id": CHECKOUT_ID,
        "checkout_reference": "pretix-dummy-FOOBAR-P1-abcdef",
        "amount": amount,
        "currency": "EUR",
        "merchant_code": "MCLIVE01",
        "description": "Dummy – FOOBAR",
        "status": status,
        "date": "2026-10-19T10:00:00.000+00:00",
        "hosted_checkout_url": "https://checkout.sumup.com/pay/8f9316a3-cda9-42e9-9771-54d534315676",
        "transactions": transactions or [],
    }
    d.update(kwargs)
    return d


def paid_checkout(amount=23.0):
    return checkout_response(status="PAID", amount=amount, transaction_id=TRANSACTION_ID,
                             transaction_code="TEENSK4W2K", transactions=[{
                                 "id": TRANSACTION_ID, "transaction_code": "TEENSK4W2K", "amount": amount,
                                 "currency": "EUR", "status": "SUCCESSFUL", "payment_type": "ECOM",
                                 "timestamp": "2026-10-19T10:01:00.000+00:00",
                             }])
