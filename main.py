import os
from contextlib import asynccontextmanager
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

load_dotenv()

DAILY_LIMIT = Decimal(os.environ.get("DAILY_LIMIT", "35"))
MIN_BALANCE = Decimal(os.environ.get("MIN_BALANCE", "1"))
DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
create table if not exists ai_credit_usage (
  owner_id text not null,
  day date not null,
  used numeric(12,4) not null default 0,
  primary key (owner_id, day)
);
create table if not exists ai_credit_txn (
  request_id text primary key,
  owner_id text not null,
  cost numeric(12,4) not null,
  created_at timestamptz not null default now()
);
"""
TODAY = "(now() at time zone 'Asia/Bangkok')::date"

def conn():
    return psycopg.connect(DATABASE_URL, autocommit=False)


@asynccontextmanager
async def lifespan(_):
    with conn() as c:
        c.execute(SCHEMA)
    yield


app = FastAPI(lifespan=lifespan)


def status(used: Decimal):
    remaining = DAILY_LIMIT - used
    return {"limit": DAILY_LIMIT, "used": used, "remaining": remaining, "allowed": remaining >= MIN_BALANCE}


def used_today(c, owner_id: str) -> Decimal:
    row = c.execute(f"select used from ai_credit_usage where owner_id=%s and day={TODAY}", (owner_id,)).fetchone()
    return row[0] if row else Decimal(0)


@app.get("/credit/{owner_id}")
def get_credit(owner_id: str):
    with conn() as c:
        return {"owner_id": owner_id, **status(used_today(c, owner_id))}


class Deduct(BaseModel):
    request_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    cost: Decimal = Field(ge=0)


@app.post("/credit/deduct")
def deduct(body: Deduct):
    with conn() as c:
        inserted = c.execute(
            "insert into ai_credit_txn (request_id, owner_id, cost) values (%s,%s,%s) on conflict do nothing",
            (body.request_id, body.owner_id, body.cost),
        ).rowcount
        if inserted:
            c.execute(
                f"""insert into ai_credit_usage (owner_id, day, used) values (%s, {TODAY}, %s)
                    on conflict (owner_id, day) do update set used = ai_credit_usage.used + excluded.used""",
                (body.owner_id, body.cost),
            )
        return {"owner_id": body.owner_id, "duplicate": not inserted, **status(used_today(c, body.owner_id))}
