export function formatNpr(amount: number): string {
  // Lakh/crore grouping used in Nepal: 1,25,000
  return "NPR " + new Intl.NumberFormat("en-IN").format(amount);
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function humanize(slug: string): string {
  return slug.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
