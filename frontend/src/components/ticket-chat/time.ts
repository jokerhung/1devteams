// SQLite stores UTC timestamps without a zone suffix.
export function eventDate(value: string) {
  return new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
}
