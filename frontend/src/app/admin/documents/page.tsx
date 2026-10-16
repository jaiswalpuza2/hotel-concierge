"use client";

import { useRef, useState } from "react";
import type { DragEvent } from "react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { DocumentItem, Page } from "@/lib/types";

const ACCEPT = ".pdf,.md,.markdown,.txt";

export default function DocumentsPage() {
  const { user } = useAuth();
  const [language, setLanguage] = useState<"en" | "ne">("en");
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const { data, error, reload } = usePolling(() => api<Page<DocumentItem>>("/api/v1/documents?page_size=100"), 3000);

  const upload = async (files: FileList | File[]) => {
    setNotice(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        form.append("language", language);
        await api("/api/v1/documents", { method: "POST", body: form });
      }
      setNotice({ kind: "ok", text: "Uploaded. Indexing runs in the background; the status updates below." });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) void upload(event.dataTransfer.files);
  };

  const remove = async (doc: DocumentItem) => {
    if (!window.confirm(`Delete "${doc.original_name}" and its indexed content?`)) return;
    try {
      await api(`/api/v1/documents/${doc.id}`, { method: "DELETE" });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Delete failed" });
    }
  };

  const indexSample = async () => {
    try {
      await api("/api/v1/documents/ingest-sample-kb", { method: "POST" });
      setNotice({ kind: "ok", text: "Indexing the sample hotel documents (English and Nepali)…" });
      await reload();
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Could not start indexing" });
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="anim-fade-up text-2xl font-semibold">Knowledge base</h1>
          <p className="anim-fade-up d1 mt-1 text-sm text-stone-500">Upload PDFs or Markdown files. The concierge answers from them and cites the source.</p>
        </div>
        {user?.role === "admin" && (
          <Button variant="secondary" onClick={() => void indexSample()}>
            Index sample documents
          </Button>
        )}
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`anim-fade-up d2 mt-6 rounded-2xl border-2 border-dashed p-8 text-center transition-all duration-200 ${
          dragging ? "scale-[1.01] border-brand bg-brand-soft shadow-inner" : "border-stone-300 bg-white hover:border-stone-400"
        }`}
      >
        <p className="text-stone-700">Drag files here, or</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          id="file-input"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) void upload(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="mt-3 flex items-center justify-center gap-3">
          <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? "Uploading…" : "Choose files"}
          </Button>
          <label className="text-sm text-stone-600">
            Language{" "}
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as "en" | "ne")}
              className="rounded-lg border border-stone-300 bg-white px-2 py-1"
            >
              <option value="en">English</option>
              <option value="ne">नेपाली</option>
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-stone-500">PDF, Markdown or text · up to 20 MB each</p>
      </div>

      {notice && (
        <p
          role={notice.kind === "error" ? "alert" : "status"}
          className={`anim-slide-down mt-4 rounded-lg px-3 py-2 text-sm ${notice.kind === "error" ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"}`}
        >
          {notice.text}
        </p>
      )}
      {error && <p role="alert" className="anim-shake mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="mt-6 overflow-x-auto rounded-2xl border border-stone-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Chunks</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-stone-500">
                  No documents yet.
                </td>
              </tr>
            )}
            {data?.items.map((doc, i) => (
              <tr key={doc.id} className="anim-fade-up border-b border-stone-100 transition-colors duration-150 last:border-0 hover:bg-stone-50" style={{ animationDelay: `${Math.min(i * 40, 320)}ms` }}>
                <td className="px-4 py-3 font-medium">
                  {doc.original_name}
                  {doc.error_message && <p className="mt-1 text-xs font-normal text-red-600">{doc.error_message}</p>}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.status} />
                </td>
                <td className="px-4 py-3 tabular-nums">{doc.chunk_count}</td>
                <td className="px-4 py-3 tabular-nums">{formatBytes(doc.size_bytes)}</td>
                <td className="px-4 py-3 text-stone-500">{formatDateTime(doc.uploaded_at)}</td>
                <td className="px-4 py-3 text-right">
                  <Button variant="ghost" className="px-2 py-1 text-xs text-red-600" onClick={() => void remove(doc)}>
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
