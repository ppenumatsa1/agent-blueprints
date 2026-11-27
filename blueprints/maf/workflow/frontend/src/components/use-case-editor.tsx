import type { ReactNode } from "react";

type PathPart = string | number;

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function replaceValue(value: unknown, path: readonly PathPart[], replacement: unknown): unknown {
  if (path.length === 0) return replacement;
  const [key, ...rest] = path;
  if (Array.isArray(value) && typeof key === "number") {
    return value.map((item, index) => index === key ? replaceValue(item, rest, replacement) : item);
  }
  if (isObject(value) && typeof key === "string" && Object.hasOwn(value, key)) {
    return { ...value, [key]: replaceValue(value[key], rest, replacement) };
  }
  throw new Error("The use-case input structure changed unexpectedly.");
}

function labelFor(key: string): string {
  return key.replaceAll("_", " ").replace(/\bid\b/g, "ID");
}

export function UseCaseEditor({
  template,
  value,
  disabled,
  onChange,
}: {
  template: Readonly<Record<string, unknown>>;
  value: Record<string, unknown>;
  disabled: boolean;
  onChange(value: Record<string, unknown>): void;
}) {
  function update(path: readonly PathPart[], replacement: unknown) {
    const updated = replaceValue(value, path, replacement);
    if (!isObject(updated)) throw new Error("The use-case input must be an object.");
    onChange(updated);
  }

  function fields(shape: unknown, current: unknown, path: PathPart[], label: string): ReactNode {
    if (Array.isArray(shape)) {
      const currentItems = Array.isArray(current) ? current : [];
      return (
        <fieldset key={path.join(".")}>
          <legend>{label}</legend>
          {shape.length === 0 ? <p>No inputs.</p> : shape.map((item, index) =>
            fields(item, currentItems[index], [...path, index], `${label} ${index + 1}`),
          )}
        </fieldset>
      );
    }
    if (isObject(shape)) {
      const currentObject = isObject(current) ? current : {};
      return (
        <fieldset key={path.join(".")}>
          <legend>{label}</legend>
          {Object.entries(shape).map(([key, item]) =>
            fields(item, currentObject[key], [...path, key], `${label} ${labelFor(key)}`),
          )}
        </fieldset>
      );
    }
    const id = `use-case-input-${path.join("-")}`;
    if (typeof shape === "boolean") {
      return (
        <label className="use-case-checkbox" key={id} htmlFor={id}>
          <input id={id} type="checkbox" checked={current === true} disabled={disabled}
            onChange={(event) => update(path, event.target.checked)} />
          {label}
        </label>
      );
    }
    if (typeof shape === "string" || typeof shape === "number") {
      return (
        <div className="use-case-field" key={id}>
          <label htmlFor={id}>{label}</label>
          <input id={id} type={typeof shape === "number" ? "number" : "text"}
            step={typeof shape === "number" ? "any" : undefined}
            value={typeof current === "string" || typeof current === "number" ? current : ""}
            required disabled={disabled}
            onChange={(event) => update(path, typeof shape === "number"
              ? (event.target.value === "" ? null : event.target.valueAsNumber)
              : event.target.value)} />
        </div>
      );
    }
    return <p key={id}>This input cannot be edited in the form. Use the JSON field below.</p>;
  }

  return (
    <div className="use-case-fields">
      {Object.entries(template).map(([key, item]) => fields(item, value[key], [key], labelFor(key)))}
    </div>
  );
}
