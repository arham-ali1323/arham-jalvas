"use client";

import {
  MonitorSmartphone,
  Pencil,
  PlugZap,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { devices as deviceApi } from "@/lib/api";
import type { Device, DeviceActionInfo, DeviceActionRecord } from "@/lib/types";

const PERMISSION_LABELS: Record<string, string> = {
  "app.launch": "Open applications",
  "browser.navigate": "Open web pages",
  "system.info": "Read system status",
  "media.control": "Control media playback",
  "volume.control": "Change volume",
  "notification.send": "Show notifications",
  "power.control": "Power: lock, sleep, restart, shut down",
};

const STATUS_STYLES: Record<string, string> = {
  pending: "text-amber",
  approved: "text-primary",
  success: "text-success",
  denied: "text-danger",
  error: "text-danger",
};

function relative(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

export default function DevicesPage() {
  const [list, setList] = useState<Device[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<DeviceActionInfo[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [code, setCode] = useState("");
  const [pairing, setPairing] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);

  const [history, setHistory] = useState<DeviceActionRecord[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      setList(await deviceApi.list());
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Failed to load devices.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    deviceApi
      .catalog()
      .then(setCatalog)
      .catch(() => setCatalog([]));
  }, [refresh]);

  const selected = useMemo(
    () => (list ?? []).find((d) => d.id === selectedId) ?? null,
    [list, selectedId],
  );

  useEffect(() => {
    if (!selectedId) {
      setHistory(null);
      return;
    }
    void deviceApi
      .actions(selectedId, 50)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [selectedId]);

  // Keep online badges and the activity feed fresh while the page is open.
  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh();
      if (selectedId) {
        void deviceApi.actions(selectedId, 50).then(setHistory).catch(() => {});
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, selectedId]);

  const allPermissions = useMemo(() => {
    const set = new Set<string>();
    for (const action of catalog ?? []) set.add(action.permission);
    return Array.from(set).sort();
  }, [catalog]);

  async function approve(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) return;
    setPairing(true);
    setPairError(null);
    try {
      const device = await deviceApi.approve(trimmed);
      setCode("");
      await refresh();
      setSelectedId(device.id);
    } catch (err) {
      setPairError(
        err instanceof Error ? err.message : "Could not approve that code.",
      );
    } finally {
      setPairing(false);
    }
  }

  const patch = useCallback((updated: Device) => {
    setList((prev) =>
      (prev ?? []).map((d) => (d.id === updated.id ? updated : d)),
    );
  }, []);

  async function togglePermission(device: Device, permission: string) {
    const granted = new Set(
      device.permissions.filter((p) => p.granted).map((p) => p.permission),
    );
    if (granted.has(permission)) granted.delete(permission);
    else granted.add(permission);
    try {
      patch(
        await deviceApi.update(device.id, {
          permissions: Array.from(granted),
        }),
      );
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  async function rename(device: Device, name: string) {
    try {
      patch(await deviceApi.update(device.id, { name }));
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Rename failed.");
    }
  }

  async function revoke(device: Device) {
    if (
      !window.confirm(
        `Unpair "${device.name}"? Its credential is destroyed and it can no longer be controlled from here.`,
      )
    ) {
      return;
    }
    try {
      await deviceApi.revoke(device.id);
      if (selectedId === device.id) setSelectedId(null);
      await refresh();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Revoke failed.");
    }
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Connected devices"
        description="Computers paired to your account. Commands run only from a fixed, allowlisted set."
        action={
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />
      <div className="flex-1 overflow-y-auto p-8">
        <div className="mx-auto grid max-w-4xl gap-6 lg:grid-cols-[1.1fr_1fr]">
          <div className="space-y-6">
            <Card>
              <div className="flex items-center gap-2">
                <PlugZap className="h-4 w-4 text-primary" />
                <CardTitle>Pair a computer</CardTitle>
              </div>
              <CardDescription>
                On the target machine, open MARK LIV and start its companion. It
                shows a short code — enter it here to approve the pairing.
              </CardDescription>
              <form onSubmit={approve} className="mt-4 flex gap-2">
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="ABC-123"
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono tracking-widest"
                  maxLength={12}
                  aria-label="Pairing code"
                />
                <Button type="submit" disabled={pairing || !code.trim()}>
                  {pairing ? <Spinner /> : "Pair"}
                </Button>
              </form>
              {pairError ? (
                <p className="mt-2 text-sm text-danger">{pairError}</p>
              ) : (
                <p className="mt-2 text-xs text-muted">
                  Codes expire after a few minutes. Never approve a code you did
                  not initiate on your own machine.
                </p>
              )}
            </Card>

            {listError ? (
              <Card>
                <CardDescription>{listError}</CardDescription>
              </Card>
            ) : list === null ? (
              <Card>
                <Spinner className="mt-1" />
              </Card>
            ) : list.length === 0 ? (
              <Card>
                <div className="flex items-center gap-3">
                  <span className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-surface-2 text-muted">
                    <MonitorSmartphone className="h-5 w-5" />
                  </span>
                  <div>
                    <CardTitle>No devices yet</CardTitle>
                    <CardDescription>
                      Pair a desktop companion to control it from anywhere.
                    </CardDescription>
                  </div>
                </div>
              </Card>
            ) : (
              list.map((device) => (
                <DeviceRow
                  key={device.id}
                  device={device}
                  selected={device.id === selectedId}
                  permissions={allPermissions}
                  onSelect={() => setSelectedId(device.id)}
                  onTogglePermission={(perm) =>
                    void togglePermission(device, perm)
                  }
                  onRename={(name) => void rename(device, name)}
                  onRevoke={() => void revoke(device)}
                />
              ))
            )}
          </div>

          <div className="space-y-6">
            {selected ? (
              <CommandPanel
                device={selected}
                catalog={catalog}
                onSent={() =>
                  void deviceApi
                    .actions(selected.id, 50)
                    .then(setHistory)
                    .catch(() => {})
                }
              />
            ) : (
              <Card>
                <CardTitle>Send a command</CardTitle>
                <CardDescription>
                  Pair a device, then select it to send an allowlisted command.
                </CardDescription>
              </Card>
            )}

            <Card>
              <div className="flex items-center justify-between">
                <CardTitle>Recent activity</CardTitle>
                {selected ? (
                  <span className="text-xs text-muted">{selected.name}</span>
                ) : null}
              </div>
              {history === null ? (
                <CardDescription>
                  Select a device to see its history.
                </CardDescription>
              ) : history.length === 0 ? (
                <CardDescription>No commands sent yet.</CardDescription>
              ) : (
                <ul className="mt-3 space-y-2">
                  {history.map((entry) => (
                    <li
                      key={entry.id}
                      className="flex items-start justify-between gap-3 border-b border-border/40 pb-2 text-sm last:border-0"
                    >
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 font-mono text-xs text-slate-100">
                          {entry.action}
                          {entry.requires_confirmation ? (
                            <ShieldCheck
                              className="h-3.5 w-3.5 text-amber"
                              aria-label="Needs on-device confirmation"
                            />
                          ) : null}
                        </p>
                        <p
                          className="truncate text-xs text-muted"
                          title={entry.result}
                        >
                          {entry.result || "—"}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p
                          className={`text-xs ${
                            STATUS_STYLES[entry.status] ?? "text-muted"
                          }`}
                        >
                          {entry.status}
                        </p>
                        <p className="text-xs text-muted">
                          {relative(entry.created_at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function DeviceRow({
  device,
  selected,
  permissions,
  onSelect,
  onTogglePermission,
  onRename,
  onRevoke,
}: {
  device: Device;
  selected: boolean;
  permissions: string[];
  onSelect: () => void;
  onTogglePermission: (permission: string) => void;
  onRename: (name: string) => void;
  onRevoke: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(device.name);

  const granted = useMemo(
    () => new Set(device.permissions.filter((p) => p.granted).map((p) => p.permission)),
    [device.permissions],
  );

  return (
    <Card
      className={
        selected ? "ring-1 ring-primary/50" : undefined
      }
    >
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <span
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg border ${
              device.online
                ? "border-success/40 bg-success/10 text-success"
                : "border-border bg-surface-2 text-muted"
            }`}
          >
            {device.online ? (
              <Wifi className="h-5 w-5" />
            ) : (
              <WifiOff className="h-5 w-5" />
            )}
          </span>
          <div className="min-w-0">
            <CardTitle className="truncate">{device.name}</CardTitle>
            <CardDescription>
              {device.platform || "desktop"} ·{" "}
              {device.online ? "online" : `last seen ${relative(device.last_seen_at)}`}
              {device.revoked ? " · unpaired" : ""}
            </CardDescription>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Rename device"
            onClick={() => {
              setName(device.name);
              setEditing((v) => !v);
            }}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Unpair device"
            onClick={onRevoke}
            disabled={device.revoked}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {editing ? (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const next = name.trim();
            if (next && next !== device.name) onRename(next);
            setEditing(false);
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            aria-label="Device name"
            autoFocus
          />
          <Button type="submit" size="sm">
            Save
          </Button>
        </form>
      ) : null}

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {permissions.map((permission) => (
          <label
            key={permission}
            className="flex cursor-pointer items-start gap-2 text-xs text-slate-200"
          >
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]"
              checked={granted.has(permission)}
              disabled={device.revoked}
              onChange={() => onTogglePermission(permission)}
            />
            <span>
              {PERMISSION_LABELS[permission] ?? permission}
            </span>
          </label>
        ))}
      </div>
    </Card>
  );
}

function CommandPanel({
  device,
  catalog,
  onSent,
}: {
  device: Device;
  catalog: DeviceActionInfo[] | null;
  onSent: () => void;
}) {
  const [actionName, setActionName] = useState("");
  const [values, setValues] = useState<Record<string, string | boolean>>({});  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<
    { kind: "ok" | "error"; text: string } | null
  >(null);

  const action = useMemo(
    () => (catalog ?? []).find((a) => a.name === actionName) ?? null,
    [catalog, actionName],
  );

  useEffect(() => {
    if (!action) {
      setValues({});
      return;
    }
    const initial: Record<string, string | boolean> = {};
    for (const [key, spec] of Object.entries(action.parameters)) {
      if (spec.type === "boolean") initial[key] = false;
      else if (spec.enum?.length) initial[key] = spec.enum[0] ?? "";
      else initial[key] = "";
    }
    setValues(initial);
  }, [action]);

  const granted = useMemo(
    () =>
      new Set(
        device.permissions.filter((p) => p.granted).map((p) => p.permission),
      ),
    [device.permissions],
  );

  const permissionMissing = action ? !granted.has(action.permission) : false;
  const offline = !device.online || device.revoked;

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!action) return;
    const parameters: Record<string, unknown> = {};
    for (const [key, spec] of Object.entries(action.parameters)) {
      const raw = values[key];
      if (spec.type === "boolean") parameters[key] = Boolean(raw);
      else if (spec.type === "integer" || spec.type === "number")
        parameters[key] = Number(raw);
      else parameters[key] = String(raw ?? "");
    }
    setBusy(true);
    setNotice(null);
    try {
      const result = await deviceApi.command(device.id, action.name, parameters);
      setNotice({
        kind: "ok",
        text: result.requires_confirmation
          ? "Sent. It will run once someone confirms it on the device."
          : "Sent.",
      });
      onSent();
    } catch (err) {
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Command failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex items-center gap-2">
        <Send className="h-4 w-4 text-primary" />
        <CardTitle>Send a command</CardTitle>
      </div>
      <CardDescription>
        Only allowlisted actions are offered. Sensitive actions still need
        confirmation on the device.
      </CardDescription>

      {catalog === null ? (
        <Spinner className="mt-4" />
      ) : (
        <form onSubmit={send} className="mt-4 space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="device-action">Action</Label>
            <select
              id="device-action"
              value={actionName}
              onChange={(e) => setActionName(e.target.value)}
              className="h-10 w-full rounded-lg border border-border bg-surface/70 px-3 text-sm text-slate-100 focus:border-primary/70 focus:outline-none"
            >
              <option value="">Choose an action…</option>
              {(catalog ?? []).map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name} — {a.description}
                </option>
              ))}
            </select>
          </div>

          {action
            ? Object.entries(action.parameters).map(([key, spec]) => (
                <div key={key} className="space-y-1">
                  <Label htmlFor={`param-${key}`}>
                    {spec.description || key}
                  </Label>
                  {spec.type === "boolean" ? (
                    <select
                      id={`param-${key}`}
                      value={values[key] ? "true" : "false"}
                      onChange={(e) =>
                        setValues((v) => ({
                          ...v,
                          [key]: e.target.value === "true",
                        }))
                      }
                      className="h-10 w-full rounded-lg border border-border bg-surface/70 px-3 text-sm text-slate-100"
                    >
                      <option value="false">No</option>
                      <option value="true">Yes</option>
                    </select>
                  ) : spec.enum?.length ? (
                    <select
                      id={`param-${key}`}
                      value={String(values[key] ?? spec.enum[0])}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, [key]: e.target.value }))
                      }
                      className="h-10 w-full rounded-lg border border-border bg-surface/70 px-3 text-sm text-slate-100"
                    >
                      {spec.enum.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      id={`param-${key}`}
                      type={
                        spec.type === "integer" || spec.type === "number"
                          ? "number"
                          : "text"
                      }
                      min={spec.minimum}
                      max={spec.maximum}
                      maxLength={spec.maxLength}
                      value={String(values[key] ?? "")}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, [key]: e.target.value }))
                      }
                    />
                  )}
                </div>
              ))
            : null}

          {action && action.requires_confirmation ? (
            <p className="flex items-center gap-2 text-xs text-amber">
              <ShieldCheck className="h-3.5 w-3.5" />
              Someone must confirm this on the device.
            </p>
          ) : null}

          {offline ? (
            <p className="text-xs text-muted">
              This device is offline. Commands can be sent once it reconnects.
            </p>
          ) : permissionMissing && action ? (
            <p className="text-xs text-danger">
              The {PERMISSION_LABELS[action.permission] ?? action.permission}{" "}
              permission is not granted to this device.
            </p>
          ) : null}

          {notice ? (
            <p
              className={
                notice.kind === "ok"
                  ? "text-xs text-success"
                  : "text-xs text-danger"
              }
            >
              {notice.text}
            </p>
          ) : null}

          <Button
            type="submit"
            disabled={!action || busy || offline || permissionMissing}
          >
            {busy ? <Spinner /> : <Send className="h-4 w-4" />}
            Send command
          </Button>
        </form>
      )}
    </Card>
  );
}
