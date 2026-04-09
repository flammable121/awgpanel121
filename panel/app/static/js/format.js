export function formatBytes(value) {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let size = Number(value) || 0;
  let unit = units.shift();
  while (size >= 1024 && units.length) {
    size /= 1024;
    unit = units.shift();
  }
  if (unit === "GB" && size >= 1024) {
    size /= 1024;
    unit = "TB";
  }
  if (unit === "B") {
    return `${Math.round(size)} ${unit}`;
  }
  return `${size.toFixed(1)} ${unit}`;
}

export function formatDuration(seconds) {
  let remaining = Math.max(0, Math.floor(seconds || 0));
  const days = Math.floor(remaining / 86400);
  remaining %= 86400;
  const hours = Math.floor(remaining / 3600);
  remaining %= 3600;
  const minutes = Math.floor(remaining / 60);
  const parts = [];
  if (days) parts.push(`${days}д`);
  if (hours) parts.push(`${hours}ч`);
  parts.push(`${minutes}м`);
  return parts.join(" ");
}
