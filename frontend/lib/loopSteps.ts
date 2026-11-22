// The 10 loop steps shown to people, how they group into 4 phases, and what kind of thing runs each one.
// Checked against the code (backend/app/graph.py has 7 LangGraph nodes; release is a separate API route):
//   Targets               -> graph node target_check (plain code: lab limits)
//   Setup agent           -> graph node setup_agent (Claude; mock reply without a key)
//   Optimizer, prediction -> graph nodes optimizer + prediction_model (a fixed table and a fixed lookup, no trained model)
//   Safety gate           -> graph node policy_kernel (plain code)
//   Scientist review      -> inside graph node triage_and_hitl (interrupt(): a person decides)
//   Make and measure      -> inside triage_and_hitl (workcell.py and measure.py simulate synthesis and measurement)
//   Measurement check     -> inside triage_and_hitl (check.py, plain code)
//   Diagnosis             -> graph node diagnose_flagged (Claude proposes; action_gate.py, plain code, decides)
//   Save and learn        -> SQLite writes after each step; history.py feeds them to the next setup agent (no retraining)
//   Release               -> API route /api/samples/{id}/release (a person decides; release.py applies the rules)

export type StepTag = "Code" | "AI agent" | "ML simulated" | "Simulated" | "Person";

export type LoopStep = {
  name: string;
  phase: 1 | 2 | 3 | 4;
  checkpoint?: boolean; // a star: the batch can be stopped here
  tag: StepTag;
  where: string; // where it runs in the code
  note: string;
};

export const PHASES: { n: 1 | 2 | 3 | 4; name: string; checkpoint: boolean }[] = [
  { n: 1, name: "Targets", checkpoint: false },
  { n: 2, name: "Plan and review", checkpoint: true },
  { n: 3, name: "Make and measure", checkpoint: true },
  { n: 4, name: "Release", checkpoint: true },
];

export const LOOP_STEPS: LoopStep[] = [
  { name: "Targets", phase: 1, tag: "Code", where: "target_check", note: "Plain code checks the targets against the lab limits." },
  { name: "Setup agent", phase: 2, tag: "AI agent", where: "setup_agent", note: "Claude reads the references and past runs and sets the search space." },
  {
    name: "Optimizer and prediction",
    phase: 2,
    tag: "ML simulated",
    where: "optimizer, prediction_model",
    note: "A fixed table and a fixed lookup, no trained model. This is where a real model plugs in.",
  },
  { name: "Safety gate", phase: 2, checkpoint: true, tag: "Code", where: "policy_kernel", note: "Blocks restricted elements and repeats of failed runs." },
  { name: "Scientist review", phase: 2, tag: "Person", where: "triage_and_hitl (pause)", note: "A person approves or rejects a risky recipe before anything is made." },
  { name: "Make and measure", phase: 3, tag: "Simulated", where: "triage_and_hitl (workcell, measure)", note: "No real synthesis: the scan and the values are simulated." },
  { name: "Measurement check", phase: 3, checkpoint: true, tag: "Code", where: "triage_and_hitl (check.py)", note: "Plain code checks the readings and flags anomalies." },
  { name: "Diagnosis", phase: 3, tag: "AI agent", where: "diagnose_flagged", note: "Claude proposes re-measure or hold; a code gate decides." },
  { name: "Save and learn", phase: 3, tag: "Code", where: "SQLite, history.py", note: "History only, no retraining: outcomes feed the next plan's prompt." },
  { name: "Release", phase: 4, checkpoint: true, tag: "Person", where: "release route, release.py", note: "A person decides, after code release rules (no Red sample, a reason for any exception)." },
];

export const CHECKPOINT_NOTE =
  "The batch can be stopped at a star: by code at the Safety gate and the Measurement check, or by a person at Release.";
