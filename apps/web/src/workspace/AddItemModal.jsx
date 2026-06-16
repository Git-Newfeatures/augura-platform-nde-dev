import { useState } from 'react'
import { X } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

// Reusable "add a library item" modal driven by a field schema.
// fields: [{ key, label, type: 'text'|'number'|'select', options?, placeholder?, required?, default? }]
//   options: array of strings, or { value, label } objects.
// onSave receives the raw form object; the caller shapes it into a row.

const inputCls =
  'w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-foreground ' +
  'placeholder:text-muted-foreground/60 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15'

const optVal = (o) => (o && typeof o === 'object' ? o.value : o)
const optLab = (o) => (o && typeof o === 'object' ? o.label : o)

export function AddItemModal({ title, subtitle, fields, submitLabel, onClose, onSave }) {
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.key,
        f.default ?? (f.type === 'select' ? optVal(f.options?.[0]) ?? '' : ''),
      ]),
    ),
  )
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))
  const requiredOk = fields
    .filter((f) => f.required)
    .every((f) => String(form[f.key] ?? '').trim().length > 0)

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[rgba(15,14,12,0.34)] p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-[460px] gap-0 p-0 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-border p-5">
          <div>
            <h2 className="text-[16px] font-semibold text-foreground">{title}</h2>
            {subtitle && <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        {/* Fields */}
        <div className="flex flex-col gap-4 p-5">
          {fields.map((f) => (
            <label key={f.key} className="block">
              <div className="mb-1.5 text-[12.5px] font-medium text-foreground">
                {f.label}
                {f.required && <span className="text-[#C0392B]"> *</span>}
              </div>
              {f.type === 'select' ? (
                <select
                  className={inputCls}
                  value={form[f.key]}
                  onChange={(e) => set(f.key, e.target.value)}
                >
                  {(f.options || []).map((o) => (
                    <option key={optVal(o)} value={optVal(o)}>
                      {optLab(o)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className={inputCls}
                  type={f.type === 'number' ? 'number' : 'text'}
                  placeholder={f.placeholder}
                  value={form[f.key]}
                  onChange={(e) => set(f.key, e.target.value)}
                  autoFocus={fields[0]?.key === f.key}
                />
              )}
            </label>
          ))}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-border p-5">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!requiredOk} onClick={() => onSave(form)}>
            {submitLabel || title}
          </Button>
        </div>
      </Card>
    </div>
  )
}
