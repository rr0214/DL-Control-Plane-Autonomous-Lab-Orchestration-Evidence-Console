"""promote_overrides: pure logic tested against a fake Phoenix client. No server, no network."""
import pytest

from app import promote_overrides as po


# ---- fake Phoenix ---------------------------------------------------------------------------

def span(name, trace, span_id, start, **attrs):
    return {"name": name, "context": {"trace_id": trace, "span_id": span_id}, "start_time": start, "attributes": attrs}


def review(span_id, thread, decision, start="2026-11-12T03:00:00+00:00", trace=None):
    return span(
        "scientist.review",
        trace or f"rev-{span_id}",
        span_id,
        start,
        thread_id=thread,
        decision=decision,
        scientist_override=decision != "approve",
    )


def plan(trace, thread):
    return span("campaign.plan", trace, f"plan-{trace}", "2026-11-12T02:59:00+00:00", thread_id=thread, campaign_id="CAMP-014")


def presynth(trace, cand, margin=0.71, blast="high", required=True, start="2026-11-12T02:59:00+00:00"):
    return span(
        "presynthesis.review", trace, f"pre-{trace}-{cand}-{start[-8:]}", start,
        candidate_id=cand, predicted_ductility_margin=margin, furnace_blast_radius=blast, review_required=required,
    )


def triage(trace, cand, status="Yellow", cv=0.71, start="2026-11-12T02:59:01+00:00"):
    return span("sample.triage", trace, f"tri-{trace}-{cand}-{start[-8:]}", start, candidate_id=cand, triage_status=status, cv_confidence=cv)


class FakeDatasets:
    def __init__(self):
        self.store = {}  # name -> list of example dicts
        self.created = []
        self.appended = []

    def list(self):
        return [{"name": n} for n in self.store]

    def get_dataset(self, dataset):
        class D:  # mimics phoenix Dataset.examples
            examples = self.store[dataset]

        return D()

    def _rows(self, inputs, outputs, metadata):
        return [{"input": i, "output": o, "metadata": m} for i, o, m in zip(inputs, outputs, metadata)]

    def create_dataset(self, name, inputs, outputs, metadata, dataset_description=None):
        self.created.append(name)
        self.store[name] = self._rows(inputs, outputs, metadata)

    def add_examples_to_dataset(self, dataset, inputs, outputs, metadata):
        self.appended.append(dataset)
        self.store[dataset].extend(self._rows(inputs, outputs, metadata))


class FakeSpans:
    def __init__(self, spans):
        self.spans = spans
        self.annotations = []

    def add_span_annotation(self, **kw):
        self.annotations.append(kw)

    def get_spans(self, project_identifier, name=None, trace_ids=None, limit=100):
        out = [s for s in self.spans if s["name"] == name]
        if trace_ids is not None:
            out = [s for s in out if s["context"]["trace_id"] in trace_ids]
        return out[:limit]


class FakeClient:
    def __init__(self, spans):
        self.spans = FakeSpans(spans)
        self.datasets = FakeDatasets()


def two_override_world():
    return [
        plan("P1", "t1"), presynth("P1", "C-3"), review("R1", "t1", "reject", "2026-11-12T03:00:00+00:00"),
        plan("P2", "t2"), presynth("P2", "C-3"), review("R2", "t2", "revise", "2026-11-12T04:00:00+00:00"),
        plan("P3", "t3"), presynth("P3", "C-3"), review("R3", "t3", "approve", "2026-11-12T05:00:00+00:00"),
    ]


# ---- selection and joining --------------------------------------------------------------------

def test_only_overrides_are_selected():
    reviews = [review("R1", "t1", "reject"), review("R2", "t2", "approve"), review("R3", "t3", "revise")]
    assert [s["context"]["span_id"] for s in po.select_overrides(reviews)] == ["R1", "R3"]


def test_review_is_joined_to_its_plan_by_thread_id_and_yellow_sample():
    spans = [plan("P1", "t1"), triage("P1", "C-1", status="Green", cv=0.95), triage("P1", "C-3"), review("R1", "t1", "reject")]
    (row,) = po.build_rows(
        [s for s in spans if s["name"] == "scientist.review"],
        [s for s in spans if s["name"] == "campaign.plan"],
        [s for s in spans if s["name"] == "sample.triage"],
    )
    assert (row.thread_id, row.decision, row.candidate_id, row.cv_confidence) == ("t1", "reject", "C-3", 0.71)
    assert row.plan_trace_id == "P1" and row.campaign_id == "CAMP-014"
    assert row.thread_link_ambiguous is False


def test_duplicate_triage_spans_from_a_resume_do_not_duplicate_the_row():
    # The triage node re-runs when the graph resumes, so the same Yellow candidate appears twice.
    spans = [
        plan("P1", "t1"),
        triage("P1", "C-3", start="2026-11-12T02:59:01+00:00"),
        triage("P1", "C-3", start="2026-11-12T03:00:01+00:00"),
        review("R1", "t1", "reject"),
    ]
    rows = po.build_rows([spans[3]], [spans[0]], [spans[1], spans[2]])
    assert len(rows) == 1 and rows[0].candidate_id == "C-3"


def test_review_with_no_matching_plan_still_produces_a_row_with_gaps():
    (row,) = po.build_rows([review("R1", "ghost", "reject")], [], [])
    assert row.plan_trace_id is None and row.candidate_id is None and row.cv_confidence is None


def test_threads_with_multiple_reviews_are_flagged_ambiguous():
    reviews = [review("R1", "t1", "reject"), review("R2", "t1", "revise"), review("R3", "t2", "reject")]
    assert po.ambiguous_threads(reviews) == {"t1"}
    rows = po.build_rows(reviews, [plan("P1", "t1"), plan("P2", "t2")], [])
    assert {r.review_span_id: r.thread_link_ambiguous for r in rows} == {"R1": True, "R2": True, "R3": False}


# ---- promotion --------------------------------------------------------------------------------

def test_promote_creates_the_dataset_with_overrides_only():
    client = FakeClient(two_override_world())
    result = po.promote(client, "sdl-control-plane")
    assert client.datasets.created == [po.DATASET_NAME]
    rows = client.datasets.store[po.DATASET_NAME]
    assert len(rows) == 2 and len(result.added) == 2
    assert result.review_spans == 3 and result.overrides == 2
    assert {r["output"]["scientist_decision"] for r in rows} == {"reject", "revise"}  # the approve is not promoted


def test_rows_are_marked_unlabeled_and_never_claim_an_expected_outcome():
    client = FakeClient(two_override_world())
    po.promote(client, "sdl-control-plane")
    for r in client.datasets.store[po.DATASET_NAME]:
        assert r["metadata"]["label_status"] == "needs_expert_label"
        assert r["metadata"]["source_project"] == "sdl-control-plane"
        assert "expected_status" not in r["output"] and "expected_status" not in r["input"]


def test_rerun_is_idempotent():
    client = FakeClient(two_override_world())
    po.promote(client, "sdl-control-plane")
    again = po.promote(client, "sdl-control-plane")
    assert again.added == [] and again.already_present == 2
    assert len(client.datasets.store[po.DATASET_NAME]) == 2
    assert client.datasets.created == [po.DATASET_NAME] and client.datasets.appended == []


def test_new_override_is_appended_to_the_existing_dataset():
    world = two_override_world()
    client = FakeClient(world)
    po.promote(client, "sdl-control-plane")
    client.spans.spans += [plan("P4", "t4"), triage("P4", "C-3"), review("R4", "t4", "reject", "2026-11-12T06:00:00+00:00")]
    result = po.promote(client, "sdl-control-plane")
    assert [r.thread_id for r in result.added] == ["t4"] and result.already_present == 2
    assert client.datasets.appended == [po.DATASET_NAME]
    assert len(client.datasets.store[po.DATASET_NAME]) == 3


def test_no_overrides_creates_nothing():
    client = FakeClient([plan("P1", "t1"), triage("P1", "C-3"), review("R1", "t1", "approve")])
    result = po.promote(client, "sdl-control-plane")
    assert result.overrides == 0 and result.added == []
    assert client.datasets.store == {} and client.datasets.created == []
    assert "No scientist overrides found yet" in po.format_summary(result)


def test_dry_run_writes_nothing_but_reports_what_it_would_add():
    client = FakeClient(two_override_world())
    result = po.promote(client, "sdl-control-plane", dry_run=True)
    assert len(result.added) == 2 and client.datasets.store == {}
    text = po.format_summary(result)
    assert "DRY RUN" in text and "Would add" in text


# ---- terminal summary -------------------------------------------------------------------------

def test_summary_shows_counts_rows_and_next_step():
    client = FakeClient(two_override_world())
    text = po.format_summary(po.promote(client, "sdl-control-plane"))
    assert "Review spans found:" in text and "Overrides (not approve):" in text
    assert po.DATASET_NAME in text and "decision=reject" in text and "decision=revise" in text
    assert "margin=0.71" in text and "Each row still needs an expert label" in text
    assert "Warning" not in text  # clean data, so no ambiguity warning


def test_summary_warns_about_repeated_thread_reviews():
    spans = [plan("P1", "t1"), triage("P1", "C-3"), review("R1", "t1", "reject"), review("R2", "t1", "revise")]
    text = po.format_summary(po.promote(FakeClient(spans), "sdl-control-plane"))
    assert "thread_link_ambiguous" in text and "[thread link ambiguous]" in text and "Reset Demo" in text


# ---- command line -----------------------------------------------------------------------------

def test_main_exits_with_a_clear_message_when_phoenix_is_down(monkeypatch, capsys):
    monkeypatch.setattr(po.telemetry, "phoenix_reachable", lambda *a, **k: False)
    assert po.main([]) == 1
    assert "Cannot reach Phoenix" in capsys.readouterr().out


def test_script_only_touches_phoenix_not_the_app():
    # Isolation guard: the script must not import the API, database, or graph modules.
    src = open(po.__file__, encoding="utf-8").read()
    for forbidden in ("from . import db", "from .api", "from .graph", "orchestrator", "sqlite3"):
        assert forbidden not in src


def test_pre_synthesis_review_is_joined_with_risk_signals_even_with_no_scan():
    # A rejected recipe is never synthesized, so there is no sample.triage span at all.
    spans = [plan("P1", "t1"), presynth("P1", "C-1", margin=0.92, blast="low", required=False),
             presynth("P1", "C-3"), review("R1", "t1", "reject")]
    rows = po.build_rows(
        [spans[3]], [spans[0]], [], [s for s in spans if s["name"] == "presynthesis.review"]
    )
    (row,) = rows
    assert row.candidate_id == "C-3" and row.review_stage == "pre_synthesis"
    assert row.predicted_ductility_margin == 0.71 and row.furnace_blast_radius == "high"
    assert row.cv_confidence is None


def test_older_traces_without_a_presynthesis_span_fall_back_to_the_yellow_scan():
    spans = [plan("P1", "t1"), triage("P1", "C-3"), review("R1", "t1", "reject")]
    (row,) = po.build_rows([spans[2]], [spans[0]], [spans[1]])
    assert row.review_stage == "post_scan_legacy" and row.cv_confidence == 0.71
    assert row.predicted_ductility_margin is None


def test_summary_shows_the_ductility_margin_for_pre_synthesis_rows():
    text = po.format_summary(po.promote(FakeClient(two_override_world()), "sdl-control-plane"))
    assert "margin=0.71" in text and "decision=reject" in text


def test_dataset_inputs_carry_the_pre_synthesis_signals():
    client = FakeClient(two_override_world())
    po.promote(client, "sdl-control-plane")
    first = client.datasets.store[po.DATASET_NAME][0]["input"]
    assert first["review_stage"] == "pre_synthesis"
    assert first["predicted_ductility_margin"] == 0.71 and first["furnace_blast_radius"] == "high"


# ---- scientist notes and themes ---------------------------------------------------------------

def review_with_note(span_id, thread, decision, note):
    s = review(span_id, thread, decision)
    s["attributes"]["review_note"] = note
    return s


def test_theme_buckets_notes_by_keyword_and_handles_empty_and_unknown():
    assert po.theme_for("Furnace blast radius is high, not worth it") == "furnace_blast_radius"
    assert po.theme_for("Ductility margin 0.71 too close to Run-088") == "ductility_margin"
    assert po.theme_for("Gut feel says no") == "other"
    assert po.theme_for("") == "no_note" and po.theme_for(None) == "no_note"


def test_note_is_read_from_the_review_span_and_carried_into_the_dataset_row():
    spans = [plan("P1", "t1"), presynth("P1", "C-3"), review_with_note("R1", "t1", "reject", "Blast radius too high")]
    client = FakeClient(spans)
    po.promote(client, "sdl-control-plane")
    row = client.datasets.store[po.DATASET_NAME][0]
    assert row["output"]["scientist_note"] == "Blast radius too high"
    assert row["metadata"]["theme"] == "furnace_blast_radius"
    assert "expected_status" not in row["output"]  # the note is evidence, not the expert's label


def test_overrides_without_a_note_still_promote():
    client = FakeClient(two_override_world())
    po.promote(client, "sdl-control-plane")
    rows = client.datasets.store[po.DATASET_NAME]
    assert all(r["output"]["scientist_note"] == "" and r["metadata"]["theme"] == "no_note" for r in rows)


def test_summary_shows_each_note_and_groups_them_by_theme():
    spans = []
    for i, note in enumerate(["Furnace blast radius is high", "Blast radius, not worth the risk", "Margin looks thin"], 1):
        spans += [plan(f"P{i}", f"t{i}"), presynth(f"P{i}", "C-3"), review_with_note(f"R{i}", f"t{i}", "reject", note)]
    text = po.format_summary(po.promote(FakeClient(spans), "sdl-control-plane"))
    assert 'note: "Furnace blast radius is high"' in text
    assert "2 x furnace_blast_radius" in text and "1 x ductility_margin" in text


# ---- notes written onto the plan trace as annotations ---------------------------------------

def noted_world():
    spans = []
    for i, note in enumerate(["Furnace blast radius is high", "Predicted ductility too close to cracking"], 1):
        spans += [plan(f"P{i}", f"t{i}"), presynth(f"P{i}", "C-3"), review_with_note(f"R{i}", f"t{i}", "reject", note)]
    spans += [plan("P3", "t3"), presynth("P3", "C-3"), review("R3", "t3", "reject")]  # no note: nothing to attach
    return spans


def test_notes_are_attached_to_the_plan_span_with_theme_and_text():
    client = FakeClient(noted_world())
    result = po.promote(client, "sdl-control-plane")
    notes = client.spans.annotations
    assert result.annotated == 2 and len(notes) == 2
    first = notes[0]
    assert first["span_id"] == "plan-P1"  # the campaign.plan span, not the review span
    assert first["annotation_name"] == "scientist_feedback" and first["annotator_kind"] == "HUMAN"
    assert first["label"] == "furnace_blast_radius" and first["explanation"] == "Furnace blast radius is high"
    assert first["identifier"] == "R1"  # re-running updates the same annotation instead of duplicating it


def test_dry_run_writes_no_annotations_but_reports_how_many_it_would():
    client = FakeClient(noted_world())
    result = po.promote(client, "sdl-control-plane", dry_run=True)
    assert client.spans.annotations == [] and result.annotated == 0 and result.annotatable == 2
    assert "Would write to traces:" in po.format_summary(result)


def test_annotating_is_best_effort_and_never_blocks_the_dataset_write():
    client = FakeClient(noted_world())

    def boom(**kw):
        raise RuntimeError("phoenix hiccup")

    client.spans.add_span_annotation = boom
    result = po.promote(client, "sdl-control-plane")
    assert result.annotated == 0 and len(result.added) == 3
