import re


PLAN_VERSION = 14
GENERAL_QUESTION = "What item or area is affected, and what happens when you try to use it? Please only observe; do not take anything apart."
REPAIR_PLANS = {
    "leak": ("Stop the reported leak and restore the affected plumbing.", "Plumber", ["Locate the source and determine which fixtures or pipes are affected.", "Have a plumber inspect the leak and any resulting water damage.", "Repair the confirmed cause, then check for leaks during normal use."]),
    "hvac": ("Restore heating, cooling, or airflow in the affected rooms.", "HVAC technician", ["Identify affected rooms and record the thermostat setting and observed symptoms.", "Have an HVAC technician inspect the equipment and diagnose the failure.", "Repair the diagnosed fault and confirm normal operation."]),
    "electrical": ("Restore safe operation of the affected electrical fixtures or outlets.", "Licensed electrician", ["Identify the affected fixtures or outlets without opening panels or touching wiring.", "Have a licensed electrician inspect the circuit and diagnose the fault.", "Complete the repair and have the electrician confirm safe operation."]),
    "appliance": ("Restore operation of the reported appliance.", "Appliance technician", ["Identify the appliance, symptoms, and any visible error code.", "Have an appliance technician inspect it and determine the repair options.", "Repair or replace the appliance after diagnosis and confirm normal operation."]),
    "structural": ("Assess and repair the reported building damage.", "Qualified building contractor", ["Identify the affected area without climbing or disturbing damaged materials.", "Have a qualified contractor assess the damage and whether a structural specialist is needed.", "Complete the repair after assessment and verify the area is safe before normal use."]),
    "pest_mold": ("Address the reported pest or mold problem and its underlying conditions.", "Pest control or mold remediation specialist", ["Identify the affected area and visible signs without disturbing mold or contaminated materials.", "Have a suitable specialist assess the problem, including moisture or entry sources.", "Complete treatment and source repairs, then arrange a follow-up inspection."]),
    "lock": ("Restore secure, working access through the affected door or lock.", "Locksmith", ["Identify the affected door and whether the home can currently be secured.", "Have an authorized locksmith inspect the lock, latch, and door alignment.", "Repair the lock and verify that the door locks, unlocks, and closes correctly."]),
    "general": ("Identify the reported maintenance problem and determine a repair.", None, ["Identify the affected item and how it is failing from the request and any additional observations.", "Arrange an inspection by a suitable maintenance technician to diagnose the cause.", "Complete the repair after diagnosis and verify that the reported problem is resolved."]),
}


def resident_messages(ticket):
    return [message["body"] for message in ticket.get("messages", []) if message.get("author_role", "tenant") == "tenant" and message.get("body", "").strip() and not message["body"].startswith(("Simulated SMS reply: ", "SMS reply queued: "))]


def rules_plan(ticket):
    from grok_bot.domain.maintenance import SAFETY_MESSAGE, _category, _classify, _handoff_requested
    from grok_bot.domain.maintenance_guidance import FAMILIES, HVAC_CONTEXT, matching_families, tracked_issues

    messages = resident_messages(ticket)
    description = ticket.get("description") or ""
    observations = " ".join([description, *messages]).lower()
    issues = tracked_issues(description, messages)
    open_issues = [issue for issue in issues if issue["status"] == "open"]
    emergency, urgent = _classify(observations)
    professional_only = bool(re.search(
        r"\b(?:oven|stove|cooktop)\b.{0,60}\b(?:won't|will not|cannot|can't|doesn't) (?:turn |switch |shut )?off\b|"
        r"\b(?:oven|stove|cooktop)\b.{0,40}\b(?:not turning off|stays on|keeps heating)\b|"
        r"\b(?:bulb|base)\b.{0,40}\b(?:stuck|broken)\b|\b(?:stuck|broken)\b.{0,40}\b(?:bulb|base)\b|"
        r"\b(?:locked out|lockout|cannot get in|can't get in|cannot secure|can't lock)\b",
        observations,
    ))
    recurring_pests = any(issue["key"] == "pest" for issue in open_issues) and bool(re.search(r"\b(?:again|returned|recurring|recurrence|after treatment)\b", observations))
    category = FAMILIES[open_issues[0]["key"]][0] if open_issues else _category(observations)
    if category == "general":
        category = ticket.get("category", "general")
    summary, trade, steps = REPAIR_PLANS[category]
    if any(issue["key"] == "hot_water" for issue in open_issues):
        summary = "Restore hot water; the cause still needs diagnosis."
        trade = "Plumber or licensed water-heater technician"
        steps = ["Review whether hot water is missing at all fixtures or only one.", "Have a qualified technician inspect the water heater and affected fixtures.", "Repair the diagnosed fault and confirm hot water is restored."]
    if any(issue["key"] == "internet" for issue in open_issues):
        trade = "Internet service or network support"
    repeated_failure = bool(re.search(r"\b(?:still|again|repeated|multiple times|several times|already)\b.{0,80}\b(?:tried|reset|restart|reboot|not working|doesn't work|no heat|not heating|cold)\b|\b(?:tried|reset|restart|reboot)\w*\b.{0,80}\b(?:still|didn't help|did not help|didn't work|did not work|multiple times|several times)\b", observations))
    priority = "EMERGENCY" if emergency or ticket["emergency"] else "URGENT_TRIAGE" if urgent or ticket["urgent_triage"] or professional_only or recurring_pests else ticket["priority"]
    active = ticket.get("status") not in {None, "INTAKE_OPEN", "MANAGER_REVIEW", "TRIAGE_PENDING", "WAITING_TENANT"}
    wants_worker = bool(ticket.get("handoff")) or _handoff_requested(observations) or bool(re.search(r"\b(?:send (?:someone|a (?:repairman|technician|plumber|electrician))|someone to come|(?:speak|talk) to someone|(?:want|need|speak to|talk to) (?:a |an )?(?:human|person|property manager|manager|repairman|technician|plumber|electrician)|stop asking|skip (?:this|questions|troubleshooting))\b", observations))
    if messages and re.fullmatch(r"(?:a )?(?:property manager|manager|repairman|human|technician|plumber|electrician)(?: please)?[.!]?", messages[-1].strip(), re.IGNORECASE):
        wants_worker = True
    answered = [message["body"] for message in ticket.get("messages", []) if message.get("author_role") in {"system", "assistant"}]
    evidence = {issue["key"]: [] for issue in open_issues}
    context = []
    for message in [{"author_role": "tenant", "body": description}, *ticket.get("messages", [])]:
        body = message.get("body", "")
        if message.get("author_role", "tenant") in {"system", "assistant"}:
            context = [key for key in matching_families(body) if key in evidence]
            continue
        if message.get("author_role", "tenant") != "tenant":
            continue
        for clause in re.split(r"[.!?;\n]+|\b(?:but|and)\b", body, flags=re.I):
            named = matching_families(clause)
            if named == ["hvac"] and context and "hvac" not in context and not re.search(HVAC_CONTEXT, clause, re.I):
                named = []
            if named:
                scope = [key for key in named if key in evidence]
            elif context:
                scope = context
            elif len(evidence) == 1:
                scope = list(evidence)
            else:
                scope = []
            for key in scope:
                evidence[key].append(clause.lower())
            if named:
                context = [key for key in named if key in evidence]
    pending_question = None
    questions = [question for issue in open_issues for _, question in FAMILIES[issue["key"]][3]]
    if not issues:
        questions.append(GENERAL_QUESTION)
    for question in (ticket.get("analysis") or {}).get("follow_up", []):
        named = set(matching_families(question))
        if evidence and (not named or named.intersection(evidence)) and not ("hvac" in named and "hvac" not in evidence):
            questions.append(question)
    for message in ticket.get("messages", []):
        if message.get("author_role", "tenant") == "tenant":
            pending_question = None
        elif message.get("author_role") == "system":
            pending_question = next((question for question in questions if question in message.get("body", "")), pending_question)
    follow_up = []
    if len(messages) < 6 and not active and not wants_worker and not repeated_failure and priority not in {"EMERGENCY", "URGENT_TRIAGE"}:
        for issue in open_issues:
            for known, question in FAMILIES[issue["key"]][3]:
                if issue["key"] == "dishwasher":
                    observations_for_issue = " ".join(evidence[issue["key"]])
                    if "power switch" in question and (re.search(r"\b(?:leak\w*|water|wet|puddle|damaged|burn\w*|smoke|spark\w*)\b", observations_for_issue) or not re.search(r"\b(?:no (?:lights?|power|display)|blank|dark|nothing happens|doesn[’']t (?:light|turn) on|won[’']t (?:light|turn) on)\b", observations_for_issue)):
                        continue
                    if question.startswith("If the dishwasher leaks") and not re.search(r"\b(?:leak\w*|water|wet|puddle)\b", observations_for_issue):
                        continue
                if not re.search(known, " ".join(evidence[issue["key"]])) and not any(question in body for body in answered):
                    follow_up = [question]
                    break
            if follow_up:
                break
        if not issues:
            question = GENERAL_QUESTION
            if not any(question in body for body in answered):
                follow_up = [question]
    if pending_question and "dishwasher power switch" in pending_question and re.search(r"\b(?:leak\w*|water|wet|puddle|damaged|burn\w*|smoke|spark\w*)\b", " ".join(evidence.get("dishwasher", []))):
        pending_question = None
    if pending_question and len(messages) < 6 and not active and not wants_worker and not repeated_failure and priority not in {"EMERGENCY", "URGENT_TRIAGE"}:
        follow_up = [pending_question]
    details = " | ".join(messages)
    summary = f"{summary} Reported: {description.strip()}" + (f" Additional details: {details}" if details else "")
    summary = summary[:1500]
    next_action = follow_up[0] if follow_up else "Thanks, that helps. The property manager will join you here to take a look."
    if repeated_failure and open_issues:
        next_action = "The checks you already tried didn’t help. The property manager will take a look."
    if issues and not open_issues:
        follow_up = []
        next_action = "Glad to hear it’s working. Let us know if the problem comes back."
    if priority == "EMERGENCY":
        next_action = ticket.get("safety_message") or SAFETY_MESSAGE
        follow_up = []
        steps = [next_action, "Have qualified emergency responders or technicians assess the hazard before repair work begins."]
    elif priority == "URGENT_TRIAGE":
        next_action = "This needs prompt attention from the property manager. Please avoid trying repairs yourself."
        follow_up = []
    stage = "triage" if follow_up else "handoff"
    return {
        "status": "ready", "summary": summary, "category": category, "priority": priority,
        "trade": trade, "repair_steps": steps, "next_action": next_action, "follow_up": follow_up,
        "source": "rules", "plan_version": PLAN_VERSION, "model": None, "assistant_stage": stage,
        "issues": issues,
        "images_analyzed": 0, "video_frames_analyzed": 0, "audio_analyzed": False,
    }
