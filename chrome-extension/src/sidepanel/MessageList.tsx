import { marked } from "marked";

import type { ConversationItem } from "../lib/types";

const renderAssistantHtml = (value: string): string => (marked.parse(value || "") as string);

export function MessageList({ items }: { items: ConversationItem[] }) {
  return (
    <div className="message-list">
      {items.map((item) => (
        <article key={item.id} className={`chat-bubble ${item.role} ${item.pending ? "pending" : ""}`}>
          {item.role === "assistant" ? (
            <div className="chat-bubble-body markdown-body" dangerouslySetInnerHTML={{ __html: renderAssistantHtml(item.text) }} />
          ) : (
            <div className="chat-bubble-body user-copy">{item.text}</div>
          )}
          {item.attachments.length ? (
            <div className="chat-attachments">
              {item.attachments.map((attachment) => (
                <span key={attachment} className="attachment-tag">
                  {attachment}
                </span>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
