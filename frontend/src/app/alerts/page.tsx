"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { api, sast } from "@/lib/format";
import type { AlertItem, AlertSettings } from "@/lib/types";

export default function AlertsPage() {
  return (
    <Shell>
      <Alerts />
    </Shell>
  );
}

function Alerts() {
  const [settings, setSettings] = useState<AlertSettings | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [push, setPush] = useState("Browser push is off");

  async function load() {
    const payload = await api<{ settings: AlertSettings; alerts: AlertItem[] }>("/api/alerts");
    setSettings(payload.settings);
    setAlerts(payload.alerts);
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "Could not load alerts"));
  }, []);

  async function update(patch: Partial<AlertSettings>) {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      const saved = await api<AlertSettings>("/api/alerts/settings", {
        method: "POST",
        body: JSON.stringify(patch),
      });
      setSettings(saved);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  function enablePush() {
    if (!("Notification" in window)) {
      setPush("This browser does not support push.");
      return;
    }
    Notification.requestPermission().then((permission) => {
      if (permission === "granted") {
        setPush("Browser push is on for this device.");
        new Notification("TrendLens", { body: "Alerts will show while this tab is open." });
      } else {
        setPush("Browser push was blocked.");
      }
    });
  }

  return (
    <section className="panel px-4 py-5 sm:px-6">
      <h1 className="font-display text-4xl">Alerts</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        In-app alerts are stored here. Email sends only when SMTP is configured. Quiet hours default to 22:00–06:00 SAST.
      </p>
      {error ? <p className="mt-4 text-sm text-bear">{error}</p> : null}
      {settings ? (
        <div className="mt-6 grid gap-3">
          <Toggle label="Alert when the signal flips" on={settings.on_flip} onChange={(on_flip) => update({ on_flip })} />
          <Toggle
            label="Alert when confidence is above 70%"
            on={settings.on_confidence}
            onChange={(on_confidence) => update({ on_confidence })}
          />
          <Toggle
            label="Alert 30 minutes before high-impact news"
            on={settings.on_news}
            onChange={(on_news) => update({ on_news })}
          />
          <Toggle label="Quiet hours" on={settings.quiet_hours} onChange={(quiet_hours) => update({ quiet_hours })} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-muted">
              Quiet from
              <input
                type="time"
                value={settings.quiet_start}
                onChange={(event) => update({ quiet_start: event.target.value })}
                className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 font-mono text-sm text-ink"
              />
            </label>
            <label className="text-xs text-muted">
              Quiet until
              <input
                type="time"
                value={settings.quiet_end}
                onChange={(event) => update({ quiet_end: event.target.value })}
                className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 font-mono text-sm text-ink"
              />
            </label>
          </div>
          <label className="text-xs text-muted">
            Email
            <input
              type="email"
              value={settings.email}
              placeholder="you@example.com"
              onChange={(event) => setSettings({ ...settings, email: event.target.value })}
              onBlur={() => update({ email: settings.email })}
              className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 text-sm text-ink"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={enablePush} className="rounded-full border border-line px-4 py-2 text-sm">
              Enable browser push
            </button>
            <span className="text-xs text-muted">{push}</span>
          </div>
        </div>
      ) : null}
      <h2 className="mt-8 text-sm uppercase tracking-[0.16em] text-muted">Last {Math.min(50, alerts.length)} alerts</h2>
      <ul className="mt-3 divide-y divide-line">
        {alerts.length === 0 ? <li className="py-4 text-sm text-muted">No alerts yet. A flip after this session starts will land here.</li> : null}
        {alerts.map((alert) => (
          <li key={alert.id} className="py-3">
            <div className="text-sm">{alert.text}</div>
            <div className="mt-1 text-xs text-muted">
              {sast(alert.at)} · {alert.channel}
              {alert.suppressed ? " · suppressed (quiet hours)" : ""} · email {alert.email}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (value: boolean) => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onChange(!on)}
      className="flex items-center justify-between rounded-xl border border-line px-3 py-3 text-left text-sm"
    >
      <span>{label}</span>
      <span className={on ? "text-bull" : "text-muted"}>{on ? "On" : "Off"}</span>
    </button>
  );
}
