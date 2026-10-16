---
inclusion: always
---

# Folder Structure Reference
## Autonomous Multi-Agent Local Business Concierge

This file is auto-included in every Kiro session. When creating new files, always place them in the correct location per this map. Never create files outside this structure without updating this file and `docs/memory.md`.

```
hotel-concierge/
├── .env.example                        # All env variable names with placeholder values
├── .env                                # Local secrets (git-ignored, never committed)
├── docker-compose.yml                  # Services: postgres, api, frontend, (redis optional)
├── Makefile                            # Targets: dev, test, migrate, seed, lint, typecheck, ci
├── README.md                           # Quick-start guide
│
├── docs/                               # All design and planning documentation
│   ├── prd.md                          # Product requirements
│   ├── architecture.md                 # Diagrams and folder map
│   ├── rules.md                        # Coding standards
│   ├── design.md                       # DB schema, API contracts, prompts, WS protocol
│   ├── tasks.md                        # Phased task checklist
│   └── memory.md                       # Living project memory (update after every task)
│
├── .kiro/
│   └── steering/
│       ├── tech-stack.md               # Pinned versions (auto-included)
│       ├── coding-standards.md         # Rules for every Kiro session (auto-included)
│       └── folder-structure.md         # This file (auto-included)
│
├── backend/
│   ├── pyproject.toml                  # Deps, ruff config, mypy config, pytest config
│   ├── alembic.ini                     # Alembic config pointing to DB_URL
│   ├── alembic/
│   │   ├── env.py                      # Async-aware Alembic environment
│   │   └── versions/                   # Auto-generated migration files
│   │
│   ├── app/
│   │   ├── main.py                     # FastAPI app factory; registers middleware and routers
│   │   ├── config.py                   # Pydantic Settings; reads .env; cached get_settings()
│   │   ├── dependencies.py             # FastAPI Depends: get_db_session, get_current_user
│   │   ├── exceptions.py               # AppError hierarchy (ValidationError, NotFoundError, etc.)
│   │   │
│   │   ├── middleware/
│   │   │   ├── logging.py              # Request ID injection, structlog JSON output
│   │   │   ├── error_handler.py        # AppError → HTTP JSON response; hides stack traces
│   │   │   └── rate_limit.py           # Sliding-window 60 req/min per IP
│   │   │
│   │   ├── db/
│   │   │   ├── base.py                 # AsyncEngine, async_session_factory, Base declarative
│   │   │   ├── models/
│   │   │   │   ├── guest.py            # Guest ORM model
│   │   │   │   ├── room.py             # Room + RoomType ORM models
│   │   │   │   ├── booking.py          # Booking ORM model
│   │   │   │   ├── service.py          # Service + ServiceRequest ORM models
│   │   │   │   ├── restaurant.py       # RestaurantTable + TableReservation ORM models
│   │   │   │   ├── seasonal_pricing.py # SeasonalPricing ORM model
│   │   │   │   ├── document.py         # Document + DocumentChunk ORM models
│   │   │   │   ├── conversation.py     # Conversation + Message ORM models
│   │   │   │   ├── handoff.py          # HandoffTicket ORM model
│   │   │   │   ├── user.py             # User (admin/staff) ORM model
│   │   │   │   └── notification.py     # NotificationLog ORM model
│   │   │   └── repositories/
│   │   │       ├── booking_repo.py     # Booking CRUD + availability query
│   │   │       ├── room_repo.py        # Room availability + pricing queries
│   │   │       ├── guest_repo.py       # Guest get-or-create, lookup
│   │   │       ├── document_repo.py    # Document status updates, chunk management
│   │   │       └── handoff_repo.py     # Handoff ticket CRUD
│   │   │
│   │   ├── auth/
│   │   │   ├── jwt.py                  # create_access_token, decode_access_token, refresh logic
│   │   │   ├── password.py             # hash_password, verify_password (bcrypt)
│   │   │   └── schemas.py              # LoginRequest, TokenResponse Pydantic schemas
│   │   │
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── router.py           # Aggregates all v1 API routers
│   │   │   │   ├── auth.py             # POST /auth/login, /auth/refresh, /auth/logout
│   │   │   │   ├── documents.py        # POST /documents, GET /documents, DELETE /documents/{id}
│   │   │   │   ├── bookings.py         # GET /bookings, GET /bookings/{id}
│   │   │   │   ├── conversations.py    # GET /conversations, GET /conversations/{id}/messages
│   │   │   │   ├── handoffs.py         # GET /handoffs, POST /reply, PATCH /resolve
│   │   │   │   └── health.py           # GET /health
│   │   │   └── ws/
│   │   │       ├── chat.py             # WebSocket /ws/chat/{session_id}
│   │   │       └── voice.py            # WebSocket /ws/voice/{session_id}
│   │   │
│   │   ├── agents/
│   │   │   ├── state.py                # ConversationState TypedDict + all sub-schemas
│   │   │   ├── graph.py                # LangGraph graph compilation, all edges
│   │   │   ├── supervisor.py           # route_intent node
│   │   │   ├── conversation.py         # draft_response node
│   │   │   ├── rag_agent.py            # retrieve_chunks node
│   │   │   ├── tool_agent.py           # call_tools node
│   │   │   ├── notification_agent.py   # send_notifications node
│   │   │   ├── guardrail_agent.py      # evaluate_handoff, create_handoff_ticket nodes
│   │   │   └── checkpointer.py         # Postgres checkpointer factory
│   │   │
│   │   ├── tools/
│   │   │   ├── schemas.py              # Pydantic input/output schemas for all 8 tools
│   │   │   ├── room_tools.py           # check_room_availability, get_room_price
│   │   │   ├── booking_tools.py        # book_room, cancel_booking, modify_booking, get_booking_status
│   │   │   ├── restaurant_tools.py     # reserve_restaurant_table
│   │   │   └── service_tools.py        # request_service
│   │   │
│   │   ├── rag/
│   │   │   ├── ingestion.py            # Orchestrator: load → split → embed → store
│   │   │   ├── loaders.py              # PDFLoader, MarkdownLoader
│   │   │   ├── splitter.py             # DevanagariAwareSplitter
│   │   │   ├── embedder.py             # EmbeddingProvider interface + implementations
│   │   │   ├── vector_store.py         # pgvector insert + cosine similarity search
│   │   │   └── retriever.py            # top-k retrieval + optional reranking
│   │   │
│   │   ├── notifications/
│   │   │   ├── base.py                 # SMSProvider, EmailProvider abstract classes
│   │   │   ├── mock_sms.py             # Mock SMS (logs to tmp/mock_sms.log)
│   │   │   ├── mock_email.py           # Mock email (logs to tmp/mock_email.log)
│   │   │   ├── sparrow_sms.py          # Sparrow SMS gateway implementation
│   │   │   └── smtp_email.py           # SMTP email implementation
│   │   │
│   │   ├── handoff/
│   │   │   ├── base.py                 # HandoffAlertProvider abstract class
│   │   │   ├── telegram_provider.py    # Telegram Bot API alert
│   │   │   └── slack_provider.py       # Slack Incoming Webhook alert
│   │   │
│   │   ├── voice/
│   │   │   ├── base.py                 # STTProvider, TTSProvider abstract classes
│   │   │   ├── whisper_stt.py          # OpenAI Whisper STT implementation
│   │   │   ├── google_stt.py           # Google Cloud STT implementation
│   │   │   └── google_tts.py           # Google Cloud TTS implementation
│   │   │
│   │   └── utils/
│   │       ├── bikram_sambat.py        # BS↔Gregorian conversion; range 2070–2090 BS
│   │       ├── language_detection.py   # detect_language() → "en" | "ne" | "ne_roman"
│   │       ├── currency.py             # NPR formatting (रू 1,20,000 style)
│   │       ├── date_utils.py           # Gregorian date parsing, Nepali month names
│   │       └── logger.py               # Structlog JSON logger factory
│   │
│   ├── scripts/
│   │   ├── seed_db.py                  # Seeds all DB tables with realistic Nepal hotel data
│   │   └── generate_sample_docs.py     # Generates knowledge base Markdown files
│   │
│   └── tests/
│       ├── conftest.py                 # Fixtures: async DB session, test client, mock providers
│       ├── unit/
│       │   ├── test_bikram_sambat.py
│       │   ├── test_language_detection.py
│       │   ├── test_seasonal_pricing.py
│       │   ├── test_booking_tools.py
│       │   ├── test_rag_splitter.py
│       │   ├── test_tool_schemas.py
│       │   ├── test_auth.py
│       │   ├── test_error_handling.py
│       │   ├── test_rate_limit.py
│       │   ├── test_notification_providers.py
│       │   ├── test_notification_templates.py
│       │   ├── test_agent_nodes.py
│       │   ├── test_voice_providers.py
│       │   └── test_date_parsing.py
│       ├── integration/
│       │   ├── test_repositories.py
│       │   ├── test_auth.py
│       │   ├── test_booking_flow.py
│       │   ├── test_rag_retrieval.py
│       │   ├── test_documents_api.py
│       │   ├── test_graph_flow.py
│       │   ├── test_checkpointer.py
│       │   ├── test_golden_conversations.py
│       │   ├── test_handoff.py
│       │   ├── test_notification_agent.py
│       │   ├── test_chat_websocket.py
│       │   ├── test_voice_websocket.py
│       │   └── test_concurrent_booking.py
│       └── eval/
│           ├── golden_qa_en.json       # 20 English Q&A pairs for RAGAS evaluation
│           ├── golden_qa_ne.json       # 20 Nepali Q&A pairs for RAGAS evaluation
│           └── run_eval.py             # RAGAS evaluation runner (manual, not in CI)
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json                   # strict: true
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   ├── public/
│   │   └── fonts/                      # Devanagari font files
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx                # Redirects to /chat
│       │   ├── chat/page.tsx
│       │   └── admin/
│       │       ├── layout.tsx
│       │       ├── page.tsx
│       │       ├── login/page.tsx
│       │       ├── documents/page.tsx
│       │       ├── handoffs/page.tsx
│       │       ├── bookings/page.tsx
│       │       └── conversations/page.tsx
│       ├── components/
│       │   ├── chat/
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── MessageList.tsx
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── InputBar.tsx
│       │   │   ├── VoiceCapture.tsx
│       │   │   ├── CitationBadge.tsx
│       │   │   └── HumanHandoffBanner.tsx
│       │   ├── admin/
│       │   │   ├── DocumentUpload.tsx
│       │   │   ├── DocumentList.tsx
│       │   │   ├── HandoffTicket.tsx
│       │   │   ├── BookingTable.tsx
│       │   │   └── ConversationViewer.tsx
│       │   └── shared/
│       │       ├── Navbar.tsx
│       │       ├── Sidebar.tsx
│       │       ├── StatusBadge.tsx
│       │       ├── LoadingSpinner.tsx
│       │       └── ErrorBoundary.tsx
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   ├── useVoice.ts
│       │   ├── useChat.ts
│       │   └── useAuth.ts
│       ├── lib/
│       │   ├── api.ts
│       │   ├── ws-protocol.ts
│       │   └── i18n.ts
│       └── types/
│           ├── chat.ts
│           ├── booking.ts
│           └── admin.ts
│
└── knowledge_base/
    ├── en/
    │   ├── hotel_policies.md
    │   ├── room_descriptions.md
    │   ├── restaurant_menu.md
    │   ├── nearby_attractions.md
    │   ├── transfer_info.md
    │   ├── festival_packages.md
    │   ├── payment_methods.md
    │   └── faq.md
    └── ne/
        ├── hotel_policies_ne.md
        ├── room_descriptions_ne.md
        ├── restaurant_menu_ne.md
        └── faq_ne.md
```
