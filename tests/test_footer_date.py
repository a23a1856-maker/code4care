"""The footer bar carries today's date, in Malay, in Malaysia time."""
from __future__ import annotations

from datetime import datetime, timezone

from app.ui import malaysia_today, today_label
from tests.conftest import sign_in


def test_date_label_uses_malay_day_and_month_names():
    moment = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)

    assert today_label(moment) == "Jumaat, 23 Oktober 2026"


def test_a_naive_moment_is_read_as_utc():
    assert today_label(datetime(2026, 3, 2, 4, 0)) == "Isnin, 2 Mac 2026"


def test_the_day_is_malaysia_time_not_server_time():
    # 17:30 UTC on 31 December is already 01:30 on 1 January in Malaysia.
    late = datetime(2026, 12, 31, 17, 30, tzinfo=timezone.utc)

    assert today_label(late) == "Jumaat, 1 Januari 2027"


def test_every_page_footer_shows_todays_date(client):
    page = client.get("/login")

    assert page.status_code == 200
    assert 'class="footer-date"' in page.text
    assert f"Tarikh hari ini: {today_label()}</time>" in page.text
    assert f'<time datetime="{malaysia_today().date().isoformat()}">' in page.text


def test_signed_in_footer_still_shows_the_date(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])

    page = client.get("/")

    assert page.status_code == 200
    assert "Tarikh hari ini: " in page.text
