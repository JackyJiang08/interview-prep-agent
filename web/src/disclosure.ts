// The landing page's two collapsed sections. Both start closed so a first
// visitor meets the sample run and the own-posting flow before anything
// else; opening one never closes the other. The state is a plain value so
// the transitions can be tested without a browser.

export type Section = "advanced" | "demos";

export type DisclosureState = Record<Section, boolean>;

export const initialDisclosure: DisclosureState = { advanced: false, demos: false };

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
