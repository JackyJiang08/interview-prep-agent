// The one screen-level state: which screen is showing, which session it
// shows, and the form beneath it. Starting a run and coming back are the
// only two transitions, and neither one touches the form.

import { formReducer, initialForm, type FormAction, type FormState } from "./form";

export interface FlowState {
  screen: "landing" | "run";
  sessionId: string | null;
  form: FormState;
}

export const initialFlow: FlowState = { screen: "landing", sessionId: null, form: initialForm };

export type FlowAction =
  | { kind: "form"; action: FormAction }
  | { kind: "started"; sessionId: string }
  | { kind: "back" };

export function flowReducer(state: FlowState, action: FlowAction): FlowState {
  switch (action.kind) {
    case "form":
      return { ...state, form: formReducer(state.form, action.action) };
    case "started":
      return { ...state, screen: "run", sessionId: action.sessionId };
    case "back":
      return { ...state, screen: "landing", sessionId: null };
  }
}
