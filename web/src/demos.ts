// Display names for the committed scenarios. The server lists them by
// internal id with the description the regression suite wrote; a viewer
// needs a title that says what they will see. The id stays visible as the
// subtitle so an engineer can find the scenario in the suite.

export const SAMPLE_DEMO_ID = "mixed-clarifications";
export const SAMPLE_DISPLAY_NAME = "Sample run: a data analyst posting";

const DISPLAY_TITLES: Record<string, string> = {
  "complete-profile-no-round": "A fully covered profile: no questions, straight to a package",
  "round-guidance-comparison": "The same evidence, prepared for a named interview round",
  "mixed-clarifications": "Three answers: one admitted, one rejected, one admitted",
  "all-clarifications-rejected": "Every answer rejected, and the package still valid",
  "wrong-target-assessment": "An assessment that names the wrong requirement",
  "research-informed-rejections": "Role research shaping the strategy, never the matching",
};

export function displayTitle(demoId: string): string {
  return DISPLAY_TITLES[demoId] ?? demoId;
}
