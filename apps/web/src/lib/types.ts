export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ProviderInfo {
  name: string;
  configured: boolean;
  model: string;
}

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "error"; message: string }
  | { type: "done"; conversation_id: string };

export interface ChatHandlers {
  onDelta: (text: string) => void;
  onConversation: (conversationId: string) => void;
  onError: (message: string) => void;
}

export interface DevicePermission {
  permission: string;
  granted: boolean;
}

export interface Device {
  id: string;
  name: string;
  platform: string;
  fingerprint: string;
  revoked: boolean;
  online: boolean;
  paired_at: string | null;
  last_seen_at: string | null;
  permissions: DevicePermission[];
}

export interface DeviceActionParam {
  type?: string;
  description?: string;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  maxLength?: number;
}

export interface DeviceActionInfo {
  name: string;
  description: string;
  permission: string;
  parameters: Record<string, DeviceActionParam>;
  requires_confirmation: boolean;
  default_granted: boolean;
}

export interface DeviceActionRecord {
  id: string;
  device_id: string | null;
  action: string;
  parameters: Record<string, unknown>;
  status: string;
  result: string;
  created_at: string;
  requires_confirmation: boolean;
}

export interface SendCommandResult {
  action_id: string;
  status: string;
  requires_confirmation: boolean;
}
