import json
from decimal import Decimal

import pytest
import responses
from django.test import RequestFactory
from django_scopes import scopes_disabled
from pretix.base.models import Order, OrderPayment, OrderRefund
from pretix.base.payment import PaymentException

from pretix_payment_sumup.client import API_BASE, SumUpClient, SumUpError
from pretix_payment_sumup.payment import SECRET_TAG, SumUpHostedCheckout
from pretix_payment_sumup.signals import poll_open_checkouts

from .conftest import CHECKOUT_ID, TRANSACTION_ID, checkout_response, paid_checkout

CHECKOUT_URL = f"{API_BASE}/v0.1/checkouts/{CHECKOUT_ID}"


def started(payment, sandbox=False):
    payment.info_data = {"checkout": checkout_response(), "sandbox": sandbox}
    payment.save()
    return payment


@responses.activate
def test_client_error_message_from_list():
    responses.post(f"{API_BASE}/v0.1/checkouts", status=409, json=[
        {"error_code": "DUPLICATED_CHECKOUT", "message": "Checkout with this checkout reference already exists"}
    ])
    with pytest.raises(SumUpError) as e:
        SumUpClient("k", "MC").create_checkout(amount=Decimal("1.00"), currency="EUR", reference="r",
                                               description="d")
    assert e.value.status_code == 409
    assert "already exists" in e.value.message


@responses.activate
def test_client_sends_hosted_checkout_payload():
    responses.post(f"{API_BASE}/v0.1/checkouts", json=checkout_response())
    SumUpClient("sup_sk_x", "MCLIVE01").create_checkout(
        amount=Decimal("23.50"), currency="EUR", reference="ref", description="desc",
        return_url="https://example.com/hook", redirect_url="https://example.com/back",
    )
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer sup_sk_x"
    body = json.loads(req.body)
    assert body == {
        "checkout_reference": "ref", "amount": 23.5, "currency": "EUR", "merchant_code": "MCLIVE01",
        "description": "desc", "hosted_checkout": {"enabled": True},
        "return_url": "https://example.com/hook", "redirect_url": "https://example.com/back",
    }


@pytest.mark.django_db
@responses.activate
def test_execute_payment_redirects_to_hosted_checkout(event, payment):
    responses.post(f"{API_BASE}/v0.1/checkouts", json=checkout_response())
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        url = prov.execute_payment(RequestFactory().get("/"), payment)
    assert url.startswith("https://checkout.sumup.com/pay/")
    body = json.loads(responses.calls[0].request.body)
    assert body["merchant_code"] == "MCLIVE01"
    assert body["amount"] == 23.0
    assert body["checkout_reference"].startswith("pretix-dummy-FOOBAR-P1-")
    assert len(body["checkout_reference"]) <= 64
    assert f"/sumup/webhook/{payment.pk}/" in body["return_url"]
    assert "/sumup/return/FOOBAR/" in body["redirect_url"]
    payment.refresh_from_db()
    assert payment.info_data["checkout"]["id"] == CHECKOUT_ID
    assert payment.info_data["sandbox"] is False


@pytest.mark.django_db
@responses.activate
def test_execute_payment_uses_sandbox_in_testmode(event, order, payment):
    order.testmode = True
    order.save()
    responses.post(f"{API_BASE}/v0.1/checkouts", json=checkout_response(merchant_code="MCSANDB1"))
    with scopes_disabled():
        SumUpHostedCheckout(event).execute_payment(RequestFactory().get("/"), payment)
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer sup_sk_sandbox"
    assert json.loads(req.body)["merchant_code"] == "MCSANDB1"
    payment.refresh_from_db()
    assert payment.info_data["sandbox"] is True


@pytest.mark.django_db
@responses.activate
def test_execute_payment_api_error_fails_payment(event, payment):
    responses.post(f"{API_BASE}/v0.1/checkouts", status=401, json={"error_code": "NOT_AUTHORIZED"})
    with scopes_disabled():
        with pytest.raises(PaymentException):
            SumUpHostedCheckout(event).execute_payment(RequestFactory().get("/"), payment)
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_FAILED


@pytest.mark.django_db
def test_not_available_in_testmode_without_sandbox_credentials(event):
    event.settings.set("payment_sumup_hosted_sandbox_api_key", "")
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        assert prov._available(testmode=False)
        assert not prov._available(testmode=True)


@pytest.mark.django_db
def test_not_available_for_unsupported_currency(event):
    event.currency = "JPY"
    event.save()
    with scopes_disabled():
        assert not SumUpHostedCheckout(event)._available(testmode=False)


@pytest.mark.django_db
@responses.activate
def test_return_view_confirms_paid_checkout(client, event, order, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=paid_checkout())
    secret = order.tagged_secret(SECRET_TAG)
    r = client.get(f"/dummy/dummy/sumup/return/{order.code}/{secret}/{payment.pk}/")
    assert r.status_code == 302
    assert "paid=yes" in r["Location"]
    with scopes_disabled():
        payment.refresh_from_db()
        order.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert order.status == Order.STATUS_PAID
    assert payment.info_data["transaction"]["id"] == TRANSACTION_ID


@pytest.mark.django_db
@responses.activate
def test_return_view_rejects_wrong_secret(client, event, order, payment):
    started(payment)
    r = client.get(f"/dummy/dummy/sumup/return/{order.code}/{'0' * 64}/{payment.pk}/")
    assert r.status_code == 404
    assert len(responses.calls) == 0


@pytest.mark.django_db
@responses.activate
def test_return_view_pending_keeps_payment_open(client, event, order, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=checkout_response())
    secret = order.tagged_secret(SECRET_TAG)
    r = client.get(f"/dummy/dummy/sumup/return/{order.code}/{secret}/{payment.pk}/")
    assert r.status_code == 302
    with scopes_disabled():
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CREATED


@pytest.mark.django_db
@responses.activate
def test_webhook_confirms_payment(client, event, order, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=paid_checkout())
    r = client.post(f"/dummy/dummy/sumup/webhook/{payment.pk}/",
                    json.dumps({"event_type": "CHECKOUT_STATUS_CHANGED", "id": CHECKOUT_ID}),
                    content_type="application/json")
    assert r.status_code == 204
    assert r.content == b""
    with scopes_disabled():
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
@responses.activate
def test_webhook_works_for_event_that_is_not_live(client, event, order, payment):
    event.live = False
    event.save()
    started(payment)
    responses.get(CHECKOUT_URL, json=paid_checkout())
    r = client.post(f"/dummy/dummy/sumup/webhook/{payment.pk}/",
                    json.dumps({"event_type": "CHECKOUT_STATUS_CHANGED", "id": CHECKOUT_ID}),
                    content_type="application/json")
    assert r.status_code == 204
    with scopes_disabled():
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
@responses.activate
def test_webhook_ignores_foreign_checkout_id(client, event, order, payment):
    started(payment)
    r = client.post(f"/dummy/dummy/sumup/webhook/{payment.pk}/",
                    json.dumps({"event_type": "CHECKOUT_STATUS_CHANGED", "id": "something-else"}),
                    content_type="application/json")
    assert r.status_code == 204
    assert len(responses.calls) == 0
    with scopes_disabled():
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CREATED


@pytest.mark.django_db
@responses.activate
def test_webhook_ignores_unknown_events(client, event, payment):
    started(payment)
    r = client.post(f"/dummy/dummy/sumup/webhook/{payment.pk}/",
                    json.dumps({"event_type": "SOMETHING_NEW", "id": CHECKOUT_ID}),
                    content_type="application/json")
    assert r.status_code == 204
    assert len(responses.calls) == 0


@pytest.mark.django_db
@responses.activate
def test_webhook_requests_retry_when_sumup_unreachable(client, event, payment):
    started(payment)
    responses.get(CHECKOUT_URL, status=502, body="Bad gateway")
    r = client.post(f"/dummy/dummy/sumup/webhook/{payment.pk}/",
                    json.dumps({"event_type": "CHECKOUT_STATUS_CHANGED", "id": CHECKOUT_ID}),
                    content_type="application/json")
    assert r.status_code == 503


@pytest.mark.django_db
@responses.activate
def test_amount_mismatch_is_not_confirmed(event, order, payment):
    started(payment)
    with scopes_disabled():
        SumUpHostedCheckout(event).sync_payment(payment, paid_checkout(amount=1.0))
        payment.refresh_from_db()
        assert payment.state == OrderPayment.PAYMENT_STATE_CREATED
        assert order.all_logentries().filter(action_type="pretix_payment_sumup.amount_mismatch").exists()


@pytest.mark.django_db
@responses.activate
def test_sync_failed_and_expired(event, order):
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        for status in ("FAILED", "EXPIRED"):
            p = started(order.payments.create(provider="sumup_hosted", amount=order.total,
                                              state=OrderPayment.PAYMENT_STATE_CREATED))
            prov.sync_payment(p, checkout_response(status=status))
            p.refresh_from_db()
            assert p.state == OrderPayment.PAYMENT_STATE_FAILED


@pytest.mark.django_db
@responses.activate
def test_periodic_task_polls_open_payments(event, order, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=paid_checkout())
    poll_open_checkouts(sender=None)
    with scopes_disabled():
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
@responses.activate
def test_cancel_deactivates_checkout(event, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=checkout_response())
    responses.delete(CHECKOUT_URL, json=checkout_response(status="EXPIRED"))
    with scopes_disabled():
        SumUpHostedCheckout(event).cancel_payment(payment)
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CANCELED
    assert responses.calls[-1].request.method == "DELETE"


@pytest.mark.django_db
@responses.activate
def test_cancel_refused_when_already_paid(event, payment):
    started(payment)
    responses.get(CHECKOUT_URL, json=paid_checkout())
    with scopes_disabled():
        with pytest.raises(PaymentException):
            SumUpHostedCheckout(event).cancel_payment(payment)
        payment.refresh_from_db()
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED


@pytest.mark.django_db
@responses.activate
def test_partial_refund(event, order, payment):
    started(payment)
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        prov.sync_payment(payment, paid_checkout())
        payment.refresh_from_db()
        assert prov.payment_partial_refund_supported(payment)
        responses.post(f"{API_BASE}/v0.1/me/refund/{TRANSACTION_ID}", status=204)
        refund = order.refunds.create(payment=payment, provider="sumup_hosted", amount=Decimal("5.00"),
                                      source=OrderRefund.REFUND_SOURCE_ADMIN, state=OrderRefund.REFUND_STATE_CREATED)
        prov.execute_refund(refund)
        refund.refresh_from_db()
    assert refund.state == OrderRefund.REFUND_STATE_DONE
    assert json.loads(responses.calls[-1].request.body) == {"amount": 5.0}


@pytest.mark.django_db
@responses.activate
def test_refund_error(event, order, payment):
    started(payment)
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        prov.sync_payment(payment, paid_checkout())
        payment.refresh_from_db()
        responses.post(f"{API_BASE}/v0.1/me/refund/{TRANSACTION_ID}", status=409,
                       json={"detail": "The transaction is not refundable in its current state"})
        refund = order.refunds.create(payment=payment, provider="sumup_hosted", amount=Decimal("5.00"),
                                      source=OrderRefund.REFUND_SOURCE_ADMIN, state=OrderRefund.REFUND_STATE_CREATED)
        with pytest.raises(PaymentException) as e:
            prov.execute_refund(refund)
    assert "not refundable" in str(e.value)


@pytest.mark.django_db
@responses.activate
def test_settings_validation_rejects_wrong_merchant_code(event):
    from django import forms
    responses.get(f"{API_BASE}/v0.1/me", json={"merchant_profile": {"merchant_code": "MCOTHER1"}})
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        with pytest.raises(forms.ValidationError):
            prov.settings_form_clean({
                "payment_sumup_hosted__enabled": True,
                "payment_sumup_hosted_api_key": "sup_sk_new",
                "payment_sumup_hosted_merchant_code": "MCLIVE01",
            })


@pytest.mark.django_db
@responses.activate
def test_settings_validation_uses_stored_key_when_redacted(event):
    responses.get(f"{API_BASE}/v0.1/me", json={"merchant_profile": {"merchant_code": "MCLIVE01"}})
    with scopes_disabled():
        SumUpHostedCheckout(event).settings_form_clean({
            "payment_sumup_hosted__enabled": True,
            "payment_sumup_hosted_api_key": "*****",
            "payment_sumup_hosted_merchant_code": "MCLIVE01",
        })
    assert responses.calls[0].request.headers["Authorization"] == "Bearer sup_sk_live"


@pytest.mark.django_db
def test_templates_render(event, payment):
    started(payment, sandbox=True)
    request = RequestFactory().get("/")
    with scopes_disabled():
        prov = SumUpHostedCheckout(event)
        pending = prov.payment_pending_render(request, payment)
        assert "https://checkout.sumup.com/pay/" in pending
        assert "/sumup/return/FOOBAR/" in pending
        control = prov.payment_control_render(request, payment)
        assert CHECKOUT_ID in control
        assert "sandbox" in control
        assert "/sumup/webhook/" in prov.settings_content_render(request)
        assert "SumUp" in prov.payment_form_render(request, Decimal("23.00"))
        assert "SumUp" in prov.checkout_confirm_render(request)
