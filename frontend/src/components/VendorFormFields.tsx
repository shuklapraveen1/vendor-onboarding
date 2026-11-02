import { Building2, Check, Landmark, MapPin, Receipt, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChangeEvent, ReactNode } from "react";
import { useAppConfig } from "../lib";
import type { VendorForm } from "../types";

type Section = keyof VendorForm;

interface Props {
  value: VendorForm;
  onChange: (next: VendorForm) => void;
  highlight?: Set<string>;
  disabled?: boolean;
}

export default function VendorFormFields({ value, onChange, highlight, disabled }: Props) {
  const config = useAppConfig();
  const bt = value.company.business_type;
  const isCompany = bt === "PRIVATE_LIMITED" || bt === "PUBLIC_LIMITED";

  const set = (section: Section, key: string, v: string | boolean) =>
    onChange({ ...value, [section]: { ...(value[section] as Record<string, unknown>), [key]: v } } as VendorForm);

  const field = (section: Section, key: string, label: string, opts: {
    required?: boolean; placeholder?: string; type?: string; mono?: boolean; wide?: boolean; help?: string;
  } = {}) => {
    const path = `${section}.${key}`;
    const v = (value[section] as Record<string, unknown>)[key];
    return (
      <label className={`field ${opts.wide ? "field-wide" : ""} ${highlight?.has(path) ? "field-flagged" : ""}`}>
        <span className="field-label">
          {label}
          {opts.required && <em>*</em>}
        </span>
        <input
          type={opts.type ?? "text"}
          className={opts.mono ? "mono" : ""}
          value={(v as string) ?? ""}
          placeholder={opts.placeholder}
          disabled={disabled}
          onChange={(e: ChangeEvent<HTMLInputElement>) => set(section, key, e.target.value)}
        />
        {opts.help && <span className="field-help">{opts.help}</span>}
      </label>
    );
  };

  const select = (section: Section, key: string, label: string, options: [string, string][], required?: boolean) => {
    const path = `${section}.${key}`;
    return (
      <label className={`field ${highlight?.has(path) ? "field-flagged" : ""}`}>
        <span className="field-label">
          {label}
          {required && <em>*</em>}
        </span>
        <select
          value={(value[section] as Record<string, string>)[key] ?? ""}
          disabled={disabled}
          onChange={(e) => set(section, key, e.target.value)}
        >
          <option value="">Select…</option>
          {options.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
    );
  };

  const group = (n: number, Icon: LucideIcon, title: string, subtitle: string, children: ReactNode) => (
    <fieldset className="form-group">
      <legend className="form-section-head">
        <span className="form-section-num">{n}</span>
        <span className="form-section-icon"><Icon size={16} /></span>
        <span>
          <strong>{title}</strong>
          <span className="muted small">{subtitle}</span>
        </span>
      </legend>
      <div className="form-grid">{children}</div>
    </fieldset>
  );

  return (
    <div className="vendor-form">
      {group(1, Building2, "Company", "Legal identity", <>
        {field("company", "legal_name", "Legal name", { required: true, wide: true, placeholder: "As registered with MCA / GST" })}
        {field("company", "trade_name", "Trade name")}
        {select("company", "business_type", "Business type", Object.entries(config?.business_types ?? {}), true)}
        {field("company", "date_of_incorporation", "Date of incorporation", { type: "date" })}
        {isCompany && field("company", "cin", "CIN", { required: true, mono: true, placeholder: "U29100KA2015PTC081234" })}
        {bt === "LLP" && field("company", "llpin", "LLPIN", { required: true, mono: true, placeholder: "AAB-1234" })}
      </>)}

      {group(2, MapPin, "Registered address", "Must match your GST registration state", <>
        {field("address", "line1", "Address line", { required: true, wide: true })}
        {field("address", "city", "City", { required: true })}
        {select("address", "state", "State", (config?.states ?? []).map((s) => [s, s] as [string, string]), true)}
        {field("address", "pincode", "PIN code", { required: true, mono: true, placeholder: "560099" })}
      </>)}

      {group(3, Receipt, "Tax registration", "PAN, GSTIN and MSME status", <>
        {field("tax", "pan", "PAN", { required: true, mono: true, placeholder: "AABCK1234M" })}
        {field("tax", "gstin", "GSTIN", { required: true, mono: true, placeholder: "29AABCK1234M1Z5" })}
        <label className={`field checkbox-field ${highlight?.has("tax.msme_registered") ? "field-flagged" : ""}`}>
          <input
            type="checkbox"
            className="check-input"
            checked={value.tax.msme_registered}
            disabled={disabled}
            onChange={(e) => set("tax", "msme_registered", e.target.checked)}
          />
          <span className="check-box" aria-hidden><Check size={12} strokeWidth={3.5} /></span>
          <span>Registered as MSME (Udyam)</span>
        </label>
        {value.tax.msme_registered && field("tax", "udyam_number", "Udyam number", { required: true, mono: true, placeholder: "UDYAM-KR-03-0012345" })}
      </>)}

      {group(4, Landmark, "Bank account", "Where payments will be sent", <>
        {field("bank", "account_holder_name", "Account holder name", { required: true, wide: true })}
        {field("bank", "account_number", "Account number", { required: true, mono: true })}
        {field("bank", "confirm_account_number", "Confirm account number", { required: true, mono: true })}
        {field("bank", "ifsc", "IFSC", { required: true, mono: true, placeholder: "HDFC0000523" })}
        {field("bank", "bank_name", "Bank name")}
        {select("bank", "account_type", "Account type", [["Current", "Current"], ["Savings", "Savings"]])}
      </>)}

      {group(5, Users, "People", "Contact and authorised signatory", <>
        {field("contact", "name", "Contact name", { required: true })}
        {field("contact", "designation", "Designation")}
        {field("contact", "email", "Email", { required: true, type: "email" })}
        {field("contact", "phone", "Mobile", { required: true, placeholder: "+91 98xxxxxxxx" })}
        {field("signatory", "name", "Authorised signatory", { required: true })}
        {field("signatory", "designation", "Signatory designation")}
      </>)}

      <label className={`declaration ${value.declaration.accepted ? "is-checked" : ""} ${highlight?.has("declaration.accepted") ? "field-flagged" : ""}`}>
        <input
          type="checkbox"
          className="check-input"
          checked={value.declaration.accepted}
          disabled={disabled}
          onChange={(e) => set("declaration", "accepted", e.target.checked)}
        />
        <span className="check-box" aria-hidden><Check size={12} strokeWidth={3.5} /></span>
        <span>I declare that the information provided is true and complete, and I am authorised to submit it on behalf of the company.</span>
      </label>
    </div>
  );
}
