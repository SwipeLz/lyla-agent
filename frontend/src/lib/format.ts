const DASH = "—";

const idCurrency = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

const idDateTime = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Jakarta",
});

const idDate = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeZone: "Asia/Jakarta",
});

export const formatCurrencyIDR = (
  value: number | null | undefined,
): string => {
  if (value == null || Number.isNaN(value)) return DASH;
  return idCurrency.format(value);
};

export const parseIsoUtc = (iso: string | null | undefined): Date | null => {
  if (!iso) return null;
  const hasTz = /Z|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
};

const tryDate = (iso: string | null | undefined): Date | null => parseIsoUtc(iso);

export const formatDateTime = (iso: string | null | undefined): string => {
  const d = tryDate(iso);
  return d ? idDateTime.format(d) : DASH;
};

export const formatDate = (iso: string | null | undefined): string => {
  const d = tryDate(iso);
  return d ? idDate.format(d) : DASH;
};

export const formatStatus = (value: string | null | undefined): string => {
  if (!value) return DASH;
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
};
