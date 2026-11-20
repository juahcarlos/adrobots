import { Offer, request } from "./api";

export interface StreamOffer {
  id: number;
  offer_id: number;
  name: string;
  preview_path: string;
  share: number;
  pinned: boolean;
  status: string;
  is_unpublished: boolean;
  is_deleted_unpublished: boolean;
}

export interface Stream {
  id: number;
  keitaro_id: number;
  name: string;
  position: number;
  filters: string;
  clicks_today: number;
  has_changes: boolean;
  offers: StreamOffer[];
}

export interface Campaign {
  id: number;
  keitaro_id: number;
  name: string;
  streams: Stream[];
}

export const getCampaign = (keitaroId: string) =>
  request<Campaign>(`/editor/campaigns/${keitaroId}`);

export const fetchStreams = (keitaroId: string) =>
  request<unknown>(`/editor/campaigns/${keitaroId}/fetch`, {
    method: "POST",
  });

export const searchOffers = (q: string) =>
  request<Offer[]>(`/offers/search?q=${encodeURIComponent(q)}`);

export const addOffer = (streamId: number, offerId: number) =>
  request<unknown>(`/editor/streams/${streamId}/offers`, {
    method: "POST",
    body: JSON.stringify({ offer_id: offerId }),
  });

export const removeOffer = (linkId: number) =>
  request<unknown>(`/editor/stream-offers/${linkId}/remove`, {
    method: "POST",
  });

export const bringBack = (linkId: number) =>
  request<unknown>(`/editor/stream-offers/${linkId}/bring-back`, {
    method: "POST",
  });

export const setPin = (linkId: number, pinned: boolean) =>
  request<unknown>(`/editor/stream-offers/${linkId}/pin`, {
    method: "PUT",
    body: JSON.stringify({ pinned }),
  });

export const pushStream = (streamId: number) =>
  request<unknown>(`/editor/streams/${streamId}/push`, { method: "POST" });

export const cancelStream = (streamId: number) =>
  request<unknown>(`/editor/streams/${streamId}/cancel`, { method: "POST" });