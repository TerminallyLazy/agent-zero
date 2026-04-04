import { marked } from "marked";
import type { LogItem } from "../lib/types";

const renderText = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
};

const bubbleClass = (item: LogItem): string => {
  if (item.type === "user") return "message user";
  if (item.type === "response" || item.type === "agent") return "message agent";
  return "message tool";
};

export function MessageList({ items }: { items: LogItem[] }) {
  return (
    <div className="message-list">
      {items.map((item) => {
        const html = marked.parse(renderText(item.content)) as string;
        const imageDataUrl = typeof item.kvps?.image_data_url === "string" ? item.kvps.image_data_url : "";
        return (
          <article key={`${item.no}-${item.id || "log"}`} className={bubbleClass(item)}>
            <div className="message-heading">{item.heading || item.type}</div>
            <div className="message-body" dangerouslySetInnerHTML={{ __html: html }} />
            {imageDataUrl ? <img className="message-image" src={imageDataUrl} alt="Chrome bridge capture" /> : null}
            {item.type !== "user" && item.kvps ? (
              <details className="message-meta">
                <summary>Details</summary>
                <pre>{JSON.stringify(item.kvps, null, 2)}</pre>
              </details>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
