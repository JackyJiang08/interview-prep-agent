// Everything the visitor typed or loaded on the landing page, as one value
// owned above the page itself. A run is a detour: the form is still here
// when the run ends, fails, or is abandoned, exactly as it was left.

import {
  disclosureReducer,
  initialDisclosure,
  type DisclosureState,
  type Section,
} from "./disclosure";
import type { EvidenceFormat } from "./inputs";

export type Provider = "gemini" | "azure" | "anthropic";

// A loaded resume: where it came from, and the text that will be used.
export interface Resume {
  filename: string | null;
  text: string;
}

export interface FormState {
  jdText: string;
  resume: Resume;
  override: EvidenceFormat | null;
  apiKey: string;
  provider: Provider;
  roundText: string;
  researchText: string;
  searchKey: string;
  azureEndpoint: string;
  azureDeployment: string;
  open: DisclosureState;
}

export const initialForm: FormState = {
  jdText: "",
  resume: { filename: null, text: "" },
  override: null,
  apiKey: "",
  provider: "gemini",
  roundText: "",
  researchText: "",
  searchKey: "",
  azureEndpoint: "",
  azureDeployment: "",
  open: initialDisclosure,
};

export type FormPatch = Partial<Omit<FormState, "open">>;

export type FormAction = { kind: "set"; patch: FormPatch } | { kind: "toggle"; section: Section };

export function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.kind) {
    case "set":
      return { ...state, ...action.patch };
    case "toggle":
      return {
        ...state,
        open: disclosureReducer(state.open, { kind: "toggle", section: action.section }),
      };
  }
}
