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

// The 7 LangGraph nodes in backend/app/graph.py, in the order the fixed edges run them.
export const GRAPH_NODES = [
  { id: "target_check", what: "Lab limits; stops impossible targets" },
  { id: "setup_agent", what: "Claude sets the search space" },
  { id: "optimizer", what: "Fixed table of ratios (via an MCP tool)" },
  { id: "prediction_model", what: "Fixed lookup, no trained model" },
  { id: "policy_kernel", what: "Safety gate" },
  { id: "triage_and_hitl", what: "Pause for review, then simulated make and measure, then the measurement check" },
  { id: "diagnose_flagged", what: "Claude proposes re-measure or hold; a code gate decides" },
] as const;
export type GraphNode = (typeof GRAPH_NODES)[number]["id"];

export type LoopStep = {
  name: string;
  phase: 1 | 2 | 3 | 4;
  checkpoint?: boolean; // a star: the batch can be stopped here
  tag: StepTag;
  where: string; // where it runs in the code
  nodes: GraphNode[]; // the graph nodes it runs on; empty when it runs outside the graph
  outside?: string; // where it runs when it is not a graph node
  note: string;
  detail?: string; // one more line on the card
};

export const PHASES: { n: 1 | 2 | 3 | 4; name: string; checkpoint: boolean }[] = [
  { n: 1, name: "Targets", checkpoint: false },
  { n: 2, name: "Plan and review", checkpoint: true },
  { n: 3, name: "Make and measure", checkpoint: true },
  { n: 4, name: "Release", checkpoint: true },
];

export const LOOP_STEPS: LoopStep[] = [
  { name: "Targets", phase: 1, tag: "Code", where: "target_check", nodes: ["target_check"], note: "Plain code checks the targets against the lab limits." },
  { name: "Setup agent", phase: 2, tag: "AI agent", where: "setup_agent", nodes: ["setup_agent"], note: "Claude reads the references and past runs and sets the search space." },
  {
    name: "Optimizer and prediction",
    phase: 2,
    tag: "ML simulated",
    where: "optimizer, prediction_model",
    nodes: ["optimizer", "prediction_model"],
    note: "A fixed table and a fixed lookup, no trained model. This is where a real model plugs in.",
    // Checked against graph.py: the optimizer node calls the propose_alloy_ratios tool through the MCP gateway, and the
    // setup agent only supplies the search space. The prediction lookup is a plain function call, not MCP.
    detail:
      "The optimizer is called through MCP, so a real optimizer can replace this mock without changing the setup agent. The prediction lookup is a plain function call.",
  },
  { name: "Safety gate", phase: 2, checkpoint: true, tag: "Code", where: "policy_kernel", nodes: ["policy_kernel"], note: "Blocks restricted elements and repeats of failed runs." },
  { name: "Scientist review", phase: 2, tag: "Person", where: "triage_and_hitl (pause)", nodes: ["triage_and_hitl"], note: "A person approves or rejects a risky recipe before anything is made." },
  { name: "Make and measure", phase: 3, tag: "Simulated", where: "triage_and_hitl (workcell, measure)", nodes: ["triage_and_hitl"], note: "No real synthesis: the scan and the values are simulated." },
  { name: "Measurement check", phase: 3, checkpoint: true, tag: "Code", where: "triage_and_hitl (check.py)", nodes: ["triage_and_hitl"], note: "Plain code checks the readings and flags anomalies." },
  { name: "Diagnosis", phase: 3, tag: "AI agent", where: "diagnose_flagged", nodes: ["diagnose_flagged"], note: "Claude proposes re-measure or hold; a code gate decides." },
  { name: "Save and learn", phase: 3, tag: "Code", where: "SQLite, history.py", nodes: [], outside: "SQLite writes after each step; history.py feeds the next setup agent", note: "History only, no retraining: outcomes feed the next plan's prompt." },
  { name: "Release", phase: 4, checkpoint: true, tag: "Person", where: "release route, release.py", nodes: [], outside: "API route /api/samples/{id}/release, rules in release.py", note: "A person decides, after code release rules (no Red sample, a reason for any exception)." },
];

export const STEPS_ON_NODES = `The console shows ${LOOP_STEPS.length} steps that run on ${GRAPH_NODES.length} graph nodes.`;

export const CHECKPOINT_NOTE =
  "The batch can be stopped at a star: by code at the Safety gate and the Measurement check, or by a person at Release.";
