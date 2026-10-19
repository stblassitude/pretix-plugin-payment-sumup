from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2025.1 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_payment_sumup"
    verbose_name = "SumUp Hosted Checkout"

    class PretixPluginMeta:
        name = gettext_lazy("SumUp Hosted Checkout")
        author = "Stefan Bethke"
        description = gettext_lazy(
            "Accept card payments, Apple Pay and Google Pay through the SumUp Hosted Checkout page."
        )
        visible = True
        version = __version__
        category = "PAYMENT"
        compatibility = "pretix>=2025.1.0"
        settings_links = [
            (
                (gettext_lazy("Payment"), gettext_lazy("SumUp")),
                "control:event.settings.payment.provider",
                {"provider": "sumup_hosted"},
            ),
        ]
        navigation_links = []

    def ready(self):
        from . import signals  # NOQA
