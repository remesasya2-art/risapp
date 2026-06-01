import { useState, useEffect, useRef } from 'react';

/**
 * Number input with live Latin formatting (1.000.000,00).
 * - Shows thousand separators as the user types.
 * - Supports comma as decimal separator.
 * - Returns the pure numeric string (with "." decimal, no grouping) via onChange.
 */
export const FormattedNumberInput = ({ value, onChange, decimals = 2, style, ...rest }) => {
  const [display, setDisplay] = useState('');
  const inputRef = useRef(null);

  // Build display string from external numeric value (with "." decimal)
  useEffect(() => {
    if (value === '' || value === null || value === undefined) {
      setDisplay('');
      return;
    }
    const num = Number(value);
    if (isNaN(num)) {
      setDisplay('');
      return;
    }
    // Preserve up to `decimals` digits
    const [intPart, decPart] = String(value).split('.');
    const intWithSep = Number(intPart || 0).toLocaleString('de-DE');
    if (decPart !== undefined) {
      setDisplay(`${intWithSep},${decPart.slice(0, decimals)}`);
    } else {
      setDisplay(intWithSep);
    }
  }, [value, decimals]);

  const handleChange = (e) => {
    let raw = e.target.value;
    // Keep only digits, dots and commas
    raw = raw.replace(/[^\d.,]/g, '');
    // Remove all dots (thousand separators); keep first comma only
    const firstComma = raw.indexOf(',');
    let intPart = '', decPart = '';
    if (firstComma === -1) {
      intPart = raw.replace(/\./g, '');
    } else {
      intPart = raw.slice(0, firstComma).replace(/\./g, '');
      decPart = raw.slice(firstComma + 1).replace(/[.,]/g, '').slice(0, decimals);
    }
    // Strip leading zeros (but keep one if empty)
    intPart = intPart.replace(/^0+(?=\d)/, '');
    // Build display
    const intDisplay = intPart === '' ? '' : Number(intPart).toLocaleString('de-DE');
    const newDisplay = firstComma === -1
      ? intDisplay
      : `${intDisplay || '0'},${decPart}`;
    setDisplay(newDisplay);

    // Emit raw numeric (with "." decimal)
    const numericRaw = firstComma === -1 ? intPart : `${intPart || '0'}.${decPart}`;
    onChange(numericRaw);
  };

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="decimal"
      value={display}
      onChange={handleChange}
      style={style}
      {...rest}
    />
  );
};
