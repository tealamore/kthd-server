"""JITAI backend: consent, intervention opportunities, rewards."""
import json
import os
import sqlite3
import uuid

from flask import Flask, jsonify, request
from pydantic import ValidationError

from . import policy
from .db import close_db, get_db, init_db, iso, now_utc, to_json
from .schemas import ConsentIn, OpportunityIn, RewardIn


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = database_path or os.environ.get("DATABASE_PATH", "data/jitai.db")

    init_db(app.config["DATABASE_PATH"])
    app.teardown_appcontext(close_db)

    # ---------- helpers ----------

    def error(status: int, message: str, **extra):
        return jsonify({"error": message, **extra}), status

    def parse(model):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return None, error(400, "Request body must be a JSON object")
        try:
            return model.model_validate(body), None
        except ValidationError as e:
            return None, error(422, "Invalid request body", details=json.loads(e.json(include_url=False)))

    def ensure_participant(db, participant_id: str):
        db.execute(
            "INSERT OR IGNORE INTO participants (participant_id, created_at) VALUES (?, ?)",
            (participant_id, now_utc()),
        )

    def has_consented(db, participant_id: str) -> bool:
        row = db.execute(
            "SELECT consented FROM consents WHERE participant_id = ? ORDER BY rowid DESC LIMIT 1",
            (participant_id,),
        ).fetchone()
        return bool(row and row["consented"])

    def decision_payload(row) -> dict:
        return {
            "decision_id": row["decision_id"],
            "participant_id": row["participant_id"],
            "arm": row["arm"],
            "probability": row["probability"],
            "available": bool(row["available"]),
            "policy_version": row["policy_version"],
            "received_at": row["received_at"],
        }

    @app.before_request
    def check_device_id():
        if request.path == "/health":
            return None
        device_id = request.headers.get("X-Device-ID", "").strip()
        if not device_id or len(device_id) > 128:
            return error(400, "Missing or invalid X-Device-ID header")
        return None

    # ---------- endpoints ----------

    @app.get("/health")
    def health():
        get_db().execute("SELECT 1").fetchone()
        return jsonify({"status": "ok"})

    @app.post("/consent")
    def post_consent():
        body, err = parse(ConsentIn)
        if err:
            return err
        db = get_db()
        consent_id = str(uuid.uuid4())
        received_at = now_utc()
        ensure_participant(db, body.participant_id)
        db.execute(
            """INSERT INTO consents
               (consent_id, participant_id, consented, consent_version, occurred_at, received_at, extra)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (consent_id, body.participant_id, int(body.consented), body.consent_version,
             iso(body.occurred_at), received_at, to_json(body.extra)),
        )
        db.commit()
        return jsonify({
            "consent_id": consent_id,
            "participant_id": body.participant_id,
            "consented": body.consented,
            "consent_version": body.consent_version,
            "received_at": received_at,
        }), 201

    @app.post("/opportunity")
    def post_opportunity():
        body, err = parse(OpportunityIn)
        if err:
            return err
        db = get_db()

        if not has_consented(db, body.participant_id):
            return error(403, "Participant has not consented (or has withdrawn)")

        # Retry from the app with the same client_decision_id -> same answer, no new randomization.
        if body.client_decision_id:
            existing = db.execute(
                "SELECT * FROM decisions WHERE participant_id = ? AND client_decision_id = ?",
                (body.participant_id, body.client_decision_id),
            ).fetchone()
            if existing:
                return jsonify(decision_payload(existing)), 200

        arm, probability = policy.choose_arm(body.participant_id, body.context, body.available)
        decision_id = str(uuid.uuid4())
        try:
            db.execute(
                """INSERT INTO decisions
                   (decision_id, participant_id, client_decision_id, occurred_at, received_at,
                    context, available, arm, probability, policy_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, body.participant_id, body.client_decision_id, iso(body.occurred_at),
                 now_utc(), json.dumps(body.context), int(body.available), arm, probability,
                 policy.POLICY_VERSION),
            )
            db.commit()
        except sqlite3.IntegrityError:
            # Two identical retries raced each other; return the one that won.
            db.rollback()
            existing = db.execute(
                "SELECT * FROM decisions WHERE participant_id = ? AND client_decision_id = ?",
                (body.participant_id, body.client_decision_id),
            ).fetchone()
            if existing:
                return jsonify(decision_payload(existing)), 200
            raise

        row = db.execute("SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
        return jsonify(decision_payload(row)), 201

    @app.post("/reward")
    def post_reward():
        body, err = parse(RewardIn)
        if err:
            return err
        db = get_db()

        decision = db.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (body.decision_id,)
        ).fetchone()
        if decision is None:
            return error(404, "Unknown decision_id")

        received_at = now_utc()
        try:
            db.execute(
                """INSERT INTO rewards (decision_id, reward, occurred_at, received_at, extra)
                   VALUES (?, ?, ?, ?, ?)""",
                (body.decision_id, body.reward, iso(body.occurred_at), received_at, to_json(body.extra)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return error(409, "A reward was already recorded for this decision")

        policy.update(decision["participant_id"], json.loads(decision["context"]),
                      decision["arm"], decision["probability"], body.reward)

        return jsonify({
            "decision_id": body.decision_id,
            "arm": decision["arm"],
            "reward": body.reward,
            "received_at": received_at,
        }), 201

    return app
