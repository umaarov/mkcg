export const nf0 = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : Math.round(v).toLocaleString("en-US").replace(/,/g, " ");

/** UZS in compact "mln" form for tight spaces. */
export function mln(v: number | null | undefined, lang: string = "en") {
  if (v == null || Number.isNaN(v)) return "—";
  const unit = lang === "ru" ? "млн" : lang === "uz" ? "mln" : "M";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)} ${lang === "ru" ? "млрд" : lang === "uz" ? "mlrd" : "B"}`;
  return `${(v / 1e6).toFixed(a >= 1e8 ? 0 : 1)} ${unit}`;
}
export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
export const x2 = (v: number | null | undefined) => (v == null ? "—" : Number(v).toFixed(2));
export const dt = (s: string) => new Date(s + (s.endsWith("Z") ? "" : "Z")).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export const CATEGORY_LABEL: Record<string, [string, string, string]> = {
  sales_receipt: ["Customer receipts", "Mijoz to'lovlari", "Поступления от клиентов"],
  cash_deposit: ["Cash deposits", "Naqd kiritish", "Взносы наличных"],
  supplier_payment: ["Supplier payments", "Yetkazuvchilarga to'lov", "Платежи поставщикам"],
  payroll: ["Payroll", "Ish haqi", "Зарплата"],
  rent: ["Rent", "Ijara", "Аренда"],
  utilities: ["Utilities", "Kommunal", "Коммунальные"],
  tax: ["Tax", "Soliq", "Налоги"],
  loan_payment: ["Loan payments", "Kredit to'lovlari", "Платежи по кредитам"],
  cash_withdrawal: ["Cash withdrawals", "Naqd yechish", "Снятие наличных"],
  owner_transfer: ["Owner transfers", "Ta'sischiga", "Переводы владельцу"],
  owner_inflow: ["Owner loans in", "Ta'sischi qarzi", "Займы владельца"],
  loan_disbursement: ["Loans received", "Olingan kreditlar", "Полученные кредиты"],
  bank_fee: ["Bank fees", "Bank komissiyasi", "Комиссии банка"],
};
export const catLabel = (c: string, lang: string) => (CATEGORY_LABEL[c] ?? [c, c, c])[lang === "en" ? 0 : lang === "uz" ? 1 : 2];
