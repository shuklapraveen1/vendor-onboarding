import { CircleCheck, FileText, TriangleAlert, Upload, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DragEvent } from "react";
import { useAppConfig } from "../lib";
import { delay } from "./motion";

interface Props {
  files: Record<string, File | null>;
  onChange: (next: Record<string, File | null>) => void;
  required: string[];
  existing?: { slot: string; filename: string }[];
  highlight?: Set<string>;
  disabled?: boolean;
}

export default function DocumentSlots({ files, onChange, required, existing = [], highlight, disabled }: Props) {
  const config = useAppConfig();
  const slots = Object.entries(config?.document_slots ?? {});
  const [dragOver, setDragOver] = useState<string | null>(null);
  const urls = useMemo(() => {
    const out: Record<string, string> = {};
    Object.entries(files).forEach(([slot, f]) => {
      if (f) out[slot] = URL.createObjectURL(f);
    });
    return out;
  }, [files]);
  useEffect(() => () => Object.values(urls).forEach((u) => URL.revokeObjectURL(u)), [urls]);

  const onDrop = (slot: string) => (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(null);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onChange({ ...files, [slot]: f });
  };

  return (
    <div className="doc-slots">
      {slots.map(([slot, label], i) => {
        const file = files[slot];
        const onFile = existing.find((e) => e.slot === slot);
        const isRequired = required.includes(slot);
        const flagged = highlight?.has(`documents.${slot}`);
        const state = file ? "has-file" : flagged ? "doc-flagged" : onFile ? "on-file" : "";
        return (
          <div
            key={slot}
            className={`doc-slot a-rise ${state} ${dragOver === slot ? "drag-over" : ""}`}
            style={delay(i * 0.04)}
            onDragOver={(e) => {
              e.preventDefault();
              if (!disabled) setDragOver(slot);
            }}
            onDragLeave={() => setDragOver((d) => (d === slot ? null : d))}
            onDrop={onDrop(slot)}
          >
            <div className="doc-slot-head">
              <span className="doc-slot-icon">
                <span key={file ? "ok" : flagged ? "warn" : "doc"} className="icon-pop icon-swap">
                  {file ? <CircleCheck size={20} /> : flagged ? <TriangleAlert size={20} /> : <FileText size={20} />}
                </span>
              </span>
              <div className="doc-slot-text">
                <div className="doc-label">
                  {label}
                  {isRequired ? <em>required</em> : <span className="doc-optional">optional</span>}
                </div>
                <div className="doc-file">
                  {file ? (
                    <a href={urls[slot]} target="_blank" rel="noreferrer">
                      {file.name} · {(file.size / 1024).toFixed(0)} KB
                    </a>
                  ) : onFile ? (
                    <span className="muted">On file: {onFile.filename}{flagged ? " · please replace" : ""}</span>
                  ) : (
                    <span className="muted">Drop a PDF here or upload</span>
                  )}
                </div>
              </div>
            </div>
            <div className="doc-actions">
              <label className={`btn btn-sm ${flagged && !file ? "btn-primary" : "btn-ghost"} ${disabled ? "disabled" : ""}`}>
                <Upload size={13} /> {file || onFile ? "Replace" : "Upload"}
                <input
                  type="file"
                  accept="application/pdf"
                  hidden
                  disabled={disabled}
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    onChange({ ...files, [slot]: f });
                    e.target.value = "";
                  }}
                />
              </label>
              {file && (
                <button
                  type="button"
                  className="btn btn-sm btn-icon btn-ghost"
                  disabled={disabled}
                  onClick={() => onChange({ ...files, [slot]: null })}
                  aria-label={`Remove ${label}`}
                  title="Remove"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
