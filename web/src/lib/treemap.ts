export interface TreeItem<T> {
  value: number
  item: T
}

export interface TreeRect<T> {
  item: T
  x: number
  y: number
  w: number
  h: number
}

/** Slice-and-dice treemap: tile area is proportional to value. Coordinates are percentages (0-100). */
export function treemap<T>(items: TreeItem<T>[], x = 0, y = 0, w = 100, h = 100): TreeRect<T>[] {
  const sorted = [...items].filter((i) => i.value > 0).sort((a, b) => b.value - a.value)
  if (sorted.length === 0) return []
  if (sorted.length === 1) return [{ item: sorted[0].item, x, y, w, h }]
  const total = sorted.reduce((s, i) => s + i.value, 0)
  let acc = 0
  let k = 0
  while (k < sorted.length - 1 && acc + sorted[k].value < total / 2) acc += sorted[k++].value
  k = Math.max(1, k)
  const first = sorted.slice(0, k)
  const rest = sorted.slice(k)
  const share = first.reduce((s, i) => s + i.value, 0) / total
  return w >= h
    ? [...treemap(first, x, y, w * share, h), ...treemap(rest, x + w * share, y, w * (1 - share), h)]
    : [...treemap(first, x, y, w, h * share), ...treemap(rest, x, y + h * share, w, h * (1 - share))]
}
