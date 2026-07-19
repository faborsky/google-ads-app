"""Experiments — A/B tests of search campaigns (SEARCH_CUSTOM).

Flow: experiment-create (experiment + control/treatment arms in ONE request →
treatment draft campaign is generated) → edit the draft campaign (its ID is
printed; query it with include_drafts) → experiment-schedule (async start) →
read results (experiments) → experiment-end / experiment-promote.

Constraints: ≤5 experiments scheduled per campaign, 1 running at a time;
traffic_split must sum to 100. Schedule the start in the future so treatment
ads clear review.
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _execute_with_retry, _get_client, _quota_guard,
                      _run_mutation, _run_query, _track_ops)
from gads.formatting import _die, _micros, _output_json


def cmd_experiments(args: argparse.Namespace) -> None:
    """List experiments with status and (for finished/running) paired metrics."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(client, cid, """
        SELECT experiment.experiment_id, experiment.name, experiment.status,
               experiment.type, experiment.start_date, experiment.end_date
        FROM experiment
        WHERE experiment.status != 'REMOVED'
    """, args.account)
    out = [{
        "id": str(r.experiment.experiment_id),
        "name": r.experiment.name,
        "status": r.experiment.status.name,
        "type": r.experiment.type_.name,
        "start": r.experiment.start_date,
        "end": r.experiment.end_date,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné experimenty.")
        return
    for e in out:
        print(f"{e['id']:>13}  {e['status']:<12} {e['type']:<15} "
              f"{e['start']} → {e['end']}  {e['name']}")


def cmd_experiment_create(args: argparse.Namespace) -> None:
    """Create a SEARCH_CUSTOM experiment on a campaign: experiment + both arms.

    Treatment draft campaign is auto-generated — its resource name is printed;
    make your change(s) on it, then experiment-schedule.
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    split = int(args.traffic_split)
    if not 1 <= split <= 99:
        _die("--traffic-split = procento pro TREATMENT, 1–99.")

    # 1) the experiment itself
    exp_op = client.get_type("ExperimentOperation")
    exp = exp_op.create
    exp.name = args.name
    exp.type_ = client.enums.ExperimentTypeEnum.SEARCH_CUSTOM
    exp.suffix = args.suffix
    exp.status = client.enums.ExperimentStatusEnum.SETUP
    exp.start_date = args.start
    exp.end_date = args.end

    print(f"PLÁN: experiment '{args.name}' na kampani {args.campaign} — "
          f"{100 - split}/{split} % (control/treatment), {args.start} → {args.end}")
    if not args.confirm:
        print("\n(experiment flow nemá smysluplný dry-run — tohle je jen plán) — přidej --confirm.")
        return

    resp = _run_mutation(client, args.account, cid,
                         service_name="ExperimentService", method_name="mutate_experiments",
                         request_type="MutateExperimentsRequest", operations=[exp_op],
                         confirm=True)
    if resp is None:
        return
    experiment_rn = resp.results[0].resource_name
    print(f"   experiment: {experiment_rn}")

    # 2) both arms in ONE request (API requirement)
    arm_ops = []
    control = client.get_type("ExperimentArmOperation")
    ca = control.create
    ca.experiment = experiment_rn
    ca.name = "control"
    ca.control = True
    ca.traffic_split = 100 - split
    ca.campaigns.append(client.get_service("CampaignService").campaign_path(cid, args.campaign))
    arm_ops.append(control)

    treatment = client.get_type("ExperimentArmOperation")
    ta = treatment.create
    ta.experiment = experiment_rn
    ta.name = "treatment"
    ta.control = False
    ta.traffic_split = split
    arm_ops.append(treatment)

    service = client.get_service("ExperimentArmService")
    request = client.get_type("MutateExperimentArmsRequest")
    request.customer_id = cid
    request.operations.extend(arm_ops)
    # ask for the generated draft campaign in the response
    request.response_content_type = (
        client.enums.ResponseContentTypeEnum.MUTABLE_RESOURCE)
    _quota_guard(args.account, len(arm_ops))
    arm_resp = _execute_with_retry(
        lambda: service.mutate_experiment_arms(request=request),
        what=f"experiment-arms {cid}")
    if arm_resp is None:
        return
    _track_ops(args.account, len(arm_ops))
    print("\n✅ ZAPSÁNO — experiment + arms:")
    draft = None
    for r in arm_resp.results:
        print(f"   {r.resource_name}")
        if r.experiment_arm and not r.experiment_arm.control:
            drafts = list(r.experiment_arm.in_design_campaigns)
            if drafts:
                draft = drafts[0]
    if draft:
        print(f"\n   DRAFT kampaň (treatment): {draft}")
        print("   → uprav ji (bidding/RSA/…), pak `experiment-schedule`. "
              "Draft je vidět v GAQL jen s include_drafts=true.")


def cmd_experiment_schedule(args: argparse.Namespace) -> None:
    """Schedule (start) an experiment — async operation on Google's side."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rn = f"customers/{cid}/experiments/{args.experiment_id}"
    print(f"PLÁN: spustit experiment {args.experiment_id}")
    if not args.confirm:
        print("\n(schedule nemá validate_only — tohle je jen plán) — přidej --confirm.")
        return
    service = client.get_service("ExperimentService")
    _quota_guard(args.account, 1)
    resp = _execute_with_retry(
        lambda: service.schedule_experiment(resource_name=rn),
        what=f"experiment-schedule {cid}")
    if resp is None:
        return
    _track_ops(args.account, 1)
    print(f"\n✅ Experiment {args.experiment_id} naplánován (async — Google ho "
          f"rozjede po zpracování; long-running operation: {resp.name}).")


def cmd_experiment_end(args: argparse.Namespace) -> None:
    """End an experiment (nothing is applied to the base campaign). An
    experiment still in SETUP can't be "ended" — it gets REMOVED instead."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rn = f"customers/{cid}/experiments/{args.experiment_id}"
    rows = _run_query(client, cid, f"""
        SELECT experiment.status FROM experiment
        WHERE experiment.experiment_id = {args.experiment_id}
    """, args.account)
    if not rows:
        _die(f"Experiment {args.experiment_id} nenalezen.")
    status = rows[0].experiment.status.name
    in_setup = status == "SETUP"
    verb = "smazat (je v SETUP, nikdy neběžel)" if in_setup else "ukončit (bez aplikace změn)"
    print(f"PLÁN: {verb} experiment {args.experiment_id}")
    if not args.confirm:
        print("\n(end nemá validate_only — tohle je jen plán) — přidej --confirm.")
        return
    service = client.get_service("ExperimentService")
    _quota_guard(args.account, 1)
    if in_setup:
        op = client.get_type("ExperimentOperation")
        op.remove = rn
        request = client.get_type("MutateExperimentsRequest")
        request.customer_id = cid
        request.operations.append(op)
        _execute_with_retry(
            lambda: service.mutate_experiments(request=request),
            what=f"experiment-remove {cid}")
    else:
        _execute_with_retry(
            lambda: service.end_experiment(experiment=rn),
            what=f"experiment-end {cid}")
    _track_ops(args.account, 1)
    print(f"\n✅ Experiment {args.experiment_id} {'smazán' if in_setup else 'ukončen'}.")


def cmd_experiment_promote(args: argparse.Namespace) -> None:
    """Promote the treatment: copy its changes onto the base campaign (async)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rn = f"customers/{cid}/experiments/{args.experiment_id}"
    print(f"PLÁN: PROMOTE experimentu {args.experiment_id} — treatment změny "
          f"se PŘEPÍŠOU do základní kampaně")
    if not args.confirm:
        print("\n(promote nemá validate_only — tohle je jen plán) — přidej --confirm.")
        return
    service = client.get_service("ExperimentService")
    _quota_guard(args.account, 1)
    resp = _execute_with_retry(
        lambda: service.promote_experiment(resource_name=rn),
        what=f"experiment-promote {cid}")
    if resp is None:
        return
    _track_ops(args.account, 1)
    print(f"\n✅ Promote spuštěn (async; long-running operation: {resp.name}).")


def cmd_experiment_results(args: argparse.Namespace) -> None:
    """Paired metrics of an experiment (treatment vs control + significance)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(client, cid, f"""
        SELECT experiment.experiment_id, experiment.name, experiment.status,
               metrics.clicks, metrics.control_clicks,
               metrics.cost_micros, metrics.control_cost_micros,
               metrics.conversions, metrics.control_conversions
        FROM experiment
        WHERE experiment.experiment_id = {args.experiment_id}
    """, args.account)
    if not rows:
        _die(f"Experiment {args.experiment_id} nenalezen.")
    r = rows[0]
    data = {
        "id": str(r.experiment.experiment_id),
        "name": r.experiment.name,
        "status": r.experiment.status.name,
        "treatment": {
            "clicks": r.metrics.clicks,
            "cost": round(_micros(r.metrics.cost_micros), 2),
            "conversions": round(r.metrics.conversions, 1),
        },
        "control": {
            "clicks": r.metrics.control_clicks,
            "cost": round(_micros(r.metrics.control_cost_micros), 2),
            "conversions": round(r.metrics.control_conversions, 1),
        },
    }
    if args.json:
        _output_json(data)
        return
    print(f"Experiment '{data['name']}' ({data['status']}):")
    print(f"{'':>12}  {'treatment':>12}  {'control':>12}")
    for k in ("clicks", "cost", "conversions"):
        print(f"{k:>12}  {data['treatment'][k]:>12,}  {data['control'][k]:>12,}")
