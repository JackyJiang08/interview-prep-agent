// The landing page's collapsed sections. All start closed so a first
// visitor meets the form before anything else; opening one never closes
// another. The state is a plain value so
// the transitions can be tested without a browser.

export type Section = "advanced" | "demos" | "preview";

export type DisclosureState = Record<Section, boolean>;

export const initialDisclosure: DisclosureState = {
  advanced: false,
  demos: false,
  preview: false,
};

export type DisclosureAction =
  | { kind: "toggle"; section: Section }
  | { kind: "open"; section: Section };

export function disclosureReducer(
  state: DisclosureState,
  action: DisclosureAction,
): DisclosureState {
  switch (action.kind) {
    case "toggle":
      return { ...state, [action.section]: !state[action.section] };
    case "open":
      return state[action.section] ? state : { ...state, [action.section]: true };
  }
}
