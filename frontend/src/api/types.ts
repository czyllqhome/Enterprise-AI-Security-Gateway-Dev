export type User = {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type Provider = {
  provider: string;
  display_name: string;
  configured: boolean;
  requires_api_key: boolean;
  masked_api_key: string | null;
  base_url: string;
  default_model: string;
  models: string[];
  updated_at: string | null;
};

export type Message = {
  id: number;
  role: "user" | "assistant";
  original_content: string | null;
  sanitized_content: string | null;
  used_content: string | null;
  has_sensitive_data: boolean;
  sensitive_entities_json: Record<string, unknown>[] | null;
  created_at: string;
};

export type ChatSession = {
  id: number;
  title: string;
  created_by: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
};

export type ChatSessionDetail = ChatSession & {
  messages: Message[];
};

export type GuardrailEntity = {
  type: string;
  original: string;
  masked: string;
  replacement: string;
  start: number;
  end: number;
  source?: string;
  sources?: string[];
};

export type BusinessSensitiveResult = {
  contains_business_sensitive: boolean;
  risk_level: "low" | "medium" | "high" | string;
  categories?: Array<{ name?: string; reason?: string; matched_text?: string }>;
  summary?: string;
  confidence?: number;
};

export type ChatPreview = {
  scan_event_id: number | null;
  session_id: number;
  status: "clean" | "needs_confirmation" | "blocked" | string;
  blocked_reason: string | null;
  original_message: string;
  sanitized_message: string;
  detected_entities: GuardrailEntity[];
  has_sensitive_data: boolean;
  privacy_filter_hit_count: number;
  custom_regex_hit_count: number;
  scanners: string[];
  enabled_scanners: string[];
  entity_types: string[];
  business_sensitive_result: BusinessSensitiveResult;
};

export type Dashboard = {
  total_requests: number;
  blocked_requests: number;
  review_required_requests: number;
  pii_requests: number;
  business_sensitive_requests: number;
  active_users: number;
  trend: Array<{ label: string; total: number; blocked: number; needs_review: number }>;
  top_risk_users: Array<{ username: string; total_events: number; blocked_events: number; review_events: number }>;
  incidents: Array<{ title: string; summary: string; actor: string; status: string; severity: string; created_at: string | null }>;
  governance: { active_scanners: number; total_scanners: number; configured_providers: number; audit_logs: number };
};

export type Scanner = {
  id: string;
  name: string;
  enabled: boolean;
  available: boolean;
  active: boolean;
  detail: string;
};

export type LogEntry = {
  id: number;
  session_id: number | null;
  message_id: number | null;
  username: string;
  sanitized_content: string;
  detected_entity_types: string[] | null;
  created_at: string;
};

export type TokenUsageUser = {
  username: string;
  request_count: number;
  blocked_count: number;
  review_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  max_input_tokens: number;
  over_limit_events: number;
  utilization_percent: number;
  risk_level: "normal" | "watch" | "limit" | string;
  primary_provider: string;
  primary_model: string;
  latest_activity: string | null;
};

export type TokenUsageMonitoring = {
  token_limit: number;
  encoding_name: string;
  total_users: number;
  total_requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  over_limit_events: number;
  users: TokenUsageUser[];
  trend: Array<{ label: string; input_tokens: number; output_tokens: number; total_tokens: number }>;
};
