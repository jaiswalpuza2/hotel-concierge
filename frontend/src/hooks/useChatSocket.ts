"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { WS_URL } from "@/lib/config";
import type { Capabilities, ChatMessage, Citation, Language } from "@/lib/types";

export type ConnectionState = "connecting" | "open" | "closed";

interface ServerReply {
  text: string;
  citations: Citation[];
  handoff_active: boolean;
}

type ServerEvent =
  | { type: "ready"; session_id: string; voice_input: boolean; voice_output: boolean }
  | { type: "status"; stage: string }
  | { type: "transcript"; text: string }
  | { type: "message_chunk"; text: string }
  | { type: "message_end"; reply: ServerReply }
  | { type: "audio"; mime: string; data: string }
  | { type: "human_message"; text: string; ticket_ref: string }
  | { type: "handoff_resolved"; text: string }
  | { type: "error"; code: string; message: string }
  | { type: "pong" };

interface HistoryResponse {
  messages: { role: string; content: string }[];
  handoff_active: boolean;
}

interface Options {
  sessionId: string;
  language: Language;
  /** Called when the server sends synthesised speech. */
  onAudio?: (base64: string) => void;
}

const newId = (): string => crypto.randomUUID();

/** Real-time chat over WebSocket with auto-reconnect, streaming text, voice upload and handoff state. */
export function useChatSocket({ sessionId, language, onAudio }: Options) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [stage, setStage] = useState<string | null>(null);
  const [handoffActive, setHandoffActive] = useState(false);
  const [capabilities, setCapabilities] = useState<Pick<Capabilities, "voice_input" | "voice_output">>({
    voice_input: false,
    voice_output: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const closedByUs = useRef(false);
  const awaitingPong = useRef(false);
  const streamingId = useRef<string | null>(null);
  const onAudioRef = useRef(onAudio);
  onAudioRef.current = onAudio;
  const languageRef = useRef(language);
  languageRef.current = language;

  // Restore earlier messages when the page is reopened.
  useEffect(() => {
    let cancelled = false;
    void api<HistoryResponse>(`/api/v1/chat/history/${sessionId}`, { auth: false })
      .then((history) => {
        if (cancelled) return;
        setMessages(
          history.messages.map((m) => ({
            id: newId(),
            role: m.role === "user" ? "user" : m.role === "human_agent" ? "human" : "assistant",
            text: m.content,
          })),
        );
        setHandoffActive(history.handoff_active);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const handleEvent = useCallback((event: ServerEvent) => {
    switch (event.type) {
      case "ready":
        setCapabilities({ voice_input: event.voice_input, voice_output: event.voice_output });
        break;
      case "status":
        setStage(event.stage);
        break;
      case "transcript":
        setMessages((prev) => {
          const idx = [...prev].reverse().findIndex((m) => m.role === "user" && m.viaVoice && m.text === "");
          if (idx === -1) return prev;
          const realIdx = prev.length - 1 - idx;
          return prev.map((m, i) => (i === realIdx ? { ...m, text: event.text } : m));
        });
        break;
      case "message_chunk": {
        // Pure updater: StrictMode double-invocation in dev must not mutate
        // refs or create ids inside it, or the second run discards the append.
        const chunk = event.text;
        let chunkId = streamingId.current;
        if (!chunkId) {
          chunkId = newId();
          streamingId.current = chunkId;
        }
        setStage(null);
        setMessages((prev) =>
          prev.some((m) => m.id === chunkId)
            ? prev.map((m) => (m.id === chunkId ? { ...m, text: m.text + chunk } : m))
            : [...prev, { id: chunkId, role: "assistant" as const, text: chunk, streaming: true }],
        );
        break;
      }
      case "message_end": {
        const id = streamingId.current;
        streamingId.current = null;
        setStage(null);
        setBusy(false);
        setHandoffActive(event.reply.handoff_active);
        setMessages((prev) =>
          id
            ? prev.map((m) =>
                m.id === id ? { ...m, text: event.reply.text, citations: event.reply.citations, streaming: false } : m,
              )
            : [...prev, { id: newId(), role: "assistant", text: event.reply.text, citations: event.reply.citations }],
        );
        break;
      }
      case "audio":
        onAudioRef.current?.(event.data);
        break;
      case "human_message":
        setHandoffActive(true);
        setMessages((prev) => [...prev, { id: newId(), role: "human", text: event.text }]);
        break;
      case "handoff_resolved":
        setHandoffActive(false);
        setMessages((prev) => [...prev, { id: newId(), role: "assistant", text: event.text }]);
        break;
      case "error":
        streamingId.current = null;
        setStage(null);
        setBusy(false);
        setError(event.message);
        break;
      case "pong":
        break;
    }
  }, []);

  const connect = useCallback(() => {
    setConnection("connecting");
    const socket = new WebSocket(`${WS_URL}/ws/chat?session_id=${sessionId}`);
    socketRef.current = socket;

    socket.onopen = () => {
      retryRef.current = 0;
      setConnection("open");
      setError(null);
    };
    socket.onmessage = (message: MessageEvent<string>) => {
      awaitingPong.current = false;
      try {
        handleEvent(JSON.parse(message.data) as ServerEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onclose = () => {
      setConnection("closed");
      setBusy(false);
      if (closedByUs.current) return;
      const delay = Math.min(15000, 1000 * 2 ** retryRef.current);
      retryRef.current += 1;
      timerRef.current = window.setTimeout(connect, delay);
    };
    socket.onerror = () => socket.close();
  }, [handleEvent, sessionId]);

  useEffect(() => {
    closedByUs.current = false;
    connect();
    const keepAlive = window.setInterval(() => {
      const socket = socketRef.current;
      if (socket?.readyState !== WebSocket.OPEN) return;
      // If the previous ping went unanswered the socket is half-open (dropped
      // by a proxy without notifying us) — close it so onclose reconnects.
      if (awaitingPong.current) {
        socket.close();
        return;
      }
      awaitingPong.current = true;
      socket.send(JSON.stringify({ type: "ping" }));
    }, 20000);
    return () => {
      closedByUs.current = true;
      window.clearInterval(keepAlive);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        // Detach handlers first: a closing socket must not schedule a
        // reconnect belonging to a previous mount.
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };
  }, [connect]);

  const sendText = useCallback((text: string, speak: boolean): boolean => {
    const socket = socketRef.current;
    const clean = text.trim();
    if (!clean || !socket || socket.readyState !== WebSocket.OPEN) return false;
    setMessages((prev) => [...prev, { id: newId(), role: "user", text: clean }]);
    setBusy(true);
    setError(null);
    socket.send(JSON.stringify({ type: "message", text: clean, language: languageRef.current, speak }));
    return true;
  }, []);

  /** Begin a streamed voice message; follow with ``sendAudioChunk`` calls and ``endAudio``. */
  const beginAudio = useCallback((mime: string, speak: boolean): boolean => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "audio_start", mime, language: languageRef.current, speak }));
    return true;
  }, []);

  const sendAudioChunk = useCallback((chunk: Blob) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(chunk);
  }, []);

  const endAudio = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [...prev, { id: newId(), role: "user", text: "", viaVoice: true }]);
    setBusy(true);
    socket.send(JSON.stringify({ type: "audio_end" }));
  }, []);

  return {
    messages,
    connection,
    stage,
    handoffActive,
    capabilities,
    error,
    busy,
    sendText,
    beginAudio,
    sendAudioChunk,
    endAudio,
    clearError: () => setError(null),
  };
}
