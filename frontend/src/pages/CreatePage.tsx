import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "../create.css";

import {
  ApiError,
  CreateCampaignResponse,
  Offer,
  createCampaign,
  getCountries,
  getOffers,
} from "../api";

export default function CreatePage() {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [geo, setGeo] = useState("");
  const [offerId, setOfferId] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateCampaignResponse | null>(null);

  useEffect(() => {
    Promise.all([getOffers(), getCountries()])
      .then(([o, c]) => {
        setOffers(o);
        setCountries(c);
      })
      .catch((e: ApiError) => setError(e.message));
  }, []);

  const shown = offers
    .filter((o) =>
      `${o.id} ${o.name}`.toLowerCase().includes(filter.toLowerCase()),
    )
    .slice(0, 20);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const data = await createCampaign({
        name,
        geo,
        offer_id: Number(offerId),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="nc-wrap">
      <form onSubmit={onSubmit}>
        <table className="nc">
          <colgroup>
            <col style={{ width: 19 }} />
            <col style={{ width: 62 }} />
            <col style={{ width: 176 }} />
            <col style={{ width: 32 }} />
          </colgroup>
          <tbody>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
            <tr className="head">
              <td />
              <td colSpan={3}>New campaign</td>
            </tr>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
            <tr>
              <td />
              <td className="label">Name</td>
              <td className="field">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="имя кампании"
                />
              </td>
              <td />
            </tr>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
            <tr>
              <td />
              <td className="label">Geo</td>
              <td className="field">
                <select
                  value={geo}
                  onChange={(e) => setGeo(e.target.value)}
                >
                  <option value="">MX,AU,RO,...</option>
                  {countries.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </td>
              <td />
            </tr>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
            <tr>
              <td />
              <td className="label">Offer</td>
              <td className="field">
                <textarea
                  rows={2}
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                    setOfferId("");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.preventDefault();
                  }}
                  placeholder={
                    "поиск по офферам с\nавтокомплитом"
                  }
                />
                {filter && !offerId && shown.length > 0 && (
                  <ul className="hints">
                    {shown.map((o) => (
                      <li
                        key={o.id}
                        onClick={() => {
                          setOfferId(String(o.id));
                          setFilter(`${o.id} ${o.name}`);
                        }}
                      >
                        {o.id} {o.name}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              <td />
            </tr>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
            <tr>
              <td />
              <td colSpan={3}>
                <button type="submit" disabled={loading}>
                  {loading ? "Создаём..." : "Create"}
                </button>
              </td>
            </tr>
            <tr className="sp">
              <td colSpan={4} />
            </tr>
          </tbody>
        </table>
      </form>

      <div className="nc-msg">
        {error && <p className="error">{error}</p>}
        {result && (
          <p>
            Кампания создана: #{result.campaign_id} {result.name}
            <br />
            <Link
              className="open-editor"
              to={`/campaigns/${result.campaign_id}`}
            >
              Открыть редактор
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}