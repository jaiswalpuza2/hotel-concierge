# Product Requirements Document (PRD)
## Autonomous Multi-Agent Local Business Concierge
### Demo Instance: Himalayan Heritage Hotel

**Version:** 1.0.0  
**Date:** 2026-10-12  
**Status:** Draft – Awaiting Approval

---

## 1. Vision

Build an AI-powered digital concierge that any regional Nepali business can deploy by swapping a configuration file — not rewriting code. The system understands Nepali and English (text and voice), retrieves answers from the business's own documents, and takes real actions (book, cancel, query, notify) through a set of structured tools. It knows when it does not know the answer and hands off to a human staff member when confidence is low or the situation demands it.

The demo business is **Himalayan Heritage Hotel**, a fictional 40-room mid-range hotel in the Itahari/Dharan region of eastern Nepal.

---

## 2. Problem Statement

Small and mid-size Nepali businesses — hotels, hospitals, agricultural cooperatives, retail stores — lose bookings and customer trust because:

- Staff are unavailable 24/7, especially outside office hours and during festivals.
- Customer queries arrive in multiple languages (Nepali Devanagari, Romanized Nepali, English) and staff cannot always respond in the customer's preferred language.
- Existing chatbots are static FAQ bots with no ability to check real availability, make bookings, or send confirmations.
- Human escalation is ad hoc: there is no structured handoff or audit trail.
- Businesses cannot measure how well their AI assistant is performing.

---

## 3. Personas

### 3.1 Guest (Primary User)
- **Who:** Hotel visitor, prospective guest, or current in-house guest contacting via web chat or WhatsApp-style interface.
- **Languages:** Nepali (Devanagari script), Romanized Nepali ("kati parcha"), English, or code-switched ("Deluxe room available cha?").
- **Goals:** Check room availability, get a price quote, make a booking, cancel or modify a booking, ask about amenities, request services (pickup, laundry, tour).
- **Pain points:** Does not want to call the front desk; wants instant answers at any hour; needs price in NPR; may not know the Gregorian date (may say "5 Kartik" instead of "21 October").
- **Technical literacy:** Low to medium. Uses a smartphone browser or embedded chat widget.

### 3.2 Hotel Manager / Staff (Internal Operator)
- **Who:** Front desk staff or hotel manager monitoring the admin dashboard.
- **Goals:** See incoming handoff tickets, respond to escalated conversations, view bookings, resolve disputes, manage documents in the knowledge base.
- **Pain points:** Currently manages inquiries by phone; needs a single inbox for AI-escalated issues; needs to reply in-thread so the customer sees the response.
- **Technical literacy:** Medium. Comfortable with a simple web dashboard; not a developer.

### 3.3 System Administrator
- **Who:** IT person or developer who deploys and maintains the system.
- **Goals:** Upload and manage knowledge-base documents, configure the system for a new business type, monitor ingestion status and errors, deploy updates.
- **Technical literacy:** High. Uses terminal, Docker, environment variables.

---

## 4. User Stories

### Guest Stories
| ID | Story | Priority |
|----|-------|----------|
| G-01 | As a guest, I can ask "Do you have a deluxe room for 2 people from 5 to 8 Kartik?" in Nepali or English and get a real availability check with price in NPR. | P0 |
| G-02 | As a guest, I can confirm a booking and receive an SMS and email confirmation in my preferred language within 30 seconds. | P0 |
| G-03 | As a guest, I can ask "Dashain ko bela ma family suite kati parcha?" and get the seasonally adjusted price. | P0 |
| G-04 | As a guest, I can say "Mero booking cancel garna paryo" and the AI will ask for my booking ID and phone, verify identity, apply the cancellation policy, and confirm cancellation. | P0 |
| G-05 | As a guest, I can ask about check-out time and late check-out and get an answer grounded in the hotel's policy document with a source citation. | P0 |
| G-06 | As a guest, I can complain about my room and be seamlessly transferred to a human staff member without losing context. | P0 |
| G-07 | As a guest, I can speak into the mic and get a spoken response in my language. | P1 |
| G-08 | As a guest, I can switch between English and Nepali mid-conversation and the AI will follow. | P1 |
| G-09 | As a guest, I can ask about nearby attractions, restaurant menu, and tour packages. | P1 |
| G-10 | As a guest, I can request airport/bus-park pickup when I have an existing booking. | P1 |

### Manager / Staff Stories
| ID | Story | Priority |
|----|-------|----------|
| M-01 | As a manager, I receive a Telegram or Slack alert when a conversation is escalated, containing a conversation summary and guest details. | P0 |
| M-02 | As a manager, I can open the admin dashboard, see all open handoff tickets, and reply to a guest in-thread. | P0 |
| M-03 | As a manager, I can see all past and upcoming bookings with guest details, dates, room type, and total in NPR. | P1 |
| M-04 | As a manager, I can see all past conversations and filter by date, language, or outcome. | P1 |
| M-05 | As a manager, I can mark a handoff ticket as resolved. | P0 |

### Admin Stories
| ID | Story | Priority |
|----|-------|----------|
| A-01 | As an admin, I can upload a PDF or Markdown document and see its ingestion status move from "queued" to "indexed". | P0 |
| A-02 | As an admin, I can delete a document and know that its vectors are removed from the knowledge base. | P0 |
| A-03 | As an admin, I can view ingestion errors with enough detail to fix the source document. | P1 |
| A-04 | As an admin, I can rotate JWT secrets without redeploying the application. | P1 |

---

## 5. Functional Requirements

### 5.1 Conversational AI Core
- **FR-01:** The system MUST detect the language of each user message (English, Nepali Devanagari, Romanized Nepali) and respond in the same language. Language detection must handle code-switching within a single message.
- **FR-02:** The system MUST convert Bikram Sambat dates (e.g., "5 Kartik") to Gregorian before passing them to any tool. A dedicated utility handles this conversion and is tested separately.
- **FR-03:** All monetary amounts MUST be displayed in NPR (Nepali Rupees, "रू" symbol) with comma separators following the South Asian numbering convention (e.g., "रू 1,20,000").
- **FR-04:** The system MUST NOT fabricate information. If retrieval returns no relevant chunks above the confidence threshold, the response must say it does not know and offer to connect the guest to a human.
- **FR-05:** The system MUST ask for explicit user confirmation (dates, room type, total price) before calling `book_room`. The booking cannot proceed without confirmation.
- **FR-06:** Every response grounded in a retrieved document MUST include a source citation showing the document name and page/section.

### 5.2 Multi-Agent Orchestration
- **FR-07:** The Supervisor/Router agent MUST classify each message into one of: FAQ, booking-intent, service-request, small-talk, cancellation, modification, complaint/escalation, or out-of-scope.
- **FR-08:** The system MUST support retry loops: if a tool call fails (e.g., DB timeout), the agent retries up to 2 times before escalating to a human.
- **FR-09:** LangGraph MUST use a Postgres checkpointer so conversation state is durable across process restarts.
- **FR-10:** Human handoff MUST use LangGraph interrupts. The conversation MUST pause (no automated replies) until the human responds, and then MUST resume with the human's reply forwarded to the customer.

### 5.3 Booking and Tool Calls
- **FR-11:** `book_room` MUST use a DB transaction with row-level locking to prevent double-booking. A guest should never be booked into an occupied room.
- **FR-12:** `cancel_booking` MUST verify the caller's phone number matches the booking before cancelling.
- **FR-13:** All tool inputs MUST be validated with Pydantic. Invalid inputs MUST return structured error objects the agent can translate into a user-facing message.
- **FR-14:** Seasonal pricing multipliers for Dashain, Tihar, and Chhath MUST be applied automatically in `get_room_price`.

### 5.4 RAG Knowledge Base
- **FR-15:** The ingestion pipeline MUST support PDF and Markdown files. Text splitting MUST use a recursive character splitter tuned for Devanagari (split on Devanagari sentence-ending characters as well as standard punctuation).
- **FR-16:** Embeddings MUST use a multilingual model that supports Nepali. The model name MUST be configurable via environment variable.
- **FR-17:** The vector store MUST use pgvector with cosine similarity and an HNSW or IVFFlat index.
- **FR-18:** Retrieval MUST return the top-k chunks (configurable, default 5) with relevance scores. Chunks below `RETRIEVAL_CONFIDENCE_THRESHOLD` (default 0.6) MUST be filtered out.
- **FR-19:** The RAG agent MAY apply an optional reranker (cross-encoder) when configured. The reranker is a swappable provider interface.

### 5.5 Notifications
- **FR-20:** After a successful `book_room`, the Notification Agent MUST dispatch an SMS and email confirmation within 60 seconds. Both MUST contain: Booking ID, guest name, room type, check-in/check-out dates, total NPR, and check-in time.
- **FR-21:** SMS and email providers MUST be interfaces with mock implementations for local development and real implementations configurable via env vars.
- **FR-22:** A failed notification MUST be logged and retried once. Persistent failure MUST be recorded in the notification log and must not block the user response.

### 5.6 Human Handoff
- **FR-23:** Handoff MUST be triggered by: (a) complaint keyword detected, (b) group booking >10 guests, (c) 2 consecutive tool failures, (d) retrieval confidence below threshold for 2 turns, (e) explicit user request for a human, (f) medical emergency keyword.
- **FR-24:** The manager alert (Telegram or Slack) MUST include: session ID, conversation summary (last 5 turns), guest language, relevant booking ID if any, and trigger reason.
- **FR-25:** The manager's reply in the admin dashboard MUST appear in the customer's chat interface within 5 seconds (via WebSocket push).

### 5.7 Voice
- **FR-26:** The system MUST expose a WebSocket endpoint for bidirectional audio streaming.
- **FR-27:** STT and TTS providers MUST be interfaces with at least one real implementation that supports Nepali. Provider tradeoffs MUST be documented.
- **FR-28:** Voice responses MUST use the same agent pipeline as text responses; there MUST NOT be a separate voice-only logic path.

### 5.8 Admin Dashboard
- **FR-29:** The dashboard MUST be protected by JWT authentication with role-based access (admin, staff).
- **FR-30:** Document upload MUST show real-time ingestion status updates (queued → processing → indexed / failed).
- **FR-31:** The handoff inbox MUST show unresolved tickets first, sorted by time. Staff can reply and resolve.
- **FR-32:** The bookings page MUST show all bookings with filter by date range, status, and room type.

---

## 6. Non-Functional Requirements

### 6.1 Latency
| Metric | Target |
|--------|--------|
| Text response (P95) | ≤ 4 seconds from message send to first token streamed |
| Booking confirmation end-to-end | ≤ 8 seconds including DB write and notification dispatch |
| RAG retrieval (top-5) | ≤ 500 ms |
| Voice STT → LLM → TTS round-trip (P95) | ≤ 6 seconds |

### 6.2 Availability
- Target uptime: 99.5% per month (excludes scheduled maintenance).
- Database writes use transactions; no booking should be lost due to application crash mid-flow.

### 6.3 Security
- All secrets (DB passwords, API keys, JWT secret) stored in environment variables, never committed to source control.
- JWT tokens: access token TTL 15 minutes, refresh token TTL 7 days, stored in HTTP-only cookies.
- All API endpoints authenticated except the public chat WebSocket (which uses a session token, not a user JWT).
- SQL queries use parameterized statements via SQLAlchemy ORM; no raw string interpolation.
- File uploads validated for MIME type and size (max 20 MB per document).
- Rate limiting: 60 requests/minute per IP on the chat endpoint.

### 6.4 Privacy
- Guest PII (name, phone, email) stored only in the relational DB.
- Conversation logs stored with session IDs; PII is not stored in vector embeddings.
- Guests can request deletion of their conversation history via a GDPR-style API endpoint (marked P2 for future implementation).

### 6.5 Scalability
- Horizontal scaling supported for the FastAPI application layer (stateless; LangGraph state in Postgres).
- pgvector index supports up to 100,000 document chunks before requiring reindexing tuning.
- The notification queue (BackgroundTasks initially, upgradeable to Celery + Redis) handles burst of 50 concurrent booking confirmations.

### 6.6 Observability
- Structured JSON logs with request ID, session ID, agent node, tool name, latency, and outcome on every log line.
- Log levels: DEBUG (dev), INFO (staging), WARNING (prod default).
- All tool calls logged with input (PII redacted), output status, and duration.

### 6.7 Internationalisation
- All user-facing strings driven by locale files (en.json, ne.json). No hardcoded strings in agent prompts or UI.
- Date formatting follows Nepali conventions when the user language is Nepali.
- The Bikram Sambat converter is tested for the range 2070 BS – 2090 BS (roughly 2013–2033 CE).

---

## 7. Success Metrics

| Metric | Target at 3 Months |
|--------|-------------------|
| Booking intent completion rate (guest starts booking flow and completes) | ≥ 65% |
| FAQ resolution without handoff | ≥ 80% |
| Average response latency (text, P95) | ≤ 4 s |
| RAG answer accuracy on golden Q&A set | ≥ 85% RAGAS faithfulness, ≥ 80% answer relevance |
| False escalation rate (unnecessary handoffs) | ≤ 15% |
| Bilingual response correctness (human eval sample) | ≥ 90% |
| Notification delivery success rate | ≥ 98% |

---

## 8. Out of Scope (v1.0)

- Payment processing (eSewa, Khalti integration produces a payment link but does not process transactions).
- WhatsApp or Viber channel integration (web chat and WebSocket API only).
- Real-time room sensor integration (IoT).
- Full GDPR data deletion workflow (endpoint placeholder only).
- Multi-property management (single hotel instance per deployment).
- Custom training / fine-tuning of the LLM.
- Mobile native app (React Native or Flutter).

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Nepali STT/TTS quality is poor across all available providers | Medium | High | Document fallback to text-only mode; use a provider with the best Devanagari support; allow admin to disable voice |
| LLM hallucinates information not in the knowledge base | High | High | Mandatory grounding check in RAG agent; return "I don't know" if no chunk above threshold |
| Double-booking under concurrent load | Low | Critical | Row-level DB locking in `book_room` transaction; load-tested in Phase 13 |
| Bikram Sambat conversion errors around month boundaries | Medium | Medium | Comprehensive unit tests covering all 12 Nepali months and leap years |
| pgvector performance degrades as document count grows | Low | Medium | HNSW index from the start; re-index script documented |
| JWT secret compromise | Low | Critical | Short access token TTL (15 min), refresh token rotation, documented rotation procedure |
| Seasonal pricing not applied → guest sees wrong price | Medium | High | `get_room_price` always passes through pricing engine; golden test for Dashain dates |
