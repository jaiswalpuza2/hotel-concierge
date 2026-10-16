# Architecture Document
## Autonomous Multi-Agent Local Business Concierge
### Demo Instance: Himalayan Heritage Hotel

**Version:** 1.0.0  
**Date:** 2026-10-12

---

## 1. System Context Diagram

```mermaid
C4Context
    title System Context – Himalayan Heritage Hotel Concierge

    Person(guest, "Hotel Guest", "Browses via web chat or voice; speaks English or Nepali")
    Person(manager, "Hotel Manager/Staff", "Monitors handoff inbox, responds to escalations, manages documents")
    Person(admin, "System Admin", "Deploys system, manages env config")

    System(concierge, "Concierge Platform", "Multi-agent AI concierge: chat, voice, bookings, RAG, handoff")

    System_Ext(postgres, "PostgreSQL + pgvector", "Relational data + vector embeddings")
    System_Ext(llm, "LLM Provider (OpenAI / Ollama / etc.)", "Language model inference")
    System_Ext(sms, "SMS Gateway (Sparrow SMS / Twilio)", "Outbound SMS notifications")
    System_Ext(email, "Email Provider (SMTP / SendGrid)", "Outbound email notifications")
    System_Ext(telegram, "Telegram Bot API", "Manager handoff alerts")
    System_Ext(slack, "Slack Webhooks", "Manager handoff alerts (alternate)")
    System_Ext(stt_tts, "STT/TTS Provider (Google / Azure / OpenAI Whisper)", "Speech-to-text and text-to-speech")

    Rel(guest, concierge, "Chat (HTTPS WebSocket) or Voice (WebSocket audio stream)")
    Rel(manager, concierge, "Admin dashboard (HTTPS)")
    Rel(admin, concierge, "Docker deploy, env config, document upload")
    Rel(concierge, postgres, "Async SQL + pgvector queries")
    Rel(concierge, llm, "LLM API calls")
    Rel(concierge, sms, "Booking confirmation SMS")
    Rel(concierge, email, "Booking confirmation email")
    Rel(concierge, telegram, "Handoff alert")
    Rel(concierge, slack, "Handoff alert (alternate)")
    Rel(concierge, stt_tts, "Audio stream")
```

---

## 2. High-Level Component Architecture

```mermaid
graph TB
    subgraph Frontend["Next.js Frontend"]
        ChatUI["Customer Chat UI\n(streaming, citations, mic, EN/NE toggle)"]
        AdminUI["Admin Dashboard\n(upload, handoff inbox, bookings, conversations)"]
    end

    subgraph Gateway["FastAPI Gateway (Python 3.12, async)"]
        ChatWS["WebSocket /ws/chat/{session_id}"]
        VoiceWS["WebSocket /ws/voice/{session_id}"]
        RestAPI["REST API /api/v1/…"]
        AuthMiddleware["JWT Auth Middleware"]
        ErrorMiddleware["Global Error Handler + Structured Logger"]
    end

    subgraph AgentLayer["LangGraph Multi-Agent System"]
        Supervisor["Supervisor / Router"]
        ConvAgent["Conversation Agent"]
        RAGAgent["RAG Agent"]
        ToolAgent["Data / Tool Agent"]
        NotifAgent["Notification Agent"]
        GuardrailAgent["Guardrail / Handoff Agent"]
    end

    subgraph DataLayer["Data Layer"]
        PG[("PostgreSQL\n(bookings, guests, rooms…)")]
        PGV[("pgvector\n(document embeddings)")]
        PGCheckpoint[("LangGraph\nPostgres Checkpointer")]
    end

    subgraph IngestionPipeline["RAG Ingestion Pipeline"]
        Loader["PDF / Markdown Loader"]
        Splitter["Recursive Text Splitter\n(Devanagari-aware)"]
        Embedder["Multilingual Embedding Model"]
        VectorStore["pgvector Store"]
    end

    subgraph ExternalServices["External Services"]
        LLMProvider["LLM Provider Interface"]
        SMSProvider["SMS Provider Interface"]
        EmailProvider["Email Provider Interface"]
        HandoffProvider["Handoff Provider Interface\n(Telegram / Slack)"]
        STTProvider["STT Provider Interface"]
        TTSProvider["TTS Provider Interface"]
        Reranker["Reranker Interface (optional)"]
    end

    ChatUI -->|HTTPS WebSocket| ChatWS
    ChatUI -->|REST| RestAPI
    AdminUI -->|REST| RestAPI
    VoiceWS --> STTProvider
    TTSProvider --> VoiceWS

    ChatWS --> AuthMiddleware --> AgentLayer
    VoiceWS --> AuthMiddleware --> AgentLayer
    RestAPI --> AuthMiddleware

    Supervisor --> ConvAgent
    Supervisor --> RAGAgent
    Supervisor --> ToolAgent
    Supervisor --> GuardrailAgent
    ToolAgent --> NotifAgent
    GuardrailAgent --> HandoffProvider

    AgentLayer --> PG
    AgentLayer --> PGV
    AgentLayer --> PGCheckpoint
    AgentLayer --> LLMProvider

    ToolAgent --> SMSProvider
    ToolAgent --> EmailProvider
    NotifAgent --> SMSProvider
    NotifAgent --> EmailProvider

    Loader --> Splitter --> Embedder --> VectorStore
    VectorStore --> PGV
    RAGAgent --> Reranker
```

---

## 3. Request Data-Flow: Chat Message

```mermaid
sequenceDiagram
    participant G as Guest Browser
    participant WS as FastAPI WebSocket
    participant SV as Supervisor Agent
    participant RA as RAG Agent
    participant TA as Tool Agent
    participant DB as PostgreSQL
    participant VDB as pgvector
    participant LLM as LLM Provider
    participant NA as Notification Agent
    participant SMS as SMS Gateway

    G->>WS: {"type":"message","text":"Do you have deluxe room 5-8 Kartik?","lang":"en"}
    WS->>WS: Load or create LangGraph checkpoint (session_id)
    WS->>SV: invoke(state)

    SV->>LLM: Classify intent
    LLM-->>SV: intent=booking_intent, lang=en

    SV->>TA: route(booking_intent)
    TA->>TA: Parse dates, convert BS→Gregorian (if needed)
    TA->>DB: check_room_availability(check_in, check_out, guests, "deluxe")
    DB-->>TA: available_rooms=[{id:14,number:"201",...}]
    TA->>DB: get_room_price("deluxe", check_in, check_out)
    DB-->>TA: {base:4500, multiplier:1.0, total:13500, nights:3}

    TA->>SV: tool_results
    SV->>ConvAgent: draft_response(tool_results, lang=en)
    ConvAgent->>LLM: Generate confirmation prompt (with price, dates)
    LLM-->>ConvAgent: "Yes, I found a Deluxe room available… Total: NPR 13,500. Shall I book it?"

    ConvAgent-->>WS: stream tokens
    WS-->>G: {"type":"stream","delta":"Yes, I found..."}

    Note over G,WS: Guest replies: "Yes, book it for me"

    G->>WS: {"type":"message","text":"Yes, book it","lang":"en"}
    WS->>SV: invoke(state with confirmation=true)
    SV->>TA: book_room(guest_name,phone,room_type,dates)
    TA->>DB: BEGIN TRANSACTION; SELECT … FOR UPDATE; INSERT booking
    DB-->>TA: booking_id="BK-2026-0441"
    TA->>NA: dispatch_notification(booking_id)
    NA->>SMS: send_sms(phone, message_en)
    NA->>EmailProvider: send_email(email, body_en)

    TA-->>WS: booking_confirmed
    WS-->>G: {"type":"booking_confirmed","booking_id":"BK-2026-0441",...}
```

---

## 4. LangGraph State Machine

```mermaid
stateDiagram-v2
    [*] --> Supervisor: user message received

    Supervisor --> ConversationAgent: intent=small_talk | FAQ (no tool needed)
    Supervisor --> RAGAgent: intent=FAQ (needs document retrieval)
    Supervisor --> ToolAgent: intent=booking | cancellation | service
    Supervisor --> GuardrailAgent: confidence < threshold OR complaint detected

    RAGAgent --> RAGAgent: retry_retrieval [no chunks above threshold, attempt < 2]
    RAGAgent --> ConversationAgent: chunks_found
    RAGAgent --> GuardrailAgent: no_relevant_chunks after 2 attempts

    ConversationAgent --> WaitForConfirmation: action requires confirmation
    WaitForConfirmation --> ToolAgent: user confirmed
    WaitForConfirmation --> ConversationAgent: user declined / changed mind

    ToolAgent --> ToolAgent: retry_tool [tool_error, attempt < 2]
    ToolAgent --> NotificationAgent: tool_success AND notification_needed
    ToolAgent --> GuardrailAgent: tool_error after 2 retries
    ToolAgent --> ConversationAgent: tool_success, no notification

    NotificationAgent --> ConversationAgent: notification dispatched (async, non-blocking)

    GuardrailAgent --> HumanHandoff: escalation_required
    HumanHandoff --> HumanHandoff: INTERRUPT — waiting for human reply
    HumanHandoff --> ConversationAgent: human_replied

    ConversationAgent --> [*]: response streamed to user
```

---

## 5. LangGraph State Schema

```mermaid
classDiagram
    class ConversationState {
        +session_id: str
        +messages: list~BaseMessage~
        +detected_language: Literal["en","ne","ne_roman"]
        +intent: IntentType
        +confidence_score: float
        +retry_count: int
        +tool_calls: list~ToolCall~
        +tool_results: list~ToolResult~
        +retrieved_chunks: list~RetrievedChunk~
        +awaiting_confirmation: bool
        +confirmed: Optional~bool~
        +booking_draft: Optional~BookingDraft~
        +active_booking_id: Optional~str~
        +escalation_reason: Optional~str~
        +handoff_ticket_id: Optional~str~
        +human_reply: Optional~str~
        +notification_status: NotificationStatus
        +error_log: list~str~
    }

    class ToolCall {
        +name: str
        +arguments: dict
        +attempt: int
    }

    class ToolResult {
        +tool_name: str
        +success: bool
        +data: dict
        +error: Optional~str~
    }

    class RetrievedChunk {
        +document_id: str
        +document_name: str
        +page: int
        +text: str
        +score: float
    }

    class BookingDraft {
        +guest_name: str
        +phone: str
        +email: Optional~str~
        +room_type: str
        +check_in: date
        +check_out: date
        +guests: int
        +total_price_npr: int
        +confirmed: bool
    }

    ConversationState --> ToolCall
    ConversationState --> ToolResult
    ConversationState --> RetrievedChunk
    ConversationState --> BookingDraft
```

---

## 6. RAG Ingestion Pipeline

```mermaid
flowchart LR
    Upload["Admin uploads\nPDF or Markdown"]
    Queue["Ingestion Job\n(BackgroundTasks / Celery)"]
    StatusQueued["Status: queued"]
    Load["Document Loader\n(PyMuPDF for PDF\nmarkdown lib for .md)"]
    StatusProc["Status: processing"]
    Split["Recursive Character Splitter\n• chunk_size=512 tokens\n• overlap=64 tokens\n• Devanagari sentence boundaries"]
    Meta["Metadata enrichment\n(doc_id, page, lang, created_at)"]
    Embed["Multilingual Embedding\n(e.g. paraphrase-multilingual-mpnet-base-v2)"]
    Store["pgvector INSERT with\nHNSW index"]
    StatusDone["Status: indexed"]
    Error["Status: failed\n(log error details)"]

    Upload --> Queue --> StatusQueued --> Load
    Load -->|parse error| Error
    Load --> StatusProc --> Split --> Meta --> Embed --> Store --> StatusDone
    Embed -->|API error| Error
```

---

## 7. Voice Streaming Flow

```mermaid
sequenceDiagram
    participant Browser
    participant FastAPI_WS as FastAPI /ws/voice
    participant STT as STT Provider
    participant Agent as LangGraph Agent
    participant TTS as TTS Provider

    Browser->>FastAPI_WS: WebSocket connect + session token
    loop Audio chunks (16kHz PCM)
        Browser->>FastAPI_WS: binary audio frame
        FastAPI_WS->>STT: stream audio chunk
        STT-->>FastAPI_WS: partial transcript (or silence)
    end
    Browser->>FastAPI_WS: {"type":"end_of_speech"}
    STT-->>FastAPI_WS: final transcript text + lang detected
    FastAPI_WS->>Agent: invoke(text=transcript, lang=detected)
    Agent-->>FastAPI_WS: stream text response tokens
    FastAPI_WS->>TTS: synthesize(text=response, lang=agent_lang)
    TTS-->>FastAPI_WS: audio stream (MP3 or PCM)
    loop Audio response chunks
        FastAPI_WS-->>Browser: binary audio frame
    end
    FastAPI_WS-->>Browser: {"type":"response_text","text":"..."}
```

---

## 8. Notification Flow

```mermaid
flowchart TB
    BookingSuccess["book_room() succeeds\nreturns booking_id"]
    NotifAgent["Notification Agent\n(async, non-blocking)"]
    BuildMsg["Build message\nin guest's language (en/ne)"]
    SMSProvider["SMS Provider Interface"]
    EmailProvider["Email Provider Interface"]
    Retry["Retry once on failure"]
    LogSuccess["Log: notification_sent"]
    LogFail["Log: notification_failed\n(does NOT block user response)"]
    GuestResponse["User sees booking confirmation\nin chat (immediate)"]

    BookingSuccess --> NotifAgent
    BookingSuccess --> GuestResponse
    NotifAgent --> BuildMsg
    BuildMsg --> SMSProvider & EmailProvider
    SMSProvider -->|success| LogSuccess
    SMSProvider -->|fail| Retry --> LogFail
    EmailProvider -->|success| LogSuccess
    EmailProvider -->|fail| Retry --> LogFail
```

---

## 9. Human Handoff Flow

```mermaid
sequenceDiagram
    participant Guest
    participant Agent as LangGraph Agent
    participant Guard as Guardrail Agent
    participant PG as Postgres (checkpoint)
    participant Alert as Handoff Alert Provider
    participant AdminUI as Admin Dashboard
    participant Manager

    Guest->>Agent: "I want to complain about my room"
    Agent->>Guard: score_confidence() → escalation_required=true
    Guard->>PG: save checkpoint (INTERRUPT node)
    Guard->>Alert: send_alert(summary, session_id, lang, booking_id)
    Alert->>Manager: Telegram / Slack message with context

    Note over Agent: ⏸ Automated replies PAUSED

    Agent-->>Guest: "Connecting you to our staff. Please wait."

    Manager->>AdminUI: Opens handoff ticket, reads context
    Manager->>AdminUI: Types reply
    AdminUI->>PG: store human_reply in checkpoint
    AdminUI->>Agent: resume(session_id, human_reply)

    Agent->>PG: load checkpoint, inject human_reply
    Agent-->>Guest: Forward manager's reply (WebSocket push, ≤5s)

    Manager->>AdminUI: Mark ticket resolved
```

---

## 10. Database ER Diagram

```mermaid
erDiagram
    GUESTS {
        uuid id PK
        varchar name
        varchar phone UK
        varchar email
        varchar preferred_language
        timestamp created_at
    }

    ROOM_TYPES {
        varchar id PK
        varchar name
        int capacity
        varchar bed_type
        int base_price_npr
        text amenities
        int floor_count
    }

    ROOMS {
        int id PK
        varchar number UK
        int floor
        varchar room_type_id FK
        varchar status
    }

    BOOKINGS {
        uuid id PK
        uuid guest_id FK
        int room_id FK
        date check_in
        date check_out
        int guests_count
        varchar status
        int total_price_npr
        timestamp created_at
        timestamp updated_at
    }

    RESTAURANT_TABLES {
        int id PK
        varchar name
        int capacity
    }

    TABLE_RESERVATIONS {
        uuid id PK
        int table_id FK
        uuid guest_id FK
        date reservation_date
        time reservation_time
        int party_size
        varchar status
    }

    SERVICES {
        int id PK
        varchar type
        varchar name
        int price_npr
        text description
    }

    SERVICE_REQUESTS {
        uuid id PK
        uuid booking_id FK
        int service_id FK
        text details
        varchar status
        timestamp created_at
    }

    SEASONAL_PRICING {
        int id PK
        varchar name
        date start_date
        date end_date
        decimal multiplier
        varchar room_type_id FK
    }

    DOCUMENTS {
        uuid id PK
        varchar filename
        varchar original_name
        varchar mime_type
        int size_bytes
        varchar status
        text error_message
        int chunk_count
        timestamp uploaded_at
        timestamp indexed_at
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        int chunk_index
        text content
        vector embedding
        jsonb metadata
        int page_number
    }

    CONVERSATIONS {
        uuid id PK
        uuid session_id UK
        uuid guest_id FK
        varchar detected_language
        timestamp started_at
        timestamp last_active_at
        varchar status
    }

    MESSAGES {
        uuid id PK
        uuid conversation_id FK
        varchar role
        text content
        varchar intent
        float confidence
        jsonb tool_calls
        jsonb retrieved_chunks
        timestamp created_at
    }

    HANDOFF_TICKETS {
        uuid id PK
        uuid conversation_id FK
        uuid booking_id FK
        varchar trigger_reason
        text conversation_summary
        varchar guest_language
        varchar status
        text manager_reply
        uuid resolved_by FK
        timestamp created_at
        timestamp resolved_at
    }

    USERS {
        uuid id PK
        varchar email UK
        varchar hashed_password
        varchar role
        bool is_active
        timestamp created_at
    }

    NOTIFICATION_LOG {
        uuid id PK
        uuid booking_id FK
        varchar type
        varchar status
        varchar recipient
        text message
        int attempt_count
        timestamp sent_at
    }

    GUESTS ||--o{ BOOKINGS : makes
    ROOMS ||--o{ BOOKINGS : hosts
    ROOM_TYPES ||--o{ ROOMS : categorises
    ROOM_TYPES ||--o{ SEASONAL_PRICING : has
    GUESTS ||--o{ TABLE_RESERVATIONS : makes
    RESTAURANT_TABLES ||--o{ TABLE_RESERVATIONS : hosts
    BOOKINGS ||--o{ SERVICE_REQUESTS : includes
    SERVICES ||--o{ SERVICE_REQUESTS : fulfils
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : contains
    GUESTS ||--o{ CONVERSATIONS : has
    CONVERSATIONS ||--o{ MESSAGES : contains
    CONVERSATIONS ||--o{ HANDOFF_TICKETS : generates
    BOOKINGS ||--o{ HANDOFF_TICKETS : referenced_in
    BOOKINGS ||--o{ NOTIFICATION_LOG : triggers
    USERS ||--o{ HANDOFF_TICKETS : resolves
```

---

## 11. Deployment Architecture

```mermaid
graph TB
    subgraph Docker["docker-compose (local) / K8s (prod)"]
        subgraph AppServices["Application Services"]
            FastAPI["concierge-api\n(FastAPI, port 8000)\nreplicas: 2+"]
            NextJS["concierge-frontend\n(Next.js, port 3000)"]
            Worker["concierge-worker\n(Celery / ARQ)\noptional, Phase 2"]
        end

        subgraph DataServices["Data Services"]
            Postgres["postgres\n(PostgreSQL 16 + pgvector)\nport 5432"]
            Redis["redis\n(cache + Celery broker)\nport 6379\noptional Phase 2"]
        end

        subgraph Observability["Observability"]
            Loki["loki\n(log aggregation)"]
            Grafana["grafana\n(dashboard)"]
        end
    end

    subgraph External["External (behind provider interfaces)"]
        LLM_Ext["LLM API"]
        SMS_Ext["SMS Gateway"]
        Email_Ext["Email API"]
        TG_Ext["Telegram Bot"]
    end

    Nginx["Nginx / Traefik\n(reverse proxy, TLS termination)"]

    Internet["Internet / Guest Browser"] --> Nginx
    Nginx --> FastAPI
    Nginx --> NextJS
    FastAPI --> Postgres
    FastAPI --> Redis
    FastAPI --> LLM_Ext
    FastAPI --> SMS_Ext
    FastAPI --> Email_Ext
    FastAPI --> TG_Ext
    Worker --> Postgres
    Worker --> Redis
    FastAPI --> Loki
    Worker --> Loki
    Loki --> Grafana
```

---

## 12. Full Folder Structure

```
hotel-concierge/
├── .env.example                        # All required environment variable names with placeholders
├── .env                                # Local secrets (git-ignored)
├── docker-compose.yml                  # Postgres, pgvector, app, frontend, optional Redis
├── Makefile                            # Shortcuts: make dev, make test, make migrate, make seed
├── README.md                           # Quick-start guide
│
├── docs/                               # All documentation (this folder)
│   ├── prd.md
│   ├── architecture.md
│   ├── rules.md
│   ├── design.md
│   ├── tasks.md
│   └── memory.md
│
├── docs/steering/
│       ├── tech-stack.md               # Tech stack and version pins
│       ├── coding-standards.md         # rules.md mirrored for AI coding sessions
│       └── folder-structure.md         # Folder map mirrored for AI coding sessions
│
├── backend/
│   ├── pyproject.toml                  # Project metadata, deps, ruff/mypy config
│   ├── alembic.ini                     # Alembic migration config
│   ├── alembic/
│   │   ├── env.py                      # Async-aware Alembic env
│   │   └── versions/                   # Migration files (auto-generated)
│   │
│   ├── app/
│   │   ├── main.py                     # FastAPI app factory, middleware registration
│   │   ├── config.py                   # Pydantic Settings, reads .env
│   │   ├── dependencies.py             # FastAPI Depends: DB session, current user
│   │   ├── exceptions.py               # Custom exception classes (AppError hierarchy)
│   │   ├── middleware/
│   │   │   ├── logging.py              # Request ID injection, structured JSON logging
│   │   │   ├── error_handler.py        # Global exception → JSON response mapper
│   │   │   └── rate_limit.py           # Sliding-window rate limiter (in-memory or Redis)
│   │   │
│   │   ├── db/
│   │   │   ├── base.py                 # SQLAlchemy async engine, session factory
│   │   │   ├── models/
│   │   │   │   ├── guest.py            # Guest ORM model
│   │   │   │   ├── room.py             # Room + RoomType ORM models
│   │   │   │   ├── booking.py          # Booking ORM model
│   │   │   │   ├── service.py          # Service + ServiceRequest ORM models
│   │   │   │   ├── restaurant.py       # RestaurantTable + TableReservation
│   │   │   │   ├── seasonal_pricing.py # SeasonalPricing ORM model
│   │   │   │   ├── document.py         # Document + DocumentChunk ORM models
│   │   │   │   ├── conversation.py     # Conversation + Message ORM models
│   │   │   │   ├── handoff.py          # HandoffTicket ORM model
│   │   │   │   ├── user.py             # User (admin/staff) ORM model
│   │   │   │   └── notification.py     # NotificationLog ORM model
│   │   │   └── repositories/
│   │   │       ├── booking_repo.py     # Async DB operations for bookings
│   │   │       ├── room_repo.py        # Room availability queries
│   │   │       ├── guest_repo.py       # Guest CRUD
│   │   │       ├── document_repo.py    # Document ingestion status updates
│   │   │       └── handoff_repo.py     # Handoff ticket CRUD
│   │   │
│   │   ├── auth/
│   │   │   ├── jwt.py                  # Token creation, verification, refresh
│   │   │   ├── password.py             # Bcrypt hashing
│   │   │   └── schemas.py              # LoginRequest, TokenResponse Pydantic schemas
│   │   │
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── router.py           # Aggregates all v1 routers
│   │   │   │   ├── auth.py             # POST /auth/login, /auth/refresh, /auth/logout
│   │   │   │   ├── documents.py        # POST /documents, GET /documents, DELETE /documents/{id}
│   │   │   │   ├── bookings.py         # GET /bookings (admin), GET /bookings/{id}
│   │   │   │   ├── conversations.py    # GET /conversations, GET /conversations/{id}
│   │   │   │   ├── handoffs.py         # GET /handoffs, POST /handoffs/{id}/reply, PATCH /handoffs/{id}/resolve
│   │   │   │   └── health.py           # GET /health
│   │   │   └── ws/
│   │   │       ├── chat.py             # WebSocket /ws/chat/{session_id}
│   │   │       └── voice.py            # WebSocket /ws/voice/{session_id}
│   │   │
│   │   ├── agents/
│   │   │   ├── state.py                # ConversationState TypedDict + all sub-schemas
│   │   │   ├── graph.py                # LangGraph graph construction, edge definitions
│   │   │   ├── supervisor.py           # Supervisor/Router node
│   │   │   ├── conversation.py         # Conversation Agent node
│   │   │   ├── rag_agent.py            # RAG Agent node (retrieval + draft)
│   │   │   ├── tool_agent.py           # Tool Agent node (validate + call tools)
│   │   │   ├── notification_agent.py   # Notification Agent node
│   │   │   ├── guardrail_agent.py      # Guardrail / Handoff Agent node
│   │   │   └── checkpointer.py         # Postgres checkpointer setup
│   │   │
│   │   ├── tools/
│   │   │   ├── schemas.py              # Pydantic input/output schemas for all tools
│   │   │   ├── room_tools.py           # check_room_availability, get_room_price
│   │   │   ├── booking_tools.py        # book_room, cancel_booking, modify_booking, get_booking_status
│   │   │   ├── restaurant_tools.py     # reserve_restaurant_table
│   │   │   └── service_tools.py        # request_service
│   │   │
│   │   ├── rag/
│   │   │   ├── ingestion.py            # Orchestrates load → split → embed → store
│   │   │   ├── loaders.py              # PDF loader (PyMuPDF), Markdown loader
│   │   │   ├── splitter.py             # Devanagari-aware recursive splitter
│   │   │   ├── embedder.py             # Embedding provider interface + implementations
│   │   │   ├── vector_store.py         # pgvector insert, similarity search
│   │   │   └── retriever.py            # top-k retrieval + optional reranking
│   │   │
│   │   ├── notifications/
│   │   │   ├── base.py                 # Abstract SMSProvider, EmailProvider
│   │   │   ├── mock_sms.py             # Mock SMS (logs to stdout/file)
│   │   │   ├── mock_email.py           # Mock email (logs to stdout/file)
│   │   │   ├── sparrow_sms.py          # Sparrow SMS gateway implementation
│   │   │   └── smtp_email.py           # SMTP email implementation
│   │   │
│   │   ├── handoff/
│   │   │   ├── base.py                 # Abstract HandoffAlertProvider
│   │   │   ├── telegram_provider.py    # Telegram Bot alert implementation
│   │   │   └── slack_provider.py       # Slack Webhook alert implementation
│   │   │
│   │   ├── voice/
│   │   │   ├── base.py                 # Abstract STTProvider, TTSProvider
│   │   │   ├── whisper_stt.py          # OpenAI Whisper STT implementation
│   │   │   ├── google_stt.py           # Google Cloud STT implementation
│   │   │   └── google_tts.py           # Google Cloud TTS implementation
│   │   │
│   │   └── utils/
│   │       ├── bikram_sambat.py        # BS↔Gregorian conversion utility
│   │       ├── language_detection.py   # Detect en / ne / ne_roman
│   │       ├── currency.py             # NPR formatting helpers
│   │       ├── date_utils.py           # Gregorian date parsing, Nepali month names
│   │       └── logger.py               # Structlog / stdlib JSON logger factory
│   │
│   ├── scripts/
│   │   ├── seed_db.py                  # Seeds all tables with realistic Nepal data
│   │   └── generate_sample_docs.py     # Generates sample hotel PDF/Markdown KB docs
│   │
│   └── tests/
│       ├── conftest.py                 # Pytest fixtures: async DB session, test client, mock providers
│       ├── unit/
│       │   ├── test_bikram_sambat.py   # All 12 months, leap years, edge cases
│       │   ├── test_language_detection.py
│       │   ├── test_seasonal_pricing.py
│       │   ├── test_booking_tools.py   # Tool input validation
│       │   └── test_rag_splitter.py    # Devanagari split correctness
│       ├── integration/
│       │   ├── test_booking_flow.py    # Full booking E2E against test DB
│       │   ├── test_rag_retrieval.py   # Ingestion + retrieval pipeline
│       │   ├── test_handoff.py         # Handoff trigger + interrupt + resume
│       │   └── test_auth.py            # JWT login, refresh, protected routes
│       └── eval/
│           ├── golden_qa_en.json       # 20 English Q&A pairs for RAG eval
│           ├── golden_qa_ne.json       # 20 Nepali Q&A pairs for RAG eval
│           └── run_eval.py             # RAGAS evaluation runner
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json                   # Strict TypeScript
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   ├── public/
│   │   └── fonts/                      # Devanagari-supporting font (Tiro Devanagari)
│   │
│   └── src/
│       ├── app/
│       │   ├── layout.tsx              # Root layout, font loading, global styles
│       │   ├── page.tsx                # Redirects to /chat
│       │   ├── chat/
│       │   │   └── page.tsx            # Customer chat page
│       │   └── admin/
│       │       ├── layout.tsx          # Admin layout with nav sidebar
│       │       ├── page.tsx            # Admin home → redirect to /admin/handoffs
│       │       ├── login/
│       │       │   └── page.tsx        # JWT login form
│       │       ├── documents/
│       │       │   └── page.tsx        # Document upload + status list
│       │       ├── handoffs/
│       │       │   └── page.tsx        # Handoff inbox + reply interface
│       │       ├── bookings/
│       │       │   └── page.tsx        # Bookings list with filters
│       │       └── conversations/
│       │           └── page.tsx        # Conversation history viewer
│       │
│       ├── components/
│       │   ├── chat/
│       │   │   ├── ChatWindow.tsx      # Main chat container, WebSocket manager
│       │   │   ├── MessageList.tsx     # Renders messages with citation badges
│       │   │   ├── MessageBubble.tsx   # Single message (user/assistant/human-agent)
│       │   │   ├── InputBar.tsx        # Text input + mic button + lang toggle
│       │   │   ├── VoiceCapture.tsx    # MediaRecorder, WebAudio, PCM streaming
│       │   │   ├── CitationBadge.tsx   # Inline source citation pill
│       │   │   └── HumanHandoffBanner.tsx  # "Connected to staff" status bar
│       │   ├── admin/
│       │   │   ├── DocumentUpload.tsx  # Drag-drop upload with progress bar
│       │   │   ├── DocumentList.tsx    # Table of docs with status badges
│       │   │   ├── HandoffTicket.tsx   # Single ticket card with reply form
│       │   │   ├── BookingTable.tsx    # Filterable bookings data grid
│       │   │   └── ConversationViewer.tsx  # Message-by-message conversation viewer
│       │   └── shared/
│       │       ├── Navbar.tsx
│       │       ├── Sidebar.tsx
│       │       ├── StatusBadge.tsx     # Reusable color-coded status badge
│       │       ├── LoadingSpinner.tsx
│       │       └── ErrorBoundary.tsx
│       │
│       ├── hooks/
│       │   ├── useWebSocket.ts         # Generic WebSocket hook with reconnect logic
│       │   ├── useVoice.ts             # MediaRecorder lifecycle, PCM chunking
│       │   ├── useChat.ts              # Chat state, message list, streaming buffer
│       │   └── useAuth.ts             # JWT login, refresh, logout, role guard
│       │
│       ├── lib/
│       │   ├── api.ts                  # Typed fetch wrapper for backend REST API
│       │   ├── ws-protocol.ts          # TypeScript types for WebSocket message protocol
│       │   └── i18n.ts                 # en/ne string maps, language switcher helper
│       │
│       └── types/
│           ├── chat.ts                 # ChatMessage, Citation, HandoffState types
│           ├── booking.ts              # Booking, RoomType, Guest types
│           └── admin.ts                # Document, HandoffTicket, User types
│
└── knowledge_base/
    ├── en/
    │   ├── hotel_policies.md           # Check-in/out, cancellation, ID, child/pet policy
    │   ├── room_descriptions.md        # All room types with amenities
    │   ├── restaurant_menu.md          # Full menu with NPR prices
    │   ├── nearby_attractions.md       # Directions to Koshi Tappu, Dharan, etc.
    │   ├── transfer_info.md            # Airport/bus-park pickup info
    │   ├── festival_packages.md        # Dashain/Tihar/Chhath packages
    │   ├── payment_methods.md          # Cash, eSewa, Khalti, bank transfer
    │   └── faq.md                      # Frequently asked questions
    └── ne/
        ├── hotel_policies_ne.md        # Same content in Nepali (Devanagari)
        ├── room_descriptions_ne.md
        ├── restaurant_menu_ne.md
        └── faq_ne.md
```
