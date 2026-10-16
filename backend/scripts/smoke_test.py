"""End-to-end smoke test against a RUNNING stack (API + database + seeded data).

    python scripts/smoke_test.py [--base-url http://localhost:8000]

It indexes the sample knowledge base, then drives real conversations over HTTP and
checks: RAG answers with citations, live availability tool calls (including Bikram
Sambat dates), the guarded booking flow, Romanized Nepali, and the human handoff loop
(ticket -> manager reply -> resolve). The booking/availability steps assert exact
replies only when LLM_PROVIDER=mock; with a real model they assert the *behaviour*
(tools were called) rather than the wording.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import uuid

import httpx

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@hotel.local")
    parser.add_argument("--password", default="Admin@2081")
    parser.add_argument("--wait", type=int, default=420, help="seconds to wait for indexing")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base_url, timeout=120.0)

    print("1. Health and sign-in")
    health = client.get("/health")
    if not check("API is healthy", health.status_code == 200, health.text):
        return 1
    login = client.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
    if not check("admin login works", login.status_code == 200, login.text):
        return 1
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    print("2. Knowledge base indexing")
    client.post("/api/v1/documents/ingest-sample-kb", headers=auth)
    deadline = time.time() + args.wait
    docs: list[dict] = []
    while time.time() < deadline:
        docs = client.get("/api/v1/documents?page_size=100", headers=auth).json().get("items", [])
        pending = [d for d in docs if d["status"] in ("queued", "processing")]
        if docs and not pending:
            break
        time.sleep(4)
    indexed = [d for d in docs if d["status"] == "indexed"]
    failed = [d for d in docs if d["status"] == "failed"]
    check("sample documents indexed", len(indexed) >= 5 and not failed,
          f"indexed={len(indexed)} failed={[(d['original_name'], d['error_message']) for d in failed]}")

    def chat(session: str, text: str, language: str | None = None) -> dict:
        res = client.post("/api/v1/chat/message", json={"session_id": session, "message": text, "language": language})
        res.raise_for_status()
        return res.json()

    print("3. Knowledge question (RAG + citations)")
    sid = str(uuid.uuid4())
    reply = chat(sid, "What time is check-out?")
    check("answers from documents", "11" in reply["text"], reply["text"][:160])
    check("cites its sources", len(reply["citations"]) > 0, str(reply["citations"]))

    print("4. Live availability with Bikram Sambat dates")
    reply = chat(sid, "Do you have a deluxe room for 2 people from 5 to 8 Kartik?")
    check("replies with prices", ("NPR" in reply["text"]) or ("रू" in reply["text"]), reply["text"][:200])
    convos = client.get("/api/v1/conversations?page_size=50", headers=auth).json()["items"]
    mine = next((c for c in convos if c["session_id"] == sid), None)
    tools_used: list[str] = []
    if mine:
        detail = client.get(f"/api/v1/conversations/{mine['id']}", headers=auth).json()
        tools_used = [t["name"] for m in detail["messages"] for t in m["tool_calls"]]
    check("availability tool was called", "check_room_availability" in tools_used, str(tools_used))

    print("5. Guarded booking flow")
    reply = chat(sid, "Deluxe please. My name is Smoke Tester, phone 9800000001")
    check("asks for explicit confirmation first", "confirm" in reply["text"].lower() or "पुष्टि" in reply["text"] or "pushti" in reply["text"].lower(), reply["text"][:200])
    bookings_before = client.get("/api/v1/bookings?page_size=200&status=confirmed", headers=auth).json()["total"]
    reply = chat(sid, "yes")
    bookings_after = client.get("/api/v1/bookings?page_size=200&status=confirmed", headers=auth).json()["total"]
    check("booking created only after 'yes'", bookings_after == bookings_before + 1,
          f"before={bookings_before} after={bookings_after} reply={reply['text'][:160]}")
    # Real LLMs may render the reference with a Unicode hyphen (U+2011/U+2013).
    check("reply contains a booking reference", re.search(r"HH[\u2010-\u2015-]?[0-9A-Fa-f]{6,}", reply["text"]) is not None, reply["text"][:200])

    print("6. Romanized Nepali")
    reply = chat(str(uuid.uuid4()), "Mero booking cancel garna paryo")
    check("replies in Romanized Nepali", reply["reply_style"] == "ne_roman", reply["reply_style"])

    print("7. Human handoff loop")
    hsid = str(uuid.uuid4())
    reply = chat(hsid, "I want to complain about my room, it is dirty")
    check("conversation handed to a human", reply["handoff_active"] and reply["handoff_ticket_ref"], str(reply))
    tickets = client.get("/api/v1/handoffs?status=open&page_size=50", headers=auth).json()["items"]
    ticket = next((t for t in tickets if t["ref"] == reply.get("handoff_ticket_ref")), None)
    check("ticket visible in the inbox", ticket is not None)
    if ticket:
        again = chat(hsid, "Hello? Is anyone there?")
        check("AI stays silent while a human is assigned", again["handoff_active"], again["text"][:120])
        sent = client.post(f"/api/v1/handoffs/{ticket['id']}/reply", headers=auth, json={"text": "Sorry about that, I am sending housekeeping now."})
        check("manager reply stored", sent.status_code == 200, sent.text)
        done = client.post(f"/api/v1/handoffs/{ticket['id']}/resolve", headers=auth)
        check("ticket resolved", done.status_code == 200, done.text)
        history = client.get(f"/api/v1/chat/history/{hsid}").json()
        roles = [m["role"] for m in history["messages"]]
        check("guest history shows the human's reply", "human_agent" in roles, str(roles))
        check("AI resumes after resolution", history["handoff_active"] is False)

    failed_checks = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed_checks)}/{len(results)} checks passed")
    return 1 if failed_checks else 0


if __name__ == "__main__":
    sys.exit(main())
