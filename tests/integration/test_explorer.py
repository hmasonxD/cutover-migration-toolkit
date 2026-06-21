"""Integration tests for the explorer surface: exception persistence, the
migrated/exceptions list endpoints, and the before/after compare endpoint.

These cover the API + pipeline code added for the dashboard, so the same green
suite that proves the migration also proves the tooling around it.
"""
from __future__ import annotations

from cutover import db


def test_exceptions_persisted_to_table(migrated):
    """The 5 injected property defects should be written to migration_exception."""
    with db.cloud_conn() as conn:
        n = db.query_value(conn, "SELECT count(*) FROM app.migration_exception WHERE entity = 'PROPERTY'")
    assert n == 5


def test_exceptions_endpoint_returns_logged_rows(migrated, api_client):
    data = api_client.get("/exceptions").json()
    assert data["total"] >= 5
    reasons = " | ".join(e["reason"] for e in data["items"])
    assert "roll number" in reasons
    assert "money" in reasons
    assert "status" in reasons
    assert "date" in reasons
    assert "owner" in reasons


def test_exceptions_carry_source_id_and_raw_roll(migrated, api_client):
    items = api_client.get("/exceptions").json()["items"]
    bad_money = next(e for e in items if "money" in e["reason"])
    assert bad_money["source_id"] is not None
    assert bad_money["roll_no_raw"] == "002000000"


def test_list_properties_paginates(migrated, api_client):
    data = api_client.get("/properties?limit=10&offset=0").json()
    assert data["total"] == 120
    assert len(data["items"]) == 10
    assert data["items"][0]["roll_number"] < data["items"][1]["roll_number"]


def test_list_properties_search_filters(migrated, api_client):
    # find a known owner from the first page, then search for it
    first = api_client.get("/properties?limit=1").json()["items"][0]
    owner = first["owner_name"].split()[0]
    data = api_client.get(f"/properties?search={owner}").json()
    assert data["total"] >= 1
    assert all(owner.lower() in p["owner_name"].lower() or owner in p["roll_number"]
               for p in data["items"])


def test_list_properties_serializes_money_as_string(migrated, api_client):
    item = api_client.get("/properties?limit=1").json()["items"][0]
    assert isinstance(item["assessed_value"], str)
    assert isinstance(item["tax_levy"], str)


def test_compare_clean_record_shows_before_and_after(migrated, api_client):
    data = api_client.get("/compare/1").json()
    assert data["before"]["roll_no"] is not None
    assert data["after"] is not None
    assert data["error"] is None
    # cleansing actually happened: raw owner reorders/cases, status expands
    assert data["after"]["status"] in ("ACTIVE", "INACTIVE", "PENDING", "EXEMPT")


def test_compare_defect_record_shows_error_and_null_after(migrated, api_client):
    # rec 123 is the injected bad-money row
    data = api_client.get("/compare/123").json()
    assert data["before"]["assessed_val"] == "N/A"
    assert data["after"] is None
    assert "money" in data["error"]


def test_compare_missing_record_returns_404(migrated, api_client):
    resp = api_client.get("/compare/999999")
    assert resp.status_code == 404