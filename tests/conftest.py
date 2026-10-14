import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dodge_satelite.cli import demo_inputs
from dodge_satelite.predict import plan


@pytest.fixture
def inputs():
    return demo_inputs()


@pytest.fixture(scope="session")
def demo_result():
    return plan(*demo_inputs())
