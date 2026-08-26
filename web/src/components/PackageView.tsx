import type { ReactNode } from "react";
import { useRef, useState } from "react";

import type {
  EvidenceItem,
  PrepPackage,
  Requirement,
  ResearchFinding,
} from "../types";

const SRC_TOKEN = /\bSRC-\d{3,}\b/g;

export function PackageView({
  prepPackage,
  evidence,
  research = [],
}: {
  prepPackage: PrepPackage;
  evidence: EvidenceItem[];
  research?: ResearchFinding[];
}) {
  const [openItem, setOpenItem] = useState<EvidenceItem | null>(null);
  const [openFinding, setOpenFinding] = useState<ResearchFinding | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const byId = new Map(evidence.map((item) => [item.id, item]));
  const findingsById = new Map(research.map((item) => [item.finding_id, item]));
  const requirements = new Map(
    prepPackage.requirements.map((item) => [item.id, item]),
  );

  const open = (evidenceId: string) => {
    const item = byId.get(evidenceId);
    if (item === undefined) return;
    setOpenFinding(null);
    setOpenItem(item);
    requestAnimationFrame(() => dialogRef.current?.showModal());
  };
  const openResearch = (findingId: string) => {
    const item = findingsById.get(findingId);
    if (item === undefined) return;
    setOpenItem(null);
    setOpenFinding(item);
    requestAnimationFrame(() => dialogRef.current?.showModal());
  };
  const close = () => {
    dialogRef.current?.close();
    setOpenItem(null);
    setOpenFinding(null);
  };

  // Preparation prose may cite findings inline by identifier; render those
  // tokens as chips that open the finding, leaving the rest of the text as is.
  const withResearchChips = (text: string) => {
    const parts = text.split(SRC_TOKEN);
    const tokens = text.match(SRC_TOKEN) ?? [];
    return parts.flatMap((part, index) => {
      const token = tokens[index];
      const chunk: ReactNode[] = [<span key={`t-${index}`}>{part}</span>];
      if (token !== undefined) {
        chunk.push(
          <button
            key={`c-${index}`}
            type="button"
            className="chip"
            onClick={() => openResearch(token)}
            aria-label={`Open role research ${token}`}
          >
            {token}
          </button>,
        );
      }
      return chunk;
    });
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
                        no supporting evidence: an honest gap
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
        <p>{withResearchChips(prepPackage.strategy.positioning_statement)}</p>
        {prepPackage.strategy.top_priorities.map((item) => (
          <div className="qa" key={`priority-${item.requirement_id}`}>
            <h3>
              <code>{item.requirement_id}</code> {item.preparation_theme}
            </h3>
            <p className="probe">{withResearchChips(item.rationale)}</p>
            <p>{item.evidence_ids.map(chip)}</p>
          </div>
        ))}
        {prepPackage.strategy.risks_to_address.length > 0 && (
          <>
            <h2>Risks: the gaps, kept visible</h2>
            {prepPackage.strategy.risks_to_address.map((risk) => (
              <div className="qa" key={`risk-${risk.requirement_id}`}>
                <h3>
                  <code>{risk.requirement_id}</code> {risk.risk}
                </h3>
                <p className="probe">{withResearchChips(risk.mitigation)}</p>
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
              Probes <code>{question.requirement_id}</code>. Follow-up:{" "}
              {withResearchChips(question.follow_up_probe)}
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

      {research.length > 0 && (
        <section className="package-section" aria-label="Role research">
          <h2>Role research</h2>
          <p className="empty-note">
            Role intelligence gathered for preparation. It informs emphasis and
            question realism; it is never candidate evidence and never supports
            a match.
          </p>
          <p>
            {research.map((item) => (
              <button
                key={item.finding_id}
                type="button"
                className="chip"
                onClick={() => openResearch(item.finding_id)}
                aria-label={`Open role research ${item.finding_id}`}
              >
                {item.finding_id}
              </button>
            ))}
          </p>
        </section>
      )}

      <dialog ref={dialogRef} className="evidence-pop" onClose={close}>
        {openItem !== null && (
          <EvidenceDetail item={openItem} requirements={requirements} onClose={close} />
        )}
        {openFinding !== null && (
          <ResearchDetail finding={openFinding} onClose={close} />
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
            Admitted from a clarification answer. This is the accepted claim:
            what survived the assessment and the admission gates. The raw answer
            stays in the audit record.
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
          <p>Source: {item.source ?? "your evidence"}</p>
        </div>
      )}
      <button className="primary" type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}

function ResearchDetail({
  finding,
  onClose,
}: {
  finding: ResearchFinding;
  onClose: () => void;
}) {
  return (
    <div>
      <h3>
        <code>{finding.finding_id}</code> {finding.title}
      </h3>
      <p>{finding.summary}</p>
      <div className="prov">
        <p>
          Role intelligence, not candidate evidence. It informs what to
          emphasize and how realistic a question sounds. It can never support a
          match or become something the candidate claims.
        </p>
        <p>
          {finding.source_kind === "search"
            ? `Found by search for: ${finding.retrieved_for}`
            : "Provided by the user."}
        </p>
        {finding.url != null && finding.url !== "" && (
          <p>
            <a href={finding.url} rel="noreferrer noopener" target="_blank">
              {finding.url}
            </a>
          </p>
        )}
      </div>
      <button className="primary" type="button" onClick={onClose}>
        Close
      </button>
    </div>
  );
}
