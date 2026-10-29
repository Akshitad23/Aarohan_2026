"""Shared Groq organization budget. Reservations are atomic across server workers."""

import math
import os
import time
import uuid

from logger_db import connect, transaction

SCOPE = "groq"


def limits():
    return {
        "rpm": max(1, int(os.getenv("GROQ_RPM_LIMIT", "30"))),
        "tpm": max(1, int(os.getenv("GROQ_TPM_LIMIT", "8000"))),
        "rpd": max(1, int(os.getenv("GROQ_RPD_LIMIT", "1000"))),
        "tpd": max(1, int(os.getenv("GROQ_TPD_LIMIT", "200000"))),
        "max_concurrent": max(1, int(os.getenv("GROQ_MAX_CONCURRENT", "4"))),
        "team_interval_seconds": max(0, int(os.getenv("GROQ_TEAM_MIN_INTERVAL", "60"))),
    }


def _rows(conn, now):
    return conn.execute("SELECT * FROM provider_reservations WHERE scope=? AND started_at>? ORDER BY started_at", (SCOPE, now - 86400)).fetchall()


def _usage(rows, now):
    minute = [row for row in rows if row["started_at"] > now - 60]
    return {"rpm": len(minute), "tpm": sum(row["tokens"] for row in minute),
            "rpd": len(rows), "tpd": sum(row["tokens"] for row in rows),
            "active": sum(row["active_until"] > now for row in rows)}


def _summary(rows, now, cooldown=0):
    configured = limits()
    used = _usage(rows, now)
    return {"scope": SCOPE, "limits": configured, "used": used,
            "remaining": {key: max(0, configured[key] - used[key]) for key in ("rpm", "tpm", "rpd", "tpd")},
            "cooldown_seconds": max(0, math.ceil(cooldown - now)), "estimated_tokens": True}


def snapshot():
    now = time.time()
    with connect() as conn:
        state = conn.execute("SELECT cooldown_until FROM provider_budget_state WHERE scope=?", (SCOPE,)).fetchone()
        return _summary(_rows(conn, now), now, state["cooldown_until"] if state else 0)


def reserve(tokens, team_id="", lease_seconds=90):
    """Reserve request and token capacity, or return an immediate fallback reason.

    Counters use rolling minute/day windows, including in-flight reservations.
    A worker crash retains its conservative token reservation and expires its
    concurrency lease; restarting or replacing an API key does not reset usage.
    """
    now = time.time()
    tokens = max(1, int(tokens))
    configured = limits()
    with transaction() as conn:
        conn.execute("INSERT INTO provider_budget_state(scope,cooldown_until) VALUES(?,0) ON CONFLICT(scope) DO NOTHING", (SCOPE,))
        conn.execute("DELETE FROM provider_reservations WHERE scope=? AND started_at<=? AND active_until<=?", (SCOPE, now - 86400, now))
        state = conn.execute("SELECT cooldown_until FROM provider_budget_state WHERE scope=?", (SCOPE,)).fetchone()
        rows = _rows(conn, now)
        used = _usage(rows, now)
        conn.execute("DELETE FROM provider_waiters WHERE scope=? AND expires_at<=?", (SCOPE, now))
        if team_id:
            conn.execute("INSERT INTO provider_waiters(scope,team_id,waiting_since,expires_at) VALUES(?,?,?,?) ON CONFLICT(scope,team_id) DO UPDATE SET expires_at=excluded.expires_at", (SCOPE, str(team_id), now, now + 30))

        def denied(reason, retry_after):
            if team_id and (reason.startswith("budget_") or reason == "org_cooldown"):
                conn.execute("UPDATE provider_waiters SET expires_at=? WHERE scope=? AND team_id=?", (now + max(30, retry_after + 15), SCOPE, str(team_id)))
            return {"allowed": False, "reason": reason, "retry_after_seconds": max(1, math.ceil(retry_after)),
                    "budget": _summary(rows, now, state["cooldown_until"])}

        if state["cooldown_until"] > now:
            return denied("org_cooldown", state["cooldown_until"] - now)
        if team_id and configured["team_interval_seconds"]:
            recent = [row for row in rows if row["team_id"] == str(team_id)]
            if recent and recent[-1]["started_at"] + configured["team_interval_seconds"] > now:
                return denied("team_pacing", recent[-1]["started_at"] + configured["team_interval_seconds"] - now)
        if used["active"] >= configured["max_concurrent"]:
            return denied("concurrency", min(row["active_until"] for row in rows if row["active_until"] > now) - now)
        for key, window, cost in (("rpm", 60, 1), ("tpm", 60, tokens), ("rpd", 86400, 1), ("tpd", 86400, tokens)):
            if used[key] + cost <= configured[key]:
                continue
            relevant = [row for row in rows if row["started_at"] > now - window]
            needed = used[key] + cost - configured[key]
            reclaimed = 0
            retry = window
            for row in relevant:
                reclaimed += 1 if key in ("rpm", "rpd") else row["tokens"]
                if reclaimed >= needed:
                    retry = row["started_at"] + window - now
                    break
            return denied("budget_" + key, retry)
        if team_id:
            waiters = conn.execute("SELECT * FROM provider_waiters WHERE scope=? ORDER BY waiting_since", (SCOPE,)).fetchall()
            counts, last = {}, {}
            for row in rows:
                counts[row["team_id"]] = counts.get(row["team_id"], 0) + 1
                last[row["team_id"]] = row["started_at"]
            eligible = [waiter for waiter in waiters if last.get(waiter["team_id"], 0) + configured["team_interval_seconds"] <= now]
            if eligible:
                first = min(eligible, key=lambda waiter: (counts.get(waiter["team_id"], 0), last.get(waiter["team_id"], 0), waiter["waiting_since"], waiter["team_id"]))
                if first["team_id"] != str(team_id):
                    return denied("fair_turn", min(10, first["expires_at"] - now))
        reservation = uuid.uuid4().hex
        conn.execute("INSERT INTO provider_reservations(id,scope,started_at,tokens,team_id,active_until) VALUES(?,?,?,?,?,?)",
                     (reservation, SCOPE, now, tokens, str(team_id), now + max(30, lease_seconds)))
        if team_id:
            conn.execute("DELETE FROM provider_waiters WHERE scope=? AND team_id=?", (SCOPE, str(team_id)))
        return {"allowed": True, "reservation_id": reservation}


def complete(reservation_id, actual_tokens=None):
    """Reconcile provider-reported total usage, including reasoning tokens."""
    with transaction() as conn:
        if isinstance(actual_tokens, int) and not isinstance(actual_tokens, bool) and actual_tokens >= 0:
            conn.execute("UPDATE provider_reservations SET tokens=?,active_until=0 WHERE id=? AND scope=?", (actual_tokens, reservation_id, SCOPE))
        else:
            conn.execute("UPDATE provider_reservations SET active_until=0 WHERE id=? AND scope=?", (reservation_id, SCOPE))


def cooldown(seconds):
    """Honor a provider 429 across all workers and restarts."""
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        seconds = 60
    until = time.time() + seconds
    with transaction() as conn:
        conn.execute("INSERT INTO provider_budget_state(scope,cooldown_until) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET cooldown_until=CASE WHEN provider_budget_state.cooldown_until>excluded.cooldown_until THEN provider_budget_state.cooldown_until ELSE excluded.cooldown_until END", (SCOPE, until))
