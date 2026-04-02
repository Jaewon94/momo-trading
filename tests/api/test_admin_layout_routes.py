import pytest


@pytest.mark.asyncio
async def test_admin_page_exposes_three_pane_layout_shell(client):
    response = await client.get("/admin")

    assert response.status_code == 200
    html = response.text
    assert 'id="admin-left-pane"' in html
    assert 'id="admin-center-pane"' in html
    assert 'id="admin-right-pane"' in html
    assert 'id="pane-resizer-left"' in html
    assert 'id="pane-resizer-right"' in html
    assert 'id="portfolio-quick-stats"' in html
    assert 'id="today-trades-info"' in html
    assert 'id="badge-broker"' in html
    assert 'id="badge-market"' in html
    assert 'id="header-trigger-cycle"' in html
    assert 'id="header-trading-on"' in html
    assert 'id="header-trading-off"' in html
    assert 'id="header-mode-semi"' in html
    assert 'id="header-mode-auto"' in html
    assert 'id="header-scheduler-start"' in html
    assert 'id="header-scheduler-stop"' in html
    assert '<script type="module" src="/admin/static/js/app.js"></script>' in html
