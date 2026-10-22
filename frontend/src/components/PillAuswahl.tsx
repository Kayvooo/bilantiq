import { useId } from "react";

interface Option<T extends string> {
  wert: T;
  label: string;
}

interface Props<T extends string> {
  legende: string;
  optionen: readonly Option<T>[];
  wert: T;
  onChange: (wert: T) => void;
}

/** Einfachauswahl im Pillen-Look. Native Radio-Buttons, daher Pfeiltasten und Gruppenansage ohne Zusatzcode. */
export function PillAuswahl<T extends string>({ legende, optionen, wert, onChange }: Props<T>) {
  const name = useId();
  return (
    <fieldset className="choice-group">
      <legend className="sr-only">{legende}</legend>
      <div className="pill-row">
        {optionen.map((option) => (
          <label key={option.wert} className="choice">
            <input type="radio" name={name} value={option.wert} checked={wert === option.wert} onChange={() => onChange(option.wert)} />
            <span className="choice-label">{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
