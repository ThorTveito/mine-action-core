import { useCallback, useEffect, useState } from "react";
import { createAccident, createSession, fetchAccidents, fetchSessions } from "./api";
import { useAuth } from "./AuthContext";
import type {
  Accident,
  AccidentActivity,
  ItemCategory,
  MapFocus,
  RiskEducationSession,
  Sex,
  VictimInput,
  VictimOutcome,
} from "./types";

const ACTIVITIES: AccidentActivity[] = [
  "farming", "herding", "travelling", "collecting", "playing", "handling", "demining", "other", "unknown",
]; // prettier-ignore
const ITEMS: Record<ItemCategory, string> = {
  ap_mine: "Anti-personnel mine",
  av_mine: "Anti-vehicle mine",
  uxo: "UXO",
  submunition: "Cluster submunition",
  ied: "IED",
  unknown: "Unknown",
};
const today = () => new Date().toISOString().slice(0, 10);
const blankVictim = (): VictimInput => ({ sex: "unknown", age: null, outcome: "injured", is_deminer: false });

function Coordinates({ lat, lon, setLat, setLon }: { lat: string; lon: string; setLat: (v: string) => void; setLon: (v: string) => void }) {
  return (
    <div className="two">
      <label>
        Latitude
        <input inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="61.55" />
      </label>
      <label>
        Longitude
        <input inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="8.55" />
      </label>
    </div>
  );
}

export function VictimRows({ victims, onChange }: { victims: VictimInput[]; onChange: (v: VictimInput[]) => void }) {
  const set = (i: number, patch: Partial<VictimInput>) => onChange(victims.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  return (
    <div className="victims">
      {victims.map((v, i) => (
        <div key={i} className="victim-row">
          <select value={v.sex} onChange={(e) => set(i, { sex: e.target.value as Sex })} aria-label="Sex">
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="unknown">Sex unknown</option>
          </select>
          <input
            type="number"
            min="0"
            max="120"
            placeholder="Age"
            value={v.age ?? ""}
            onChange={(e) => set(i, { age: e.target.value === "" ? null : Number(e.target.value) })}
            aria-label="Age"
          />
          <select value={v.outcome} onChange={(e) => set(i, { outcome: e.target.value as VictimOutcome })} aria-label="Outcome">
            <option value="injured">Injured</option>
            <option value="killed">Killed</option>
          </select>
          <label className="inline-check">
            <input type="checkbox" checked={v.is_deminer} onChange={(e) => set(i, { is_deminer: e.target.checked })} />
            deminer
          </label>
          <button className="small" onClick={() => onChange(victims.filter((_, j) => j !== i))} aria-label="Remove victim">
            ✕
          </button>
        </div>
      ))}
      <button className="small" onClick={() => onChange([...victims, blankVictim()])}>
        + Victim
      </button>
      <p className="muted small-line">No names are recorded: sex, age and outcome are enough for reporting.</p>
    </div>
  );
}

function AccidentForm({ onSaved }: { onSaved: () => void }) {
  const [date, setDate] = useState(today());
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [item, setItem] = useState<ItemCategory | "">("");
  const [activity, setActivity] = useState<AccidentActivity>("unknown");
  const [description, setDescription] = useState("");
  const [victims, setVictims] = useState<VictimInput[]>([blankVictim()]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const save = async () => {
    setMsg(null);
    try {
      const a = await createAccident({
        occurred_on: date,
        lat: Number(lat),
        lon: Number(lon),
        item_category: item || null,
        activity,
        description,
        victims,
      });
      setMsg({ ok: true, text: `Saved as ${a.code}${a.hazard_code ? `, linked to ${a.hazard_code}` : ", no hazard within 500 m"}.` });
      setVictims([blankVictim()]);
      setDescription("");
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section className="card field-form">
      <h2>Record an accident</h2>
      <label>
        Date
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <Coordinates lat={lat} lon={lon} setLat={setLat} setLon={setLon} />
      <div className="two">
        <label>
          Item
          <select value={item} onChange={(e) => setItem(e.target.value as ItemCategory | "")}>
            <option value="">Unknown</option>
            {(Object.keys(ITEMS) as ItemCategory[]).map((c) => (
              <option key={c} value={c}>
                {ITEMS[c]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Activity at the time
          <select value={activity} onChange={(e) => setActivity(e.target.value as AccidentActivity)}>
            {ACTIVITIES.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Victims
        <VictimRows victims={victims} onChange={setVictims} />
      </label>
      <label>
        Notes
        <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {msg && <p className={msg.ok ? "success" : "error"}>{msg.text}</p>}
      <button className="primary" disabled={!lat || !lon} onClick={save}>
        Save accident
      </button>
    </section>
  );
}

function SessionForm({ onSaved }: { onSaved: () => void }) {
  const [date, setDate] = useState(today());
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [org, setOrg] = useState("Delta Mine Action NGO");
  const [counts, setCounts] = useState({ girls: "", boys: "", women: "", men: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const n = (v: string) => Number(v) || 0;

  const save = async () => {
    setMsg(null);
    try {
      const s = await createSession({
        held_on: date,
        lat: Number(lat),
        lon: Number(lon),
        organisation: org,
        girls: n(counts.girls),
        boys: n(counts.boys),
        women: n(counts.women),
        men: n(counts.men),
        notes: null,
      });
      setMsg({ ok: true, text: `Saved as ${s.code}: ${s.total} people.` });
      setCounts({ girls: "", boys: "", women: "", men: "" });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section className="card field-form">
      <h2>Record a risk education session</h2>
      <label>
        Date
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <Coordinates lat={lat} lon={lon} setLat={setLat} setLon={setLon} />
      <label>
        Organisation
        <input value={org} onChange={(e) => setOrg(e.target.value)} />
      </label>
      <div className="four">
        {(["girls", "boys", "women", "men"] as const).map((k) => (
          <label key={k}>
            {k[0].toUpperCase() + k.slice(1)}
            <input type="number" min="0" inputMode="numeric" value={counts[k]} onChange={(e) => setCounts({ ...counts, [k]: e.target.value })} />
          </label>
        ))}
      </div>
      {msg && <p className={msg.ok ? "success" : "error"}>{msg.text}</p>}
      <button className="primary" disabled={!lat || !lon || !org.trim()} onClick={save}>
        Save session
      </button>
    </section>
  );
}

export default function CasualtiesPage({ onShow }: { onShow: (f: Omit<MapFocus, "nonce">) => void }) {
  const { can } = useAuth();
  const [accidents, setAccidents] = useState<Accident[] | null>(null);
  const [sessions, setSessions] = useState<RiskEducationSession[] | null>(null);

  const load = useCallback(() => {
    fetchAccidents()
      .then(setAccidents)
      .catch(() => setAccidents([]));
    fetchSessions()
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="page wide">
      <h1>Accidents and risk education</h1>
      <p className="muted">
        Accident records are visible to staff only; the public dashboard shows totals by sex and age. Each accident is
        linked to the hazard it happened in, or the nearest one within 500 m.
      </p>
      {can("write") && (
        <div className="two-col even">
          <AccidentForm onSaved={load} />
          <SessionForm onSaved={load} />
        </div>
      )}
      <div className="two-col even">
        <section className="card">
          <h3>Accidents ({accidents?.length ?? "…"})</h3>
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Date</th>
                <th>Activity</th>
                <th className="num">Killed</th>
                <th className="num">Injured</th>
                <th>Hazard</th>
              </tr>
            </thead>
            <tbody>
              {accidents?.slice(0, 60).map((a) => (
                <tr key={a.id}>
                  <td>
                    <button className="link" onClick={() => onShow({ hazardId: a.hazard_id ?? undefined, lon: a.lon, lat: a.lat })}>
                      {a.code}
                    </button>
                  </td>
                  <td>{a.occurred_on}</td>
                  <td>{a.activity}</td>
                  <td className="num">{a.killed}</td>
                  <td className="num">{a.injured}</td>
                  <td>{a.hazard_code ?? <span className="muted">none nearby</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="card">
          <h3>Risk education sessions ({sessions?.length ?? "…"})</h3>
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Date</th>
                <th>Region</th>
                <th className="num">Girls</th>
                <th className="num">Boys</th>
                <th className="num">Women</th>
                <th className="num">Men</th>
              </tr>
            </thead>
            <tbody>
              {sessions?.slice(0, 60).map((s) => (
                <tr key={s.id}>
                  <td>{s.code}</td>
                  <td>{s.held_on}</td>
                  <td>{s.region ?? "–"}</td>
                  <td className="num">{s.girls}</td>
                  <td className="num">{s.boys}</td>
                  <td className="num">{s.women}</td>
                  <td className="num">{s.men}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
