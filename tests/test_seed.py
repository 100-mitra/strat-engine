"""The seed_demo management command creates a runnable demo and is idempotent."""

from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_runnable_demo():
    call_command("seed_demo", stdout=StringIO())

    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token

    from apps.strategies.models import Strategy

    user = User.objects.get(username="demo")
    assert Token.objects.filter(user=user).exists()
    assert Strategy.objects.filter(owner=user).count() == 1


def test_seed_demo_is_idempotent():
    call_command("seed_demo", stdout=StringIO())
    call_command("seed_demo", stdout=StringIO())

    from django.contrib.auth.models import User

    from apps.strategies.models import Strategy

    user = User.objects.get(username="demo")
    assert User.objects.filter(username="demo").count() == 1
    assert Strategy.objects.filter(owner=user).count() == 1
