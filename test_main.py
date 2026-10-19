import uuid

from fastapi.testclient import TestClient

from main import DAILY_LIMIT, app


def test_flow():
    owner = f"test-{uuid.uuid4().hex}"
    with TestClient(app) as cl:
        assert cl.get(f"/credit/{owner}").json()["remaining"] == DAILY_LIMIT

        spend = DAILY_LIMIT - 5
        r = cl.post("/credit/deduct", json={"request_id": f"{owner}-1", "owner_id": owner, "cost": str(spend)}).json()
        assert r["remaining"] == 5 and r["allowed"]

        dup = cl.post("/credit/deduct", json={"request_id": f"{owner}-1", "owner_id": owner, "cost": str(spend)}).json()
        assert dup["duplicate"] and dup["remaining"] == 5

        r = cl.post("/credit/deduct", json={"request_id": f"{owner}-2", "owner_id": owner, "cost": "4.5"}).json()
        assert r["remaining"] == 0.5 and not r["allowed"]  # < 1 baht blocked
