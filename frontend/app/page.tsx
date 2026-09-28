"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import SchemaMap from "@/components/SchemaMap";
import { api, ApiError, Template, Validation } from "@/lib/api";

export default function NewDatasetPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [yaml, setYaml] = useState("");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [seed, setSeed] = useState("");
  const [defects, setDefects] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitErrors, setSubmitErrors] = useState<string[]>([]);
  const [loadError, setLoadError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    api
      .templates()
      .then((t) => {
        setTemplates(t);
        if (t.length) {
          setTemplateId(t[0].id);
          setYaml(t[0].yaml);
        }
      })
      .catch(() => setLoadError("Could not reach the backend. Check that it is running."));
  }, []);

  // Validate a moment after the user stops typing.
  useEffect(() => {
    if (!yaml) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      api.validate(yaml).then(setValidation).catch(() => setValidation(null));
    }, 400);
    return () => clearTimeout(timer.current);
  }, [yaml]);

  const pickTemplate = (id: string) => {
    setTemplateId(id);
    const t = templates.find((x) => x.id === id);
    if (t) setYaml(t.yaml);
  };

  const generate = async () => {
    setBusy(true);
    setSubmitErrors([]);
    try {
      const run = await api.createRun(yaml, seed.trim() === "" ? null : Number(seed), defects);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      const err = e as ApiError;
      setSubmitErrors(err.details?.length ? err.details : [err.message]);
      setBusy(false);
    }
  };

  const seedInvalid = seed.trim() !== "" && !/^\d+$/.test(seed.trim());
  const canGenerate = !!validation?.valid && !busy && !seedInvalid;

  return (
    <div>
      <h1>Describe a company, get its data</h1>
      <p className="lede">
        Write the tables you need in the editor. SynthCorp fills them with connected records: every invoice belongs to a real customer, and customers who leave
        raise more support tickets first.
      </p>

      {loadError && <p className="status-bad">{loadError}</p>}

      <div className="workspace">
        <section className="panel" aria-label="Schema editor">
          <div className="panel-head">
            <strong>Schema</strong>
            <label className="field">
              Start from
              <select className="select" value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea className="editor" value={yaml} onChange={(e) => setYaml(e.target.value)} spellCheck={false} aria-label="Schema in YAML" />
          <div className="status-line" aria-live="polite">
            {!validation ? (
              <span className="muted">Checking the schema…</span>
            ) : validation.valid ? (
              <span className="status-ok">Schema is valid. {validation.plan?.tables.length} tables will be generated in the order shown.</span>
            ) : (
              <ul className="errors">
                {validation.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="panel" aria-label="Schema map">
          <div className="panel-head">
            <strong>How the tables connect</strong>
          </div>
          <div className="panel-body">
            <SchemaMap plan={validation?.valid ? validation.plan : null} />
          </div>
        </section>
      </div>

      <div className="actions">
        <label className="field">
          Seed
          <input type="number" min={0} placeholder="from schema" value={seed} onChange={(e) => setSeed(e.target.value)} aria-invalid={seedInvalid} />
        </label>
        <label className="field">
          <input type="checkbox" checked={defects} onChange={(e) => setDefects(e.target.checked)} />
          Damage a few rows so I can see the quality checks catch them
        </label>
        <button className="btn" onClick={generate} disabled={!canGenerate}>
          {busy ? "Starting…" : "Generate data"}
        </button>
      </div>
      {submitErrors.length > 0 && (
        <ul className="errors" style={{ marginTop: 14 }}>
          {submitErrors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
