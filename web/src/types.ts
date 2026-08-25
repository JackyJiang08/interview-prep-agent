// Domain types mirroring the server's business models, as serialized over
// the wire. Optional fields are populated by whichever path could honestly
// supply them, exactly as in the package contracts.

export interface EvidenceItem {
  id: string;
  summary: string;
  skills?: string[];
  impact?: string | null;
  source?: string | null;
  addresses_requirement_id?: string | null;
  question?: string | null;
}

export interface Requirement {
  id: string;
  text: string;
  importance?: number | null;
  category?: string | null;
  requirement_type?: string | null;
  source_quote?: string | null;
}

export interface EvidenceCitation {
  evidence_id: string;
  score: number;
  overlapping_terms?: string[];
}

export type Coverage = "FULL" | "PARTIAL" | "GAP";

export interface RequirementMatch {
  requirement_id: string;
  status: string;
  coverage?: Coverage | null;
  matches: EvidenceCitation[];
  explanation?: string | null;
  confidence?: number | null;
  method: string;
}

export interface FocusArea {
  requirement_id: string;
  coverage: Coverage;
  priority: number;
  preparation_action: string;
  reason: string;
}

export interface StrategyItem {
  requirement_id: string;
  evidence_ids: string[];
  preparation_theme: string;
  rationale: string;
}

export interface StoryPlan {
  requirement_id: string;
  evidence_ids: string[];
  story_to_prepare: string;
}

export interface RiskItem {
  requirement_id: string;
  risk: string;
  mitigation: string;
}

export interface InterviewStrategy {
  top_priorities: StrategyItem[];
  positioning_statement: string;
  stories_to_prepare: StoryPlan[];
  risks_to_address: RiskItem[];
}

export interface MockQuestion {
  question: string;
  requirement_id: string;
  capability_tested: string;
  evidence_ids: string[];
  follow_up_probe: string;
  answer_outline: string[];
}

export interface PrepPackage {
  requirements: Requirement[];
  matches: RequirementMatch[];
  focus_areas: FocusArea[];
  strategy: InterviewStrategy;
  mock_questions: MockQuestion[];
}

export interface Demo {
  demo_id: string;
  description: string;
  profile: string;
  round_text: string;
  suggested_answers: Record<string, string>;
}
