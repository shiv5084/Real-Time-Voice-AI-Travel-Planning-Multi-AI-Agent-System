"use client";

import { useEffect, useRef, useState } from "react";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ChatInterfaceProps {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  loading?: boolean;
  placeholder?: string;
  className?: string;
}

export default function ChatInterface({
  messages,
  onSend,
  loading = false,
  placeholder = "Ask a follow-up question…",
  className = "",
}: ChatInterfaceProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <div
      className={`flex flex-col ${className}`}
      style={{
        background: "var(--bg-surface)",
        border:     "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        overflow:   "hidden",
      }}
      aria-label="Chat interface"
    >
      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto p-4"
        style={{ maxHeight: "400px", minHeight: "200px" }}
        role="log"
        aria-live="polite"
        aria-label="Conversation history"
      >
        {messages.length === 0 ? (
          <p
            className="text-center text-sm"
            style={{ color: "var(--text-muted)", marginTop: "2rem" }}
          >
            No messages yet. Ask a question to get started.
          </p>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`mb-4 flex w-full ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className={`flex gap-3 items-start ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                {/* Avatar Circle */}
                <div className="flex flex-col items-center gap-1 shrink-0">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-md ${
                      msg.role === "user"
                        ? "bg-[#e03e52] text-white"
                        : "bg-gray-800 text-[#e03e52] border border-gray-700"
                    }`}
                  >
                    {msg.role === "user" ? "U" : "A"}
                  </div>
                </div>

                {/* Chat Bubble */}
                <div
                  className="max-w-[75%] rounded-xl px-4 py-2.5 text-sm leading-relaxed"
                  style={{
                    background:
                      msg.role === "user"
                        ? "var(--accent)"
                        : "var(--bg-elevated)",
                    color:
                      msg.role === "user" ? "#fff" : "var(--text-primary)",
                    borderBottomRightRadius:
                      msg.role === "user" ? "4px" : undefined,
                    borderBottomLeftRadius:
                      msg.role === "assistant" ? "4px" : undefined,
                  }}
                  aria-label={`${msg.role === "user" ? "You" : "Assistant"}: ${msg.content}`}
                >
                  {msg.content}
                  <time
                    dateTime={msg.timestamp.toISOString()}
                    className="mt-1 block text-right text-xs opacity-60"
                  >
                    {msg.timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                </div>
              </div>
            </div>
          ))
        )}

        {/* Loading indicator */}
        {loading && (
          <div className="flex justify-start w-full" aria-label="Assistant is typing">
            <div className="flex gap-3 items-start flex-row">
              {/* Avatar Circle */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-md bg-gray-800 text-[#e03e52] border border-gray-700">
                  A
                </div>
              </div>

              {/* Loading Bubble */}
              <div
                className="rounded-xl px-4 py-3"
                style={{ background: "var(--bg-elevated)" }}
              >
                <span className="flex gap-1" aria-hidden="true">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="inline-block h-2 w-2 rounded-full"
                      style={{
                        background: "var(--text-muted)",
                        animation: `bounce 1s ${i * 0.15}s infinite`,
                      }}
                    />
                  ))}
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 border-t p-3"
        style={{ borderColor: "var(--border)" }}
        aria-label="Send a message"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={placeholder}
          rows={1}
          disabled={loading}
          className="input flex-1 resize-none text-sm"
          style={{ maxHeight: "120px" }}
          aria-label="Type a message"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="btn btn-primary h-10 w-10 shrink-0 p-0"
          aria-label="Send message"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </form>
    </div>
  );
}
