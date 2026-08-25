import { useRef, useState } from "react";

import type { EvidenceItem, PrepPackage, Requirement } from "../types";

export function PackageView({
  prepPackage,
  evidence,
}: {
  prepPackage: PrepPackage;
  evidence: EvidenceItem[];
}) {
  const [openItem, setOpenItem] = useState<EvidenceItem | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const byId = new Map(evidence.map((item) => [item.id, item]));
  const requirements = new Map(
    prepPackage.requirements.map((item) => [item.id, item]),
  );

  const open = (evidenceId: string) => {
    const item = byId.get(evidenceId);
    if (item === undefined) return;
    setOpenItem(item);
    requestAnimationFrame(() => dialogRef.current?.showModal());
  };
  const close = () => {
    dialogRef.current?.close();
    setOpenItem(null);
  };

  const chip = (evidenceId: string) => (
    <button
      key={evidenceId}
      type="button"
      className="chip"
      onClick={() => open(evidenceId)}
      aria-label={`Open evidence ${evidenceId}`}
    >
      {evidenceId}
    </button>
  );

  return (
    <div aria-label="Preparation package">
      <section className="package-section" aria-label="Coverage">
        <h2>Requirements and coverage</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Requirement</th>
              <th scope="col">Coverage</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {prepPackage.matches.map((match) => {
              const requirement = requirements.get(match.requirement_id);
              const coverage = match.coverage ?? "GAP";
              return (
                <tr key={match.requirement_id}>
                  <td>
                    <code>{match.requirement_id}</code>{" "}
                    {requirement?.text ?? ""}
                  </td>
                  <td>
                    <span className={`coverage ${coverage.toLowerCase()}`}>
                      {coverage}
                    </span>
                  </td>
                  <td>
                    {match.matches.length === 0 ? (
                      <span className="empty-note">
                        no supporting evidence - an honest gap
                      </span>
                    ) : (
                      match.matches.map((item) => chip(item.evidence_id))
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="package-section" aria-label="Focus areas">
        <h2>Where to spend preparation time</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Priority</th>
              <th scope="col">Requirement</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {prepPackage.focus_areas.map((area) => (
              <tr key={area.requirement_id}>
                <td>
                  <code>{area.priority}</code>
                </td>
                <td>
                  <code>{area.requirement_id}</code>{" "}
                  <span className={`coverage ${area.coverage.toLowerCase()}`}>
                    {area.coverage}
                  </span>
                </td>
                <td>
                  {area.preparation_action}
                  <div className="empty-note">{area.reason}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="package-section" aria-label="Strategy">
        <h2>Strategy</h2>
        <p>{prepPackage.strategy.positioning_statement}</p>
        {prepPackage.strategy.top_priorities.map((item) => (
          <div className="qa" key={`priority-${item.requirement_id}`}>
            <h3>
              <code>{item.requirement_id}</code> {item.preparation_theme}
            </h3>
            <p className="probe">{item.rationale}</p>
            <p>{item.evidence_ids.map(chip)}</p>
          </div>
        ))}
        {prepPackage.strategy.risks_to_address.length > 0 && (
          <>
            <h2>Risks - the gaps, kept visible</h2>
            {prepPackage.strategy.risks_to_address.map((risk) => (
              <div className="qa" key={`risk-${risk.requirement_id}`}>
                <h3>
                  <code>{risk.requirement_id}</code> {risk.risk}
                </h3>
                <p className="probe">{risk.mitigation}</p>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="package-section" aria-label="Practice questions">
        <h2>Practice questions</h2>
        {prepPackage.mock_questions.map((question, index) => (
          <div className="qa" key={index}>
            <h3>{question.question}</h3>
            <p className="probe">
              Probes <code>{question.requirement_id}</code> - follow-up:{" "}
              {question.follow_up_probe}
            </p>
            <p>{question.evidence_ids.map(chip)}</p>
            <ul>
              {question.answer_outline.map((line, outlineIndex) => (
                <li key={outlineIndex}>{line}</li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <dialog ref={dialogRef} className="evidence-pop" onClose={close}>
        {openItem !== null && (
          <EvidenceDetail item={openItem} requirements={requirements} onClose={close} />
        )}
      </dialog>
    </div>
  );
}

function EvidenceDetail({
  item,
  requirements,
  onClose,
}: {
  item: EvidenceItem;
  requirements: Map<string, Requirement>;
  onClose: () => void;
}) {
  const addressed =
    item.addresses_requirement_id != null
      ? requirements.get(item.addresses_requirement_id)
      : undefined;
  return (
    <div>
      <h3>
        <code>{item.id}</code>
      </h3>
      <p>{item.summary}</p>
      {item.id.startsWith("CL-") ? (
        <div className="prov">
          <p>
            Admitted from a clarification answer. This is the accepted claim -
            what survived the assessment and the admission gates - not the raw
            answer, which stays in the audit record.
          </p>
          {item.question != null && <p>Question asked: {item.question}</p>}
          {item.addresses_requirement_id != null && (
            <p>
              Addresses <code>{item.addresses_requirement_id}</code>
              {addressed !== undefined && <>: {addressed.text}</>}
            </p>
          )}
        </div>
      ) : (
        <div className="prov">
          {item.skills != null && item.skills.length > 0 && (
            <p>Skills: {item.skills.join(", ")}</p>
          )}
          {item.impact != null && <p>Impact: {item.impact}</p>}
          <p>Source: {item.source ?? "evidence corpus"}</p>
        </div>
      )}
      <button className="primary" type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}
