// A three-way merge applies only local edits; remote-only edits survive.
export interface FieldDifference {
  path: string[];
  base: unknown;
  local: unknown;
  remote: unknown;
  collision: boolean;
}
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
export function equal(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (record(a) && record(b)) {
    const keys = Object.keys(a);
    return (
      keys.length === Object.keys(b).length &&
      keys.every((k) => Object.hasOwn(b, k) && equal(a[k], b[k]))
    );
  }
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((v, i) => equal(v, b[i]));
  return false;
}
export function merge<T>(base: T, local: T, remote: T) {
  const fields: FieldDifference[] = [];
  function visit(b: unknown, l: unknown, r: unknown, path: string[]): unknown {
    if (record(l) && record(r) && (record(b) || b === undefined)) {
      const original = record(b) ? b : {};
      const entries = new Set([
        ...Object.keys(original),
        ...Object.keys(l),
        ...Object.keys(r),
      ]);
      return Object.fromEntries(
        [...entries].flatMap((key) => {
          const value = visit(original[key], l[key], r[key], [...path, key]);
          return value === undefined ? [] : [[key, value]];
        }),
      );
    }
    const collision = !equal(l, b) && !equal(r, b) && !equal(l, r);
    fields.push({ path, base: b, local: l, remote: r, collision });
    return equal(l, b) ? r : l;
  }
  const value = visit(base, local, remote, []) as T;
  return { value, fields, collisions: fields.filter((f) => f.collision) };
}
export function replaceField<T>(
  value: T,
  path: readonly string[],
  replacement: unknown,
): T {
  if (!path.length) return replacement as T;
  const [key = "", ...rest] = path;
  const source = value as Record<string, unknown>;
  return Object.fromEntries(
    Object.entries({
      ...source,
      [key]: replaceField(source[key], rest, replacement),
    }).filter(([, v]) => v !== undefined),
  ) as T;
}
