"""
Compile gettext catalogs while building, so that wheels ship ready-to-use .mo files.
All other metadata lives in pyproject.toml.
"""
import shutil
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithTranslations(build_py):
    def run(self):
        msgfmt = shutil.which("msgfmt")
        catalogs = list(Path("pretix_payment_sumup", "locale").glob("*/LC_MESSAGES/*.po"))
        if catalogs and not msgfmt:
            raise RuntimeError("msgfmt (GNU gettext) is required to build pretix-payment-sumup")
        for po in catalogs:
            subprocess.check_call([msgfmt, "--check", "-o", str(po.with_suffix(".mo")), str(po)])
        super().run()


setup(cmdclass={"build_py": BuildWithTranslations})
