export type Language = "en" | "ne";

export interface Citation {
  document_name: string;
  section?: string | null;
  page?: number | null;
  score?: number;
}

export type ChatRole = "user" | "assistant" | "human";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  citations?: Citation[];
  streaming?: boolean;
  viaVoice?: boolean;
}

export interface Capabilities {
  business_name: string;
  voice_input: boolean;
  voice_output: boolean;
  languages: Language[];
  max_message_chars: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentItem {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  status: "queued" | "processing" | "indexed" | "failed";
  chunk_count: number;
  error_message: string | null;
  uploaded_at: string;
  indexed_at: string | null;
}

export interface Ticket {
  id: string;
  ref: string;
  status: "open" | "in_progress" | "resolved";
  reason: string;
  guest_language: Language;
  summary: string;
  manager_reply: string | null;
  conversation_id: string;
  created_at: string;
  resolved_at: string | null;
}

export interface TicketDetail extends Ticket {
  messages: { role: string; content: string; created_at: string }[];
}

export interface BookingItem {
  id: string;
  reference: string;
  status: string;
  guest_name: string;
  guest_phone: string;
  guest_email: string | null;
  room_number: string;
  room_type: string;
  check_in: string;
  check_out: string;
  guests_count: number;
  total_price_npr: number;
  created_at: string;
}

export interface ConversationItem {
  id: string;
  session_id: string;
  status: string;
  language: string;
  last_active_at: string;
}

export interface ConversationDetail {
  id: string;
  session_id: string;
  status: string;
  language: string;
  messages: {
    role: string;
    content: string;
    intent: string | null;
    confidence: number | null;
    tool_calls: { name: string; ok: boolean; error_code?: string | null }[];
    sources: Citation[];
    created_at: string;
  }[];
}

export interface Stats {
  open_handoffs: number;
  in_progress_handoffs: number;
  upcoming_bookings: number;
  arrivals_today: number;
  documents_indexed: number;
  documents_failed: number;
}
