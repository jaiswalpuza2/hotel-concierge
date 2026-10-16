# Technical Design Document
## Autonomous Multi-Agent Local Business Concierge
### Demo Instance: Himalayan Heritage Hotel

**Version:** 1.0.0  
**Date:** 2026-10-12

---

## 1. Database Schema (Complete)

### 1.1 `users`
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  NOT NULL CHECK (role IN ('admin', 'staff')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

### 1.2 `room_types`
```sql
CREATE TABLE room_types (
    id              VARCHAR(50)  PRIMARY KEY,  -- e.g. 'standard', 'deluxe', 'family_suite', 'conference_hall'
    name            VARCHAR(100) NOT NULL,
    capacity        INTEGER      NOT NULL CHECK (capacity > 0),
    bed_type        VARCHAR(100) NOT NULL,
    base_price_npr  INTEGER      NOT NULL CHECK (base_price_npr > 0),
    amenities       TEXT         NOT NULL,     -- JSON array stored as text, or use JSONB
    floor_count     INTEGER      NOT NULL DEFAULT 1
);
```

### 1.3 `rooms`
```sql
CREATE TABLE rooms (
    id              SERIAL       PRIMARY KEY,
    number          VARCHAR(10)  NOT NULL UNIQUE,  -- e.g. '101', '201', 'CONF-A'
    floor           INTEGER      NOT NULL,
    room_type_id    VARCHAR(50)  NOT NULL REFERENCES room_types(id),
    status          VARCHAR(20)  NOT NULL DEFAULT 'available'
                    CHECK (status IN ('available', 'occupied', 'maintenance', 'reserved'))
);
```

### 1.4 `guests`
```sql
CREATE TABLE guests (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL,
    phone               VARCHAR(20)  NOT NULL UNIQUE,
    email               VARCHAR(255),
    preferred_language  VARCHAR(10)  NOT NULL DEFAULT 'en'
                        CHECK (preferred_language IN ('en', 'ne')),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

### 1.5 `bookings`
```sql
CREATE TABLE bookings (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id         UUID        NOT NULL REFERENCES guests(id),
    room_id          INTEGER     NOT NULL REFERENCES rooms(id),
    check_in         DATE        NOT NULL,
    check_out        DATE        NOT NULL,
    guests_count     INTEGER     NOT NULL CHECK (guests_count > 0),
    status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
    total_price_npr  INTEGER     NOT NULL CHECK (total_price_npr >= 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_checkout_after_checkin CHECK (check_out > check_in)
);
CREATE INDEX idx_bookings_room_dates ON bookings (room_id, check_in, check_out)
    WHERE status NOT IN ('cancelled');
CREATE INDEX idx_bookings_guest ON bookings (guest_id);
```

### 1.6 `seasonal_pricing`
```sql
CREATE TABLE seasonal_pricing (
    id              SERIAL          PRIMARY KEY,
    name            VARCHAR(100)    NOT NULL,  -- e.g. 'Dashain 2081'
    start_date      DATE            NOT NULL,
    end_date        DATE            NOT NULL,
    multiplier      NUMERIC(4, 2)   NOT NULL CHECK (multiplier > 0),
    room_type_id    VARCHAR(50)     REFERENCES room_types(id),  -- NULL = applies to all
    CONSTRAINT chk_seasonal_end_after_start CHECK (end_date >= start_date)
);
```

### 1.7 `restaurant_tables`
```sql
CREATE TABLE restaurant_tables (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(50)  NOT NULL,  -- e.g. 'Table 1', 'Garden Table'
    capacity    INTEGER      NOT NULL CHECK (capacity > 0)
);
```

### 1.8 `table_reservations`
```sql
CREATE TABLE table_reservations (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id         INTEGER     NOT NULL REFERENCES restaurant_tables(id),
    guest_id         UUID        REFERENCES guests(id),
    reservation_date DATE        NOT NULL,
    reservation_time TIME        NOT NULL,
    party_size       INTEGER     NOT NULL CHECK (party_size > 0),
    status           VARCHAR(20) NOT NULL DEFAULT 'confirmed'
                     CHECK (status IN ('confirmed', 'cancelled', 'completed'))
);
```

### 1.9 `services`
```sql
CREATE TABLE services (
    id          SERIAL       PRIMARY KEY,
    type        VARCHAR(50)  NOT NULL,   -- 'pickup', 'laundry', 'tour'
    name        VARCHAR(255) NOT NULL,
    price_npr   INTEGER      NOT NULL CHECK (price_npr >= 0),
    description TEXT         NOT NULL
);
```

### 1.10 `service_requests`
```sql
CREATE TABLE service_requests (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id  UUID        REFERENCES bookings(id),
    service_id  INTEGER     NOT NULL REFERENCES services(id),
    details     TEXT,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 1.11 `documents`
```sql
CREATE TABLE documents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(255) NOT NULL,          -- stored filename on disk/S3
    original_name   VARCHAR(255) NOT NULL,          -- original upload name
    mime_type       VARCHAR(100) NOT NULL,
    size_bytes      INTEGER      NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'processing', 'indexed', 'failed')),
    error_message   TEXT,
    chunk_count     INTEGER      DEFAULT 0,
    uploaded_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    indexed_at      TIMESTAMPTZ
);
```

### 1.12 `document_chunks`
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER     NOT NULL,
    content         TEXT        NOT NULL,
    embedding       vector(768) NOT NULL,   -- dimension set by EMBEDDING_DIMENSIONS env var
    metadata        JSONB       NOT NULL DEFAULT '{}',   -- {page: N, lang: "en", section: "..."}
    page_number     INTEGER
);
CREATE INDEX idx_chunks_document ON document_chunks (document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 1.13 `conversations`
```sql
CREATE TABLE conversations (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID        NOT NULL UNIQUE,
    guest_id          UUID        REFERENCES guests(id),
    detected_language VARCHAR(10) NOT NULL DEFAULT 'en',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status            VARCHAR(20) NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'handed_off', 'resolved', 'abandoned'))
);
```

### 1.14 `messages`
```sql
CREATE TABLE messages (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID        NOT NULL REFERENCES conversations(id),
    role             VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'human_agent', 'system')),
    content          TEXT        NOT NULL,
    intent           VARCHAR(50),
    confidence       FLOAT,
    tool_calls       JSONB       DEFAULT '[]',
    retrieved_chunks JSONB       DEFAULT '[]',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at);
```

### 1.15 `handoff_tickets`
```sql
CREATE TABLE handoff_tickets (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id       UUID        NOT NULL REFERENCES conversations(id),
    booking_id            UUID        REFERENCES bookings(id),
    trigger_reason        VARCHAR(100) NOT NULL,
    conversation_summary  TEXT        NOT NULL,
    guest_language        VARCHAR(10)  NOT NULL,
    status                VARCHAR(20)  NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'in_progress', 'resolved')),
    manager_reply         TEXT,
    resolved_by           UUID        REFERENCES users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at           TIMESTAMPTZ
);
CREATE INDEX idx_handoff_status ON handoff_tickets (status, created_at);
```

### 1.16 `notification_log`
```sql
CREATE TABLE notification_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id      UUID        NOT NULL REFERENCES bookings(id),
    type            VARCHAR(20) NOT NULL CHECK (type IN ('sms', 'email')),
    status          VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
    recipient       VARCHAR(255) NOT NULL,     -- phone or email (partially redacted in logs)
    message         TEXT        NOT NULL,
    attempt_count   INTEGER     NOT NULL DEFAULT 1,
    sent_at         TIMESTAMPTZ
);
```

---

## 2. API Contracts

### 2.1 Authentication

```
POST /api/v1/auth/login
Request:  { "email": "string", "password": "string" }
Response: { "access_token": "string", "refresh_token": "string", "token_type": "bearer",
            "expires_in": 900, "user": { "id": "uuid", "email": "string", "role": "admin|staff" } }
Status: 200 | 401

POST /api/v1/auth/refresh
Request:  { "refresh_token": "string" }
Response: { "access_token": "string", "expires_in": 900 }
Status: 200 | 401

POST /api/v1/auth/logout
Headers: Authorization: Bearer <access_token>
Response: 204 No Content
```

### 2.2 Documents

```
POST /api/v1/documents
Headers: Authorization: Bearer <access_token> (admin only)
Content-Type: multipart/form-data
Body: file (binary), language ("en"|"ne")
Response: { "id": "uuid", "original_name": "string", "status": "queued", "uploaded_at": "ISO8601" }
Status: 201 | 400 | 413

GET /api/v1/documents?page=1&page_size=20
Headers: Authorization: Bearer <access_token>
Response: { "items": [ DocumentStatus ], "total": N, "page": N, "page_size": N }
DocumentStatus: { "id": "uuid", "original_name": "string", "status": "queued|processing|indexed|failed",
                   "chunk_count": N, "uploaded_at": "ISO8601", "indexed_at": "ISO8601|null",
                   "error_message": "string|null" }

DELETE /api/v1/documents/{id}
Headers: Authorization: Bearer <access_token> (admin only)
Response: 204 No Content | 404
```

### 2.3 Bookings (Admin)

```
GET /api/v1/bookings?page=1&page_size=20&status=confirmed&from_date=2026-10-01&to_date=2026-12-31&room_type=deluxe
Headers: Authorization: Bearer <access_token>
Response: { "items": [ BookingDetail ], "total": N, "page": N, "page_size": N }
BookingDetail: { "id": "uuid", "guest_name": "string", "guest_phone": "string",
                  "room_number": "string", "room_type": "string",
                  "check_in": "YYYY-MM-DD", "check_out": "YYYY-MM-DD",
                  "guests_count": N, "status": "string", "total_price_npr": N,
                  "created_at": "ISO8601" }

GET /api/v1/bookings/{id}
Headers: Authorization: Bearer <access_token>
Response: BookingDetail (with service_requests array)
Status: 200 | 404
```

### 2.4 Conversations (Admin)

```
GET /api/v1/conversations?page=1&page_size=20&language=ne&status=resolved
Headers: Authorization: Bearer <access_token>
Response: { "items": [ ConversationSummary ], "total": N, "page": N, "page_size": N }
ConversationSummary: { "id": "uuid", "session_id": "uuid", "detected_language": "string",
                        "message_count": N, "started_at": "ISO8601", "last_active_at": "ISO8601",
                        "status": "string" }

GET /api/v1/conversations/{id}/messages
Headers: Authorization: Bearer <access_token>
Response: { "messages": [ Message ] }
Message: { "id": "uuid", "role": "string", "content": "string",
            "intent": "string|null", "created_at": "ISO8601",
            "retrieved_chunks": [ CitationRef ] }
```

### 2.5 Handoff Tickets

```
GET /api/v1/handoffs?page=1&page_size=20&status=open
Headers: Authorization: Bearer <access_token>
Response: { "items": [ HandoffTicket ], "total": N, "page": N, "page_size": N }
HandoffTicket: { "id": "uuid", "conversation_id": "uuid", "booking_id": "uuid|null",
                  "trigger_reason": "string", "conversation_summary": "string",
                  "guest_language": "string", "status": "open|in_progress|resolved",
                  "manager_reply": "string|null", "created_at": "ISO8601",
                  "resolved_at": "ISO8601|null" }

POST /api/v1/handoffs/{id}/reply
Headers: Authorization: Bearer <access_token>
Request: { "reply": "string" }
Response: HandoffTicket (updated)
Status: 200 | 404

PATCH /api/v1/handoffs/{id}/resolve
Headers: Authorization: Bearer <access_token>
Response: HandoffTicket (status=resolved)
Status: 200 | 404
```

### 2.6 Health

```
GET /health
Response: { "status": "ok", "db": "ok|degraded", "vector_db": "ok|degraded", "version": "1.0.0" }
Status: 200 | 503
```

---

## 3. WebSocket Message Protocol

All messages are JSON-encoded text frames.

### 3.1 Client → Server (Chat)

```typescript
// Initiate or resume conversation
type ConnectMessage = {
  type: "connect";
  session_id: string;        // UUID, client-generated on first connect
  language: "en" | "ne";    // user's current preferred language
}

// Send a text message
type UserMessage = {
  type: "message";
  text: string;
  language: "en" | "ne" | "ne_roman";
  timestamp: string;         // ISO8601
}

// User confirms booking details
type ConfirmMessage = {
  type: "confirm";
  confirmed: boolean;
}

// Language switch
type LanguageSwitchMessage = {
  type: "language_switch";
  new_language: "en" | "ne";
}
```

### 3.2 Server → Client (Chat)

```typescript
// First token of a new response
type StreamStart = {
  type: "stream_start";
  message_id: string;
}

// Streaming token delta
type StreamDelta = {
  type: "stream_delta";
  message_id: string;
  delta: string;
}

// Streaming complete
type StreamEnd = {
  type: "stream_end";
  message_id: string;
  intent: string;
  citations: Citation[];
}

// Booking confirmation prompt
type BookingConfirmPrompt = {
  type: "booking_confirm_prompt";
  booking_draft: {
    room_type: string;
    room_type_display: string;    // localised
    check_in: string;             // YYYY-MM-DD
    check_out: string;
    nights: number;
    guests: number;
    total_price_npr: number;
    room_number: string;
  };
}

// Booking confirmed
type BookingConfirmed = {
  type: "booking_confirmed";
  booking_id: string;
  message: string;               // localised confirmation text
}

// Human handoff triggered
type HandoffStarted = {
  type: "handoff_started";
  ticket_id: string;
  message: string;               // "Connecting you to our staff…"
}

// Human agent reply forwarded
type HumanAgentMessage = {
  type: "human_agent_message";
  sender_name: string;           // Manager's display name
  text: string;
  timestamp: string;
}

// Error
type ErrorMessage = {
  type: "error";
  code: string;
  message: string;
}

type Citation = {
  document_name: string;
  page: number | null;
  section: string | null;
  score: number;
}
```

### 3.3 Voice WebSocket (`/ws/voice/{session_id}`)

```
Client → Server: binary frames (raw PCM audio, 16kHz, 16-bit, mono)
Client → Server: JSON {"type":"end_of_speech"} to signal turn end
Server → Client: JSON {"type":"transcript","text":"...","lang":"en"}  (partial/final)
Server → Client: binary frames (MP3 audio response)
Server → Client: JSON {"type":"response_text","text":"...","citations":[...]}
Server → Client: JSON {"type":"audio_end"}
```

---

## 4. Tool JSON Schemas

### 4.1 `check_room_availability`
```json
{
  "name": "check_room_availability",
  "description": "Check which rooms of a given type are available for the requested dates and guest count.",
  "parameters": {
    "type": "object",
    "properties": {
      "check_in":   { "type": "string", "format": "date", "description": "Check-in date (YYYY-MM-DD, Gregorian)" },
      "check_out":  { "type": "string", "format": "date", "description": "Check-out date (YYYY-MM-DD, Gregorian)" },
      "guests":     { "type": "integer", "minimum": 1, "maximum": 10 },
      "room_type":  { "type": "string", "enum": ["standard","deluxe","family_suite","conference_hall"], "description": "Optional filter" }
    },
    "required": ["check_in", "check_out", "guests"]
  }
}
```

### 4.2 `get_room_price`
```json
{
  "name": "get_room_price",
  "description": "Get the total price for a room type and date range, including seasonal multipliers.",
  "parameters": {
    "type": "object",
    "properties": {
      "room_type":  { "type": "string", "enum": ["standard","deluxe","family_suite","conference_hall"] },
      "check_in":   { "type": "string", "format": "date" },
      "check_out":  { "type": "string", "format": "date" }
    },
    "required": ["room_type", "check_in", "check_out"]
  }
}
```

### 4.3 `book_room`
```json
{
  "name": "book_room",
  "description": "Create a confirmed room booking. MUST only be called after explicit user confirmation of dates, room type, and total price.",
  "parameters": {
    "type": "object",
    "properties": {
      "guest_name":  { "type": "string", "minLength": 2, "maxLength": 255 },
      "phone":       { "type": "string", "pattern": "^\\+977[0-9]{10}$|^9[0-9]{9}$" },
      "email":       { "type": "string", "format": "email" },
      "room_type":   { "type": "string", "enum": ["standard","deluxe","family_suite","conference_hall"] },
      "check_in":    { "type": "string", "format": "date" },
      "check_out":   { "type": "string", "format": "date" },
      "guests":      { "type": "integer", "minimum": 1, "maximum": 10 },
      "language":    { "type": "string", "enum": ["en", "ne"], "description": "Guest's language for confirmation" }
    },
    "required": ["guest_name", "phone", "room_type", "check_in", "check_out", "guests"]
  }
}
```

### 4.4 `cancel_booking`
```json
{
  "name": "cancel_booking",
  "description": "Cancel an existing booking after verifying the guest's identity via phone number.",
  "parameters": {
    "type": "object",
    "properties": {
      "booking_id": { "type": "string", "format": "uuid" },
      "phone":      { "type": "string", "description": "Must match the phone number on the booking" }
    },
    "required": ["booking_id", "phone"]
  }
}
```

### 4.5 `modify_booking`
```json
{
  "name": "modify_booking",
  "description": "Change the check-in or check-out dates of an existing booking.",
  "parameters": {
    "type": "object",
    "properties": {
      "booking_id":     { "type": "string", "format": "uuid" },
      "phone":          { "type": "string" },
      "new_check_in":   { "type": "string", "format": "date" },
      "new_check_out":  { "type": "string", "format": "date" }
    },
    "required": ["booking_id", "phone"]
  }
}
```

### 4.6 `get_booking_status`
```json
{
  "name": "get_booking_status",
  "description": "Retrieve the details and current status of a booking.",
  "parameters": {
    "type": "object",
    "properties": {
      "booking_id": { "type": "string", "format": "uuid" },
      "phone":      { "type": "string" }
    },
    "required": ["booking_id", "phone"]
  }
}
```

### 4.7 `reserve_restaurant_table`
```json
{
  "name": "reserve_restaurant_table",
  "description": "Reserve a table at the hotel restaurant.",
  "parameters": {
    "type": "object",
    "properties": {
      "date":       { "type": "string", "format": "date" },
      "time":       { "type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$", "description": "24h format HH:MM" },
      "party_size": { "type": "integer", "minimum": 1, "maximum": 20 },
      "guest_name": { "type": "string" },
      "phone":      { "type": "string" }
    },
    "required": ["date", "time", "party_size", "guest_name"]
  }
}
```

### 4.8 `request_service`
```json
{
  "name": "request_service",
  "description": "Request an additional hotel service (airport pickup, laundry, tour).",
  "parameters": {
    "type": "object",
    "properties": {
      "service_type": { "type": "string", "enum": ["airport_pickup","bus_park_pickup","laundry","koshi_tappu_tour","dharan_tour"] },
      "booking_id":   { "type": "string", "format": "uuid" },
      "details":      { "type": "string", "description": "Free-text details, e.g. flight number or pickup time" }
    },
    "required": ["service_type", "booking_id"]
  }
}
```

---

## 5. LangGraph Node and Edge Definitions

### 5.1 Nodes

| Node | Async function signature | Responsibility |
|------|--------------------------|----------------|
| `route_intent` | `(state) → state` | Classify message intent + detect language; set `state.intent`, `state.detected_language`, `state.confidence_score` |
| `retrieve_chunks` | `(state) → state` | Query pgvector, filter by threshold, populate `state.retrieved_chunks` |
| `call_tools` | `(state) → state` | Execute one or more tools, populate `state.tool_results`, increment `state.retry_count` on failure |
| `draft_response` | `(state) → state` | LLM call to produce final user-facing text; uses tool results and retrieved chunks; sets `state.messages[-1]` |
| `ask_confirmation` | `(state) → state` | Emit a `booking_confirm_prompt` WS message; set `state.awaiting_confirmation = True` |
| `send_notifications` | `(state) → state` | Dispatch SMS + email async; update `state.notification_status` |
| `evaluate_handoff` | `(state) → state` | Score confidence, check trigger conditions; set `state.escalation_reason` |
| `create_handoff_ticket` | `(state) → state` | Write `handoff_tickets` row, set `state.handoff_ticket_id`, fire alert provider |
| `await_human_reply` | `(state) → state` | INTERRUPT node — pauses execution until `state.human_reply` is set |
| `forward_human_reply` | `(state) → state` | Prepend human reply to messages, clear `state.human_reply` |

### 5.2 Conditional Edges

```python
def should_retrieve(state: ConversationState) -> str:
    """After route_intent: go to retrieve_chunks only for FAQ intents."""
    if state["intent"] in ("faq", "policy_query"):
        return "retrieve_chunks"
    if state["intent"] in ("booking_intent", "cancellation", "modification", "service_request"):
        return "call_tools"
    return "draft_response"  # small_talk, out_of_scope

def after_retrieval(state: ConversationState) -> str:
    """After retrieve_chunks: check if we got useful chunks."""
    good_chunks = [c for c in state["retrieved_chunks"] if c["score"] >= RETRIEVAL_THRESHOLD]
    if good_chunks:
        return "draft_response"
    if state["retry_count"] < MAX_RETRIEVAL_RETRIES:
        return "retrieve_chunks"  # retry with expanded query
    return "evaluate_handoff"    # escalate if still no results

def after_tool_call(state: ConversationState) -> str:
    """After call_tools."""
    last_result = state["tool_results"][-1] if state["tool_results"] else None
    if last_result and not last_result["success"]:
        if state["retry_count"] < MAX_TOOL_RETRIES:
            return "call_tools"
        return "evaluate_handoff"
    if last_result and last_result["tool_name"] == "book_room" and last_result["success"]:
        if not state["awaiting_confirmation"]:
            return "ask_confirmation"
        return "send_notifications"
    return "draft_response"

def after_evaluation(state: ConversationState) -> str:
    if state.get("escalation_reason"):
        return "create_handoff_ticket"
    return "draft_response"

def after_handoff_created(state: ConversationState) -> str:
    return "await_human_reply"

def after_human_reply(state: ConversationState) -> str:
    return "forward_human_reply"
```

---

## 6. Prompt Templates

### 6.1 System Prompt – Supervisor / Router (English)

```
You are the routing brain of an AI concierge for Himalayan Heritage Hotel in Itahari, Nepal.
Your only job is to classify the user's intent and detect their language.

Classify intent as one of:
- faq: question about hotel policies, amenities, menu, attractions, or general info
- booking_intent: wants to make a new room reservation
- cancellation: wants to cancel an existing booking
- modification: wants to change dates or details of an existing booking
- service_request: wants additional services (pickup, laundry, tour, table reservation)
- complaint: expressing dissatisfaction or wanting a refund
- small_talk: casual conversation with no actionable request
- out_of_scope: completely unrelated to the hotel

Detect language as one of: en, ne, ne_roman

Respond ONLY with a JSON object:
{"intent": "<intent>", "language": "<language>", "confidence": <0.0-1.0>}
```

### 6.2 System Prompt – Supervisor / Router (Nepali)

```
तपाईं Himalayan Heritage Hotel, इटहरी, नेपालको AI concierge को routing दिमाग हुनुहुन्छ।
तपाईंको एक मात्र काम प्रयोगकर्ताको उद्देश्य वर्गीकरण गर्नु र उनको भाषा पहिचान गर्नु हो।

निम्न मध्ये एक उद्देश्य वर्गीकरण गर्नुहोस्:
- faq: होटेल नीति, सुविधा, मेनु वा सामान्य जानकारीको प्रश्न
- booking_intent: नयाँ कोठा बुक गर्न चाहन्छ
- cancellation: बुकिङ रद्द गर्न चाहन्छ
- modification: बुकिङमा परिवर्तन गर्न चाहन्छ
- service_request: थप सेवाहरू चाहन्छ
- complaint: असन्तुष्टि वा फिर्ता चाहन्छ
- small_talk: सामान्य कुराकानी
- out_of_scope: होटेलसँग सम्बन्धित छैन

भाषा पहिचान: en, ne, ne_roman मध्ये एउटा

केवल JSON object फर्काउनुहोस्:
{"intent": "<intent>", "language": "<language>", "confidence": <0.0-1.0>}
```

### 6.3 RAG Agent – Grounded Response Prompt (English)

```
You are a knowledgeable and friendly concierge for Himalayan Heritage Hotel.
Answer the guest's question using ONLY the information in the provided document excerpts.

Rules:
1. If the answer is in the excerpts, answer clearly and cite the source as [Source: <document_name>, p.<page>].
2. If the answer is NOT in the excerpts, say: "I'm sorry, I don't have that information in our documents. Would you like me to connect you with our staff?"
3. Never invent information, prices, or policies.
4. All prices must be in NPR (रू).
5. Keep the tone warm and professional.

Document excerpts:
{retrieved_chunks}

Guest question: {user_message}
```

### 6.4 RAG Agent – Grounded Response Prompt (Nepali)

```
तपाईं Himalayan Heritage Hotel को जानकार र मैत्री concierge हुनुहुन्छ।
तलका दस्तावेज अंशहरू मात्र प्रयोग गरी पाहुनाको प्रश्नको उत्तर दिनुहोस्।

नियमहरू:
१. यदि उत्तर अंशहरूमा छ भने, स्पष्ट रूपमा उत्तर दिनुहोस् र स्रोत उल्लेख गर्नुहोस्: [स्रोत: <document_name>, पृ.<page>]
२. यदि उत्तर अंशहरूमा छैन भने, यसो भन्नुहोस्: "माफ गर्नुहोस्, हाम्रो कागजातमा त्यो जानकारी छैन। के हाम्रो कर्मचारीसँग जोड्न चाहनुहुन्छ?"
३. जानकारी, मूल्य वा नीतिहरू कहिल्यै मनगढन्ते नबनाउनुहोस्।
४. सबै मूल्य NPR (रू) मा हुनुपर्छ।

दस्तावेज अंशहरू:
{retrieved_chunks}

पाहुनाको प्रश्न: {user_message}
```

### 6.5 Booking Confirmation Prompt (English)

```
You are a hotel concierge confirming a booking for the guest. Present the following details clearly and ask for explicit confirmation.

Booking details:
- Room type: {room_type}
- Check-in: {check_in} (arrival after 2:00 PM)
- Check-out: {check_out} (departure by 11:00 AM)
- Number of nights: {nights}
- Guests: {guests}
- Total price: रू {total_price}

Ask: "Shall I confirm this booking? Please reply YES to confirm or NO to change the details."
```

### 6.6 Booking Confirmation Prompt (Nepali)

```
तपाईं पाहुनाको बुकिङ पुष्टि गर्दै हुनुहुन्छ। तलका विवरण स्पष्ट रूपमा प्रस्तुत गर्नुहोस् र स्पष्ट पुष्टि माग्नुहोस्।

बुकिङ विवरण:
- कोठाको किसिम: {room_type}
- चेक-इन: {check_in} (दिउँसो २ बजे पछि)
- चेक-आउट: {check_out} (बिहान ११ बजे अगाडि)
- रात्री संख्या: {nights}
- पाहुना संख्या: {guests}
- कुल मूल्य: रू {total_price}

सोध्नुहोस्: "के म यो बुकिङ पक्का गर्ने? पुष्टि गर्न YES वा विवरण परिवर्तन गर्न NO टाइप गर्नुहोस्।"
```

### 6.7 Handoff Message (English)

```
I'm connecting you to our hotel staff who will be able to help you further. 
A member of our team will respond shortly. Your conversation history has been shared with them.
```

### 6.8 Handoff Message (Nepali)

```
म तपाईंलाई हाम्रो होटेल कर्मचारीसँग जोड्दैछु जसले तपाईंलाई थप सहायता गर्न सक्नुहुन्छ।
हाम्रो टिमको एक सदस्यले छिट्टै जवाफ दिनुहुनेछ। तपाईंको कुराकानी इतिहास उनीहरूसँग साझा गरिएको छ।
```

---

## 7. Handoff Ticket Lifecycle

```
States: open → in_progress → resolved

Transitions:
  open → in_progress  : triggered when a staff member opens the ticket in the dashboard
  in_progress → resolved : triggered when staff clicks "Resolve" after replying

Trigger reasons (machine-readable slugs):
  complaint_detected, group_booking, two_tool_failures, low_retrieval_confidence,
  user_requested_human, medical_emergency, payment_dispute, out_of_scope_repeated

Alert payload sent to Telegram / Slack:
{
  "hotel": "Himalayan Heritage Hotel",
  "ticket_id": "uuid",
  "session_id": "uuid",
  "trigger_reason": "complaint_detected",
  "guest_language": "ne",
  "booking_id": "uuid | null",
  "summary": "Guest complained about noise in room 301. Has booking BK-2026-0441 (check-out tomorrow).",
  "last_5_messages": [ { "role": "user|assistant", "text": "..." }, ... ],
  "dashboard_url": "https://admin.hotel.local/handoffs/<ticket_id>"
}
```

---

## 8. Frontend Component Tree

```
App (Next.js App Router)
├── /chat
│   └── ChatPage
│       └── ChatWindow (WebSocket manager, streaming buffer, lang state)
│           ├── HumanHandoffBanner (shown when status=handed_off)
│           ├── MessageList
│           │   └── MessageBubble[] (user | assistant | human_agent)
│           │       └── CitationBadge[] (inline, one per retrieved chunk)
│           └── InputBar
│               ├── TextInput (controlled, onKeyDown Enter to send)
│               ├── LanguageToggle (EN / नेपाली)
│               ├── MicButton → VoiceCapture (MediaRecorder, PCM stream)
│               └── SendButton
│
└── /admin
    ├── LoginPage (JWT form)
    └── AdminLayout (Navbar + Sidebar, auth guard)
        ├── /admin/documents
        │   └── DocumentsPage
        │       ├── DocumentUpload (drag-drop, progress bar, status SSE)
        │       └── DocumentList (table with StatusBadge)
        ├── /admin/handoffs
        │   └── HandoffsPage
        │       └── HandoffTicket[] (reply form, resolve button)
        ├── /admin/bookings
        │   └── BookingsPage
        │       ├── FilterBar (date range, status, room type)
        │       └── BookingTable (sortable data grid)
        └── /admin/conversations
            └── ConversationsPage
                └── ConversationViewer (message list with tool call details)
```

---

## 9. UI/UX Design Notes

### 9.1 Chat Interface
- Default language: auto-detected from browser's `navigator.language`. If `ne-NP` or `ne`, show Nepali UI strings; else English.
- Language toggle button in the input bar switches UI strings AND tells the server to respond in the new language from the next message onward.
- Streaming: messages render token-by-token using a streaming buffer. A blinking cursor shows while the stream is in progress.
- Citation badges: small pills at the bottom of each assistant message showing `[Document Name, p.N]`. Clicking a badge opens a tooltip with the full chunk text.
- Voice: mic button activates on click, shows a pulsing red indicator while recording. Releasing or clicking again stops recording and sends the audio. Plays back the TTS response automatically.
- Booking confirmation: a special card component shows the booking details table with "Confirm" (green) and "Cancel" (grey) buttons, making the confirmation step clear and unambiguous.
- Human handoff banner: a yellow banner at the top of the chat window shows "You are now connected with our staff" during handoff mode. Automated AI messages are paused.

### 9.2 Admin Dashboard
- Left sidebar navigation: Documents, Handoffs (badge with open count), Bookings, Conversations.
- Handoffs page: unresolved tickets at the top, sorted by created_at descending. Each ticket is a card showing: trigger reason badge, guest language flag, conversation summary, and an inline reply text area.
- Document upload: Dropzone component with progress bar. Status updates via SSE or WebSocket polling every 3 seconds.
- All tables are sortable and paginated client-side for small datasets (< 500 rows); server-paginated for larger sets.

### 9.3 Accessibility
- All interactive elements have visible focus rings (Tailwind `focus-visible:ring-2`).
- Mic button has `aria-label="Start voice recording"` / `"Stop voice recording"`.
- Language toggle has `aria-pressed` state.
- Colour is never the sole indicator of status (status badges always have text labels).
- Devanagari text uses `font-feature-settings: "kern"` and line-height ≥ 1.6 for readability.
- All images and icons have descriptive `alt` text or `aria-hidden="true"` for decorative elements.
- WCAG 2.1 AA target. Full validation requires manual testing with screen readers (NVDA, JAWS, VoiceOver).

---

## 10. Bikram Sambat Converter Design

The converter handles dates in the range **2070 BS – 2090 BS** (approximately 2013–2033 CE).

### Data structure
```python
# maps each BS year to: [days_in_Baisakh, days_in_Jestha, ..., days_in_Chaitra]
# 12 values per year; Nepali calendar months:
# 1=Baisakh, 2=Jestha, 3=Ashadh, 4=Shrawan, 5=Bhadra, 6=Ashwin,
# 7=Kartik, 8=Mangsir, 9=Poush, 10=Magh, 11=Falgun, 12=Chaitra
BS_CALENDAR_DATA: dict[int, list[int]] = { ... }  # seeded from official Nepal calendar
```

### API
```python
def bs_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert Bikram Sambat date to Gregorian."""

def gregorian_to_bs(gregorian_date: date) -> tuple[int, int, int]:
    """Convert Gregorian date to (BS year, BS month, BS day)."""

def parse_nepali_month_name(name: str) -> int:
    """Convert Nepali month name (Devanagari or Romanized) to month number (1-12)."""
    # Handles: "Kartik", "Kartik", "कार्तिक", "baisakh", "वैशाख", etc.

NEPALI_MONTH_NAMES: dict[str, int] = {
    "baisakh": 1, "वैशाख": 1,
    "jestha": 2, "जेठ": 2,
    "ashadh": 3, "असार": 3,
    "shrawan": 4, "साउन": 4,
    "bhadra": 5, "भदौ": 5,
    "ashwin": 6, "असोज": 6,
    "kartik": 7, "कार्तिक": 7,
    "mangsir": 8, "मङ्सिर": 8,
    "poush": 9, "पुस": 9,
    "magh": 10, "माघ": 10,
    "falgun": 11, "फागुन": 11,
    "chaitra": 12, "चैत": 12,
}
```

### Edge cases covered by tests
- Chaitra leap days (years where Chaitra has 31 instead of 30 days)
- Dates at the start of each month (day = 1)
- Dates at the end of each month (day = max days for that month/year)
- Year boundaries (e.g., 30 Chaitra → 1 Baisakh of next year)
- Range validation: raises `ValueError` for dates outside 2070–2090 BS

---

## 11. Business-Type Configuration Interface

To support swapping the concierge for a different business (hospital, co-op, retail), the following must be configuration-only:

```yaml
# business_config.yaml (loaded via Pydantic Settings)
business:
  name: "Himalayan Heritage Hotel"
  type: hotel                      # hotel | hospital | agri_coop | retail
  location: "Itahari, Sudurpurba Province, Nepal"
  currency: NPR
  timezone: "Asia/Kathmandu"
  default_language: ne
  supported_languages: [en, ne]

tools_enabled:
  - check_room_availability
  - get_room_price
  - book_room
  - cancel_booking
  - modify_booking
  - reserve_restaurant_table
  - request_service
  - get_booking_status

knowledge_base_path: "knowledge_base/"
system_prompt_template: "prompts/hotel_system.txt"
handoff_triggers:
  complaint_keywords: ["complaint", "refund", "terrible", "disgusting", "गुनासो", "फिर्ता"]
  group_size_threshold: 10
  tool_failure_threshold: 2
  retrieval_confidence_threshold: 0.6
```
