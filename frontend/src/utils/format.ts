export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
}

export function messageText(message: { role: string; used_content: string | null; sanitized_content: string | null; original_content: string | null }) {
  if (message.role === "assistant") {
    return message.sanitized_content || message.original_content || message.used_content || "";
  }
  return message.used_content || message.sanitized_content || message.original_content || "";
}
