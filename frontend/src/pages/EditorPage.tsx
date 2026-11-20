import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, Offer } from "../api";
import {
  Campaign,
  Stream,
  addOffer,
  bringBack,
  cancelStream,
  fetchStreams,
  getCampaign,
  pushStream,
  removeOffer,
  searchOffers,
  setPin,
} from "../editorApi";
import "../editor.css";

type Run = (action: () => Promise<unknown>) => Promise<void>;

const KT_URL: string =
  import.meta.env.VITE_KEITARO_URL ?? "https://tlgk.host";

function StreamTitle({ stream }: { stream: Stream }) {
  return (
    <>
      <strong>
        Stream: {stream.name} (#{stream.position})
      </strong>
      {" "}
      <span className="meta">
        filter by {stream.filters || "None"}, stream_id{" "}
        {stream.keitaro_id}, clicks today: {stream.clicks_today}
      </span>
    </>
  );
}

function EmptyStream({ stream }: { stream: Stream }) {
  return (
    <tbody className="stream">
      <tr className="group">
        <td colSpan={5}>
          <StreamTitle stream={stream} />
        </td>
      </tr>
    </tbody>
  );
}

function StreamBlock({
  stream,
  busy,
  run,
}: {
  stream: Stream;
  busy: boolean;
  run: Run;
}) {
  const [query, setQuery] = useState("");
  const [hints, setHints] = useState<Offer[]>([]);
  const [picked, setPicked] = useState<Offer | null>(null);

  async function onQuery(value: string) {
    setQuery(value);
    setPicked(null);
    if (value.trim().length < 2) {
      setHints([]);
      return;
    }
    try {
      setHints(await searchOffers(value.trim()));
    } catch {
      setHints([]);
    }
  }

  function pick(offer: Offer) {
    setPicked(offer);
    setQuery(`${offer.id} ${offer.name}`);
    setHints([]);
  }

  async function onAdd() {
    if (!picked) return;
    await run(() => addOffer(stream.id, picked.id));
    setQuery("");
    setPicked(null);
  }

  return (
    <tbody className={stream.has_changes ? "stream changed" : "stream"}>
      <tr className="group">
        <td colSpan={5}>
          <StreamTitle stream={stream} />
          {stream.has_changes && (
            <span className="group-actions">
              <button
                disabled={busy}
                onClick={() => run(() => pushStream(stream.id))}
              >
                Push to KT
              </button>
              <button
                disabled={busy}
                onClick={() => run(() => cancelStream(stream.id))}
              >
                Cancel
              </button>
            </span>
          )}
        </td>
      </tr>

      {stream.offers.map((o) => {
        const removed = o.status === "removed" || o.is_deleted_unpublished;
        return (
          <tr key={o.id} className={removed ? "offer removed" : "offer"}>
            <td className="name">
              {o.offer_id} {o.name}
              {o.preview_path && (
                <>
                  <br />
                  <a href={o.preview_path} target="_blank" rel="noreferrer">
                    (preview)
                  </a>
                </>
              )}
            </td>
            <td className="share">
              {removed ? 0 : o.share}%{" "}
              <button
                className={o.pinned ? "pin on" : "pin"}
                disabled={busy || removed}
                title="Закрепить долю"
                onClick={() => run(() => setPin(o.id, !o.pinned))}
              >
                📌
              </button>
            </td>
            <td />
            <td />
            <td className="actions">
              {removed ? (
                <button
                  disabled={busy}
                  onClick={() => run(() => bringBack(o.id))}
                >
                  Bring Back
                </button>
              ) : (
                <button
                  disabled={busy}
                  onClick={() => run(() => removeOffer(o.id))}
                >
                  Remove
                </button>
              )}
            </td>
          </tr>
        );
      })}

      <tr>
        <td colSpan={5} className="add-cell">
          <div className="add-row">
            <div className="add-field">
              <input
                value={query}
                onChange={(e) => onQuery(e.target.value)}
                placeholder="Номер или название оффера"
              />
              {hints.length > 0 && (
                <ul className="hints">
                  {hints.map((h) => (
                    <li key={h.id} onClick={() => pick(h)}>
                      {h.id} {h.name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button disabled={busy || !picked} onClick={onAdd}>
              ADD
            </button>
          </div>
        </td>
      </tr>
    </tbody>
  );
}

export default function EditorPage() {
  const { keitaroId = "" } = useParams();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setCampaign(await getCampaign(keitaroId));
  }, [keitaroId]);

  const run = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
        await load();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  useEffect(() => {
    run(async () => undefined);
  }, [run]);

  const streams = campaign?.streams ?? [];
  const withOffers = streams.filter((s) => s.offers.length > 0);
  const empty = streams.filter((s) => s.offers.length === 0);

  return (
    <div className="editor">
      <nav className="crumbs">
        <Link to="/">Campaigns</Link>
        <span className="sep">/</span>
        <span>{campaign ? campaign.name : keitaroId}</span>
        <span className="sep">/</span>
        <span>Keitaro Streams</span>
      </nav>

      <div className="toolbar">
        <button
          disabled={busy}
          onClick={() => run(() => fetchStreams(keitaroId))}
        >
          FETCH STREAMS FROM KT
        </button>
        <a
          className="btn"
          href={`${KT_URL}/admin/#!/campaign/${keitaroId}`}
          target="_blank"
          rel="noreferrer"
        >
          VIEW IN KT
        </a>
      </div>

      {error && <p className="error">{error}</p>}

      <table className="streams">
        <colgroup>
          <col style={{ width: "11%" }} />
          <col style={{ width: "7.5%" }} />
          <col style={{ width: "45.5%" }} />
          <col style={{ width: "23%" }} />
          <col style={{ width: "13%" }} />
        </colgroup>
        <thead>
          <tr>
            <th />
            <th>Share</th>
            <th>Stats</th>
            <th>Trends</th>
            <th>Actions</th>
          </tr>
        </thead>
        {withOffers.map((s) => (
          <StreamBlock key={s.id} stream={s} busy={busy} run={run} />
        ))}
        {empty.map((s) => (
          <EmptyStream key={s.id} stream={s} />
        ))}
      </table>
    </div>
  );
}