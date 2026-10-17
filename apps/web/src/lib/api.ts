import type {
  ChatHandlers,
  Conversation,
  ConversationDetail,
  Device,
  DeviceActionInfo,
  DeviceActionRecord,
  ProviderInfo,
  SendCommandResult,
  User,
} from "./types";

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status}).`;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/${path}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(await errorMessage(res));
  return (await res.json()) as T;
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const res = await fetch(`/api/proxy/${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function authPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/auth/${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const auth = {
  login: (email: string, password: string) =>
    authPost<{ user: User }>("login", { email, password }),
  register: (email: string, password: string, displayName: string) =>
    authPost<{ user: User }>("register", {
      email,
      password,
      display_name: displayName,
    }),
  logout: () => authPost<void>("logout", {}),
  requestPasswordReset: (email: string) =>
    authPost<{ status: string }>("password-reset/request", { email }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    authPost<{ status: string }>("password-reset/confirm", {
      token,
      new_password: newPassword,
    }),
};

export const conversations = {
  list: () => apiGet<Conversation[]>("conversations"),
  get: (id: string) => apiGet<ConversationDetail>(`conversations/${id}`),
  create: (title: string) =>
    apiSend<Conversation>("conversations", "POST", { title }),
  remove: (id: string) => apiSend<void>(`conversations/${id}`, "DELETE"),
};

export const devices = {
  list: () => apiGet<Device[]>("devices"),
  catalog: () => apiGet<DeviceActionInfo[]>("devices/catalog"),
  actions: (deviceId?: string, limit = 50) =>
    apiGet<DeviceActionRecord[]>(
      `devices/actions?limit=${limit}${
        deviceId ? `&device_id=${encodeURIComponent(deviceId)}` : ""
      }`,
    ),
  approve: (code: string, name?: string, permissions?: string[]) =>
    apiSend<Device>("devices/pairing/approve", "POST", {
      code,
      ...(name ? { name } : {}),
      ...(permissions ? { permissions } : {}),
    }),
  update: (id: string, body: { name?: string; permissions?: string[] }) =>
    apiSend<Device>(`devices/${id}`, "PATCH", body),
  revoke: (id: string) => apiSend<void>(`devices/${id}`, "DELETE"),
  command: (id: string, action: string, parameters: Record<string, unknown>) =>
    apiSend<SendCommandResult>(`devices/${id}/command`, "POST", {
      action,
      parameters,
    }),
};

export const chat = {
  providers: () => apiGet<ProviderInfo[]>("chat/providers"),

  async stream(
    body: { message: string; conversation_id?: string | null; system?: string | null },
    handlers: ChatHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    const res = await fetch("/api/proxy/chat/completions", {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok || !res.body) {
      handlers.onError(await errorMessage(res));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") continue;
        try {
          const event = JSON.parse(payload) as
            | { type: "delta"; text: string }
            | { type: "error"; message: string }
            | { type: "done"; conversation_id: string };
          if (event.type === "delta") handlers.onDelta(event.text);
          else if (event.type === "error") handlers.onError(event.message);
          else if (event.type === "done") handlers.onConversation(event.conversation_id);
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  },
};
