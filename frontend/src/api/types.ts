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
  attachments?: Array<{ file_id: number; filename: string; sha256: string }>;
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

export type BusinessSensitiveFinding = {
  source: "prompt" | "attachment" | string;
  file_id?: number | null;
  filename?: string | null;
  result: BusinessSensitiveResult;
};

export type ChatPreview = {
  snapshot_id: string | null;
  scan_event_id: number | null;
  session_id: number;
  attachment_file_id: number | null;
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
  business_sensitive_findings: BusinessSensitiveFinding[];
  scan_proof: string | null;
  proof_expires_at: string | null;
  degraded_scanners: string[];
  scan_duration_ms: number;
};

export type UploadedFile = {
  id: number;
  original_filename: string;
  stored_filename: string;
  file_type: string;
  content_type: string;
  extension: string;
  size_bytes: number;
  storage_path: string;
  uploaded_by: string;
  status: "processing" | "completed" | "failed" | string;
  extraction_summary: string | null;
  extracted_text: string | null;
  extracted_segments: ExtractedSegment[];
  review_result: {
    review_decision: "allow" | "needs_confirmation" | "block" | "unknown";
    total_chunks: number;
    reviewed_chunks: number;
    failed_locations: string[];
    contains_business_sensitive: boolean;
    risk_level: "low" | "medium" | "high" | string;
    summary: string;
    confidence?: number;
    categories?: string[];
    hits?: Array<{ category: string; risk_level: string; reason: string; matched_text: string; location: string }>;
    model?: string;
  } | null;
  review_fingerprint: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ExtractedSegment = {
  location: string;
  text: string;
  page_number: number | null;
  sheet_name: string | null;
  slide_number: number | null;
  source_kind: string;
};

export type FileStorageSettings = {
  default_storage_path: string;
  active_storage_profile: "windows" | "linux";
  windows_storage_path: string;
  linux_storage_path: string;
  per_user_subdirectories: boolean;
  max_upload_mb: number;
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

export type BusinessSensitiveScannerOption = {
  provider: "ollama" | "qwen" | "openrouter" | "bedrock";
  model: string;
  label: string;
  description: string;
};

export type BusinessSensitiveScannerConfig = {
  provider: "ollama" | "qwen" | "openrouter" | "bedrock";
  model: string;
  options: BusinessSensitiveScannerOption[];
  configured: boolean;
  detail: string;
};

export type ConsoleScannersResponse = {
  scanners: Scanner[];
  enabled_scanners: string[];
  strict_mode: boolean;
  business_sensitive_config?: BusinessSensitiveScannerConfig | null;
};

export type LogEntry = {
  id: number;
  session_id: number | null;
  message_id: number | null;
  scan_event_id: number | null;
  username: string;
  decision: "allowed" | "review" | "blocked";
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
