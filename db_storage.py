"""
Postgres-backed storage (Supabase). Same function names/shapes as the old
storage.py (local JSON files) so app.py doesn't need to change once we cut
over — this file is being prepared ahead of getting the real connection
string, not wired in yet.
"""
import os
import re
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    slug TEXT PRIMARY KEY,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS history (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL REFERENCES properties(slug) ON DELETE CASCADE,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS known_comps JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS known_feedback JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Per-agent isolation: which agent's properties these are, so one agent
-- never lists/loads another's. Existing rows (pre-dating this column)
-- default to 'unassigned' rather than silently vanishing from anyone's
-- list — an empty-string default would make them invisible to everyone.
ALTER TABLE properties ADD COLUMN IF NOT EXISTS agent_slug TEXT NOT NULL DEFAULT 'unassigned';
CREATE INDEX IF NOT EXISTS idx_properties_agent_slug ON properties(agent_slug);
"""


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "unknown"


def property_slug(agent_slug: str, address: str) -> str:
    """The property's storage key, namespaced by agent — this is the whole
    isolation mechanism: two agents working the same address never collide,
    and an agent's own properties are found by filtering/prefixing on their
    own agent_slug. Not real per-user authentication (anyone who knows
    another agent's slug could still construct their key), just practical
    separation for a small group of known, trusted agents sharing one
    passcode-gated app — the same trust level the app already assumes."""
    return f"{agent_slug or 'unassigned'}--{slugify(address)}"


@contextmanager
def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set. Check the .env file.")
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


def init_schema():
    with _connect() as conn:
        conn.execute(SCHEMA)


def list_properties(agent_slug: str):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT slug, profile FROM properties WHERE agent_slug = %s ORDER BY created_at DESC", (agent_slug,)
        ).fetchall()
    return [(row[0], row[1]) for row in rows]


def load_profile(slug: str):
    with _connect() as conn:
        row = conn.execute("SELECT profile FROM properties WHERE slug = %s", (slug,)).fetchone()
    return row[0] if row else None


def save_profile(slug: str, profile: dict, agent_slug: str):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO properties (slug, profile, agent_slug) VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET profile = EXCLUDED.profile
            """,
            (slug, Jsonb(profile), agent_slug),
        )


def load_history(slug: str):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT snapshot FROM history WHERE slug = %s ORDER BY created_at ASC", (slug,)
        ).fetchall()
    return [row[0] for row in rows]


def save_snapshot(slug: str, snapshot: dict):
    with _connect() as conn:
        conn.execute("INSERT INTO history (slug, snapshot) VALUES (%s, %s)", (slug, Jsonb(snapshot)))


def delete_property(slug: str):
    with _connect() as conn:
        conn.execute("DELETE FROM properties WHERE slug = %s", (slug,))


def load_known_comps(slug: str) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT known_comps FROM properties WHERE slug = %s", (slug,)).fetchone()
    return row[0] if row and row[0] else {}


def save_known_comps(slug: str, known_comps: dict):
    with _connect() as conn:
        conn.execute("UPDATE properties SET known_comps = %s WHERE slug = %s", (Jsonb(known_comps), slug))


def load_known_feedback(slug: str) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT known_feedback FROM properties WHERE slug = %s", (slug,)).fetchone()
    return row[0] if row and row[0] else {}


def save_known_feedback(slug: str, known_feedback: dict):
    with _connect() as conn:
        conn.execute("UPDATE properties SET known_feedback = %s WHERE slug = %s", (Jsonb(known_feedback), slug))
