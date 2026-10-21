"""Run with: python -m unittest discover tests"""
import os
import tempfile
import unittest
from collections import Counter

from app import create_app, policy


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(database_path=os.path.join(self.tmp.name, "test.db"), api_key="")
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def consent(self, pid="p1", consented=True):
        return self.client.post("/consent", json={
            "participant_id": pid, "consented": consented, "consent_version": "v1.0",
            "occurred_at": "2026-10-21T09:00:00-04:00",
        })

    def opportunity(self, pid="p1", **kw):
        body = {"participant_id": pid, "context": {"steps_last_hour": 120, "location": "home"}, **kw}
        return self.client.post("/opportunity", json=body)

    # --- consent ---
    def test_consent_saved(self):
        r = self.consent()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json["consented"])
        self.assertIn("consent_id", r.json)

    def test_consent_validation(self):
        r = self.client.post("/consent", json={"participant_id": "p1"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/consent", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    # --- opportunity ---
    def test_opportunity_requires_consent(self):
        self.assertEqual(self.opportunity().status_code, 403)

    def test_withdrawn_consent_blocks(self):
        self.consent(consented=True)
        self.consent(consented=False)
        self.assertEqual(self.opportunity().status_code, 403)

    def test_opportunity_returns_arm_and_probability(self):
        self.consent()
        r = self.opportunity(occurred_at="2026-10-21T10:00:00Z")
        self.assertEqual(r.status_code, 201)
        self.assertIn(r.json["arm"], policy.ARMS)
        self.assertEqual(r.json["probability"], policy.ARMS[r.json["arm"]])
        self.assertTrue(r.json["available"])

    def test_unavailable_gets_control_with_prob_1(self):
        self.consent()
        r = self.opportunity(available=False)
        self.assertEqual(r.json["arm"], policy.CONTROL_ARM)
        self.assertEqual(r.json["probability"], 1.0)

    def test_retry_with_client_decision_id_is_idempotent(self):
        self.consent()
        first = self.opportunity(client_decision_id="abc")
        second = self.opportunity(client_decision_id="abc")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json["decision_id"], second.json["decision_id"])
        self.assertEqual(first.json["arm"], second.json["arm"])

    def test_randomization_is_roughly_balanced(self):
        self.consent()
        arms = Counter(self.opportunity().json["arm"] for _ in range(400))
        for arm in policy.ARMS:
            self.assertGreater(arms[arm], 120, arms)

    # --- reward ---
    def test_reward_for_every_arm(self):
        self.consent()
        seen = set()
        for _ in range(50):
            d = self.opportunity().json
            r = self.client.post("/reward", json={"decision_id": d["decision_id"], "reward": 0.0})
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.json["arm"], d["arm"])
            seen.add(d["arm"])
        self.assertEqual(seen, set(policy.ARMS))

    def test_reward_unknown_decision(self):
        r = self.client.post("/reward", json={"decision_id": "nope", "reward": 1})
        self.assertEqual(r.status_code, 404)

    def test_duplicate_reward_rejected(self):
        self.consent()
        d = self.opportunity().json
        self.client.post("/reward", json={"decision_id": d["decision_id"], "reward": 1})
        r = self.client.post("/reward", json={"decision_id": d["decision_id"], "reward": 2})
        self.assertEqual(r.status_code, 409)

    def test_reward_rejects_nan(self):
        self.consent()
        d = self.opportunity().json
        r = self.client.post("/reward", data='{"decision_id": "%s", "reward": NaN}' % d["decision_id"],
                             content_type="application/json")
        self.assertEqual(r.status_code, 422)

    # --- auth ---
    def test_api_key(self):
        app = create_app(database_path=os.path.join(self.tmp.name, "auth.db"), api_key="secret")
        c = app.test_client()
        self.assertEqual(c.get("/health").status_code, 200)
        body = {"participant_id": "p1", "consented": True, "consent_version": "v1"}
        self.assertEqual(c.post("/consent", json=body).status_code, 401)
        self.assertEqual(c.post("/consent", json=body, headers={"X-API-Key": "wrong"}).status_code, 401)
        self.assertEqual(c.post("/consent", json=body, headers={"X-API-Key": "secret"}).status_code, 201)


if __name__ == "__main__":
    unittest.main()
