const BASE: string = import.meta.env.VITE_API_URL ?? "http://localhost:8012";

export class ApiError extends Error {
  step: string | null;

  constructor(message: string, step: string | null) {
    super(message);
    this.step = step;
  }
}




function formatError(raw: string): string {
  try {
    const data = JSON.parse(raw) as Record<string, string[]>;
    const used = [...(data.name ?? []), ...(data.alias ?? [])].some((m) =>
      m.includes("already used"),
    );
    if (used) return "Кампания с таким названием уже существует";
    return Object.entries(data)
      .map(([field, msgs]) => `${field}: ${msgs.join(", ")}`)
      .join("\n");
  } catch {
    return raw;
  }
}




export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Сервер недоступен", null);
  }
  if (!response.ok) {
    const body: { error?: string; step?: string } | null = await response
      .json()
      .catch(() => null);
    throw new ApiError(
      formatError(body?.error ?? `Ошибка ${response.status}`),
      body?.step ?? null,
    );
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
}

export interface Offer {
  id: number;
  name: string;
}

export interface CreateCampaignRequest {
  name: string;
  geo: string;
  offer_id: number;
}

export interface CreateCampaignResponse {
  campaign_id: number;
  name: string;
}

export const getOffers = () => request<Offer[]>("/offers");

export const getCountries = () => request<string[]>("/countries");

export const createCampaign = (data: CreateCampaignRequest) =>
  request<CreateCampaignResponse>("/campaigns", {
    method: "POST",
    body: JSON.stringify(data),
  });