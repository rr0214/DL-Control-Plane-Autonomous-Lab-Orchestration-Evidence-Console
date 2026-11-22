// Dates in example data are fixed UTC times; live times come from the API in UTC. Shown the same way everywhere.
const DATE = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const parse = (iso: string) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
export const formatDay = (iso: string) => DATE.format(parse(iso));
export const formatDateTime = (iso: string) => `${DATE_TIME.format(parse(iso))} UTC`;
