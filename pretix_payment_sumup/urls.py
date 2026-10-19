from django.urls import include, re_path
from pretix.multidomain import event_url

from .views import ReturnView, webhook

event_patterns = [
    re_path(r"^sumup/", include([
        # Both URLs must work for events that are not live yet, since SumUp calls the webhook and
        # customers return from SumUp regardless of the event's shop status.
        event_url(r"^return/(?P<order>[^/]+)/(?P<hash>[A-Za-z0-9]+)/(?P<payment>[0-9]+)/$",
                  ReturnView.as_view(), name="return", require_live=False),
        event_url(r"^webhook/(?P<payment>[0-9]+)/$", webhook, name="webhook", require_live=False),
    ])),
]
