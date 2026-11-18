import re


SAFE_GUIDANCE = (
    "Ask one useful question at a time, at most six tenant turns; never repeat an answered question. "
    "Offer only familiar normal controls, safe photos, and visible labels or errors; no panels, wiring, gas, chemicals, ladders, force, or dismantling. "
    "A shower control photo can establish normal operation; floor water may be curtain runoff but a separate dishwasher leak remains open. "
    "Ask whether hot water is missing everywhere or at one fixture. An oven that will not turn off and a stuck bulb base need professionals. "
    "A dishwasher supply wall switch is property-specific: never assume one exists. Verify HVAC filter dimensions and fridge filter model from accessible labels before recommending a replacement. "
    "A delivered filter or remote is not a working repair: ask for normal-operation confirmation. A clogged toilet referral is not resolution. "
    "Recurring pests require prompt professional reassessment; do not infer species. Lockouts need authorized human help, never access codes. "
    "Honor fragrance sensitivities when addressing odors. Keep every issue separate; resolve only explicit, issue-specific tenant confirmation. "
    "On handoff, pass the open issues to the property manager. Only after the manager assigns a repairman should visit scheduling begin."
)

HVAC_CONTEXT = r"\b(?:hvac|thermostat|furnace|radiator|central (?:air|heating)|space heat(?:er|ing)|heating system|air condition(?:er|ing)|a/?c)\b|\b(?:house|home|room|bedroom|apartment)\b(?:\s+(?:is|has|feels|stays|too|very|still|really)){0,4}\s+(?:cold|hot|no heat|no cooling|not heating|not cooling)\b|\b(?:heat|heating|cooling)\s+(?:in|throughout|for)\s+(?:the |my |our )?(?:house|home|room|bedroom|apartment)\b"

FAMILIES = {
    "shower_leak": ("leak", "Water outside the shower", r"\bshower\b.{0,70}\b(?:leak\w*|floor|curtain)\b|\b(?:leak\w*|water on (?:the )?floor|floor water|curtain)\b.{0,70}\b(?:shower|bathtub)\b", [
        (r"\b(?:curtain|screen|door)\b.{0,30}\b(?:inside|outside|closed|open)\b", "Is the shower curtain inside the tub, or is the shower door fully closed during normal use? Only observe; do not take anything apart."),
        (r"\b(?:when off|only during|only after|continues|constant|stopped)\b", "Does water reach the floor only during shower use, or does it continue after the normal control is off? Avoid the wet area and do not repeat a check that causes more leakage."),
    ]),
    "shower_drain": ("leak", "Shower drainage", r"\bshower\b.{0,45}\b(?:drain\w*|clog\w*|block\w*)\b|\b(?:drain\w*|clog\w*|block\w*)\b.{0,45}\bshower\b", [
        (r"\b(?:only|other drains|other fixtures|all drains)\b", "Is only the shower draining slowly, or are other drains affected too? Stop using a fixture if water is backing up; do not add drain chemicals."),
    ]),
    "internet": ("general", "Internet or streaming", r"\b(?:internet|wi[ -]?fi|router|modem|buffering|streaming)\b", [
        (r"\b(?:all devices|every device|other devices|only (?:the |one )?(?:tv|phone|laptop)|network visible|network missing)\b", "Is the problem affecting every device or only one, and can you see the usual network? Do not share passwords or access codes."),
        (r"\b(?:tried|restart|reset|reboot|already)\w*\b", "What have you already tried, and what do the normal equipment indicator lights show? Do not reset configuration, disconnect wiring, or repeat a restart that already failed."),
        (r"\b(?:restart|reboot|reset|unfamiliar|cannot|can't)\w*\b", "If you already know the equipment's documented normal restart control and have not tried it, one normal restart may help. Skip it if unfamiliar; never use a factory reset or change wiring. Did service return?"),
    ]),
    "microwave": ("appliance", "Microwave", r"\bmicrowave\b", [
        (r"\b(?:display|light|timer|no power|buttons?|start)\b", "Does the microwave have a normal display but fail to heat, or does it have no power at all? Do not open it, move it, or run it empty."),
    ]),
    "fan": ("electrical", "Ceiling fan", r"\b(?:ceiling fan|bedroom fan|fan (?:is |not |does))\b", [
        (r"\b(?:switch|remote|setting|light|tried)\b", "Does the fan respond to its familiar normal wall switch or remote, and does its light work? Skip unfamiliar controls; do not climb, open a cover, or touch wiring."),
    ]),
    "furniture": ("general", "Furniture or mattress", r"\b(?:mattress|bed frame|broken chair|broken table|broken sofa|broken couch)\b", [
        (r"\b(?:photo|picture|image|stain|broken|sag|damage)\w*\b", "Can you describe or safely photograph the damage? Do not lift heavy furniture or attempt repairs; this helps identify the right replacement or professional."),
    ]),
    "hot_water": ("leak", "Hot water", r"\b(?:hot water|water heater|cold shower)\b|\bshower\b.{0,25}\bcold\b", [
        (r"\b(?:all|every|other)\b.{0,30}\b(?:faucets?|taps?|fixtures?|sinks?)\b|\b(?:only|just)\b.{0,20}\b(?:shower|fixture|faucet)\b|\b(?:throughout|everywhere)\b|\b(?:sink|faucet|tap)\b.{0,35}\b(?:hot|warm|cold)\b", "Does the sink have hot water, or is it cold there too? Please don’t adjust the water heater."),
    ]),
    "shower": ("leak", "Shower controls or water", r"\bshower\b", [
        (r"\b(?:photo|picture|image)\b", "Can you send a photo of the shower's normal controls without removing anything? This can help identify how to operate them safely."),
        (r"\b(?:tried|adjusted|normal controls|works now|working now)\b", "If you recognize the shower controls, use only their normal marked settings without forcing anything. Does that restore normal water flow and temperature? Skip this if the controls are unfamiliar."),
        (r"\b(?:curtain|screen|door)\b.{0,30}\b(?:inside|outside|closed|open)\b", "If water reaches the floor during shower use, is the curtain inside the tub or the shower door fully closed? Only observe; do not take anything apart."),
    ]),
    "dishwasher": ("appliance", "Dishwasher", r"\bdishwasher\b", [
        (r"\b(?:error|code|display|no lights?|no power|blank)\b", "What does the dishwasher's normal display show, including any visible error code? Do not move it or open panels."),
        (r"\b(?:switch\b.{0,35}\b(?:on|tried|checked)|(?:no|cannot find|can[’']t find|not sure|unsure|unfamiliar)\b.{0,35}\bswitch|power (?:is back|returned)|display (?:is on|lit up))\b", "Is there a clearly labeled dishwasher power switch, or one you already know controls it? If it is off, dry, and undamaged, turn it on normally and check the display. Skip this if you are unsure which switch it is, and do not touch a breaker or electrical panel."),
        (r"\b(?:only during|while running|when running|when off|turned off|even when|constant)\b", "If the dishwasher leaks, does water appear only during normal use or also while it is off? Do not run it again if it is leaking."),
    ]),
    "oven": ("appliance", "Oven or stove", r"\b(?:oven|stove|cooktop)\b", [
        (r"\b(?:off|heating|heat|turn on|error|code)\b", "Does the oven or stove respond to its normal off control, or is it continuing to heat? If it will not turn off, stop using it and keep clear for a qualified professional."),
    ]),
    "hvac_filter": ("hvac", "HVAC filter", r"\b(?:air|hvac|furnace|ac)\s+filters?\b|\b\d{1,2}\s*[x×]\s*\d{1,2}\s*[x×]\s*\d\b", [
        (r"\b\d{1,2}\s*[x×]\s*\d{1,2}\s*[x×]\s*\d\b", "What dimensions are printed on the existing HVAC filter or an already accessible label? A photo is useful; do not open equipment or climb to find it."),
    ]),
    "hvac": ("hvac", "Heating or cooling", HVAC_CONTEXT + r"|\b(?:heat|heating|cooling)\b", [
        (r"\b(?:set to|setting|mode|display)\b", "What mode and temperature are shown on the thermostat's normal display? Do not open equipment or electrical panels."),
    ]),
    "fridge_filter": ("appliance", "Refrigerator filter", r"\b(?:fridge|refrigerator|water)\s+filter\b", [
        (r"\b(?:model|part number|label says)\b", "Can you share the refrigerator model or filter part number from an already visible label? Verify that before ordering; do not move or dismantle the appliance."),
    ]),
    "fridge": ("appliance", "Refrigerator", r"\b(?:fridge|refrigerator|freezer)\b", [
        (r"\b(?:error|code|display|temperature)\b", "What temperature or error appears on the refrigerator's normal display? Please observe without moving or opening equipment panels."),
    ]),
    "bulb": ("electrical", "Light bulb or fixture", r"\b(?:bulb|light fixture)\b", [
        (r"\b(?:stuck|broken|base|socket)\b", "Is the bulb intact, or is a broken bulb base stuck in the socket? Do not touch the socket or attempt to remove a stuck base."),
    ]),
    "toilet": ("leak", "Toilet", r"\btoilet\b", [
        (r"\b(?:overflow|rising|stable|drain|clog|block)\w*\b", "Is the toilet water rising or overflowing, or is the level stable? Do not flush again if it is blocked or rising."),
    ]),
    "remote": ("appliance", "TV remote", r"\b(?:remote|television|tv)\b", [
        (r"\b(?:brand|model|photo|picture)\b", "Can you share a photo of the remote and the TV brand or an already visible model label so a compatible replacement can be identified?"),
    ]),
    "pest": ("pest_mold", "Pests", r"\b(?:pests?|bugs?|roaches?|cockroaches?|ants?|mice|rats?|bedbugs?)\b", [
        (r"\b(?:again|return|recurr|after treatment|treated)\w*\b", "Where are you seeing pests, and have they returned after treatment? A safe photo can help a professional assess them; do not apply chemicals."),
    ]),
    "lock": ("lock", "Door or lock access", r"\b(?:lock(?:ed)?|lockout|door|key)\b", [
        (r"\b(?:locked out|cannot get in|can't get in|cannot secure|can't lock|can secure)\b", "Can you enter and secure the home using the door normally? Do not force it or share access codes; an authorized person can help with access."),
    ]),
    "odor": ("general", "Odor", r"\b(?:odor|odour|smoky|smell)\b", [
        (r"\b(?:fragrance|scent|sensitive|sensitivity)\b", "Where is the odor strongest, and are there fragrance sensitivities the repair team should honor? Do not mask the odor with sprays or chemicals."),
    ]),
    "sink": ("leak", "Sink or faucet", r"\b(?:sink|faucet|tap)\b", [
        (r"\b(?:drip|steady|constant|blocked|clogged|drain)\b", "Is the sink or faucet leaking, draining slowly, or failing to deliver water? Please observe without taking anything apart."),
    ]),
    "laundry": ("appliance", "Washer or dryer", r"\b(?:washer|dryer|washing machine)\b", [
        (r"\b(?:error|code|display)\b", "What does the washer or dryer's normal display show, including any visible error code? Do not move it or open panels."),
    ]),
    "electrical": ("electrical", "Electrical fixture or outlet", r"\b(?:outlet|socket|wiring|electrical)\b", [
        (r"\b(?:kitchen|bedroom|bathroom|living room)\b", "Which room contains the affected electrical fixture or outlet? Observe from a safe distance without touching wiring or opening panels."),
    ]),
    "mold": ("pest_mold", "Mold or dampness", r"\b(?:mold|mould|dampness)\b", [
        (r"\b(?:photo|picture|image)\b", "Can you share a photo of the affected area from a safe distance? Do not disturb mold or apply chemicals."),
    ]),
    "structural": ("structural", "Building damage", r"\b(?:ceiling|roof|crack|cracked|wall damage|fence|vent cover)\b", [
        (r"\b(?:photo|picture|image)\b", "Can you share a photo of the damage from a stable, safe position? Do not climb or disturb damaged materials."),
    ]),
    "leak": ("leak", "Other water leak", r"\b(?:leak|leaking|water on (?:the )?floor|floor water)\b", [
        (r"\b(?:steady|drip|continuous|constant|only during|when off)\b", "Is water dripping or flowing steadily, and does it continue when the fixture is turned off normally? Do not force controls or take anything apart."),
    ]),
}


def matching_families(text):
    keys = [key for key, (_, _, pattern, _) in FAMILIES.items() if re.search(pattern, text, re.I)]
    for specific, general in (("hvac_filter", "hvac"), ("fridge_filter", "fridge"), ("bulb", "electrical")):
        if specific in keys and general in keys:
            keys.remove(general)
    if "shower" in keys and any(key in keys for key in ("shower_leak", "shower_drain")):
        keys.remove("shower")
    if "leak" in keys and any(key in keys for key in ("shower", "shower_leak", "shower_drain", "dishwasher", "toilet", "fridge", "sink", "laundry")):
        keys.remove("leak")
    if "hot_water" in keys and "shower" in keys and not re.search(r"\b(?:leak|control|handle|curtain|floor)\b", text, re.I):
        keys.remove("shower")
    if "hot_water" in keys and "sink" in keys and not re.search(r"\b(?:leak|drain|clog|block)\w*\b", text, re.I):
        keys.remove("sink")
    if "hvac" in keys and any(key in keys for key in ("microwave", "oven", "dishwasher", "fridge", "laundry", "hot_water")) and not re.search(HVAC_CONTEXT, text, re.I):
        keys.remove("hvac")
    if "lock" in keys and any(key in keys for key in ("shower", "microwave", "dishwasher", "oven", "fridge", "laundry")) and not re.search(r"\b(?:lock|locked|key|lockout)\b", text, re.I):
        keys.remove("lock")
    if "internet" in keys and "remote" in keys and not re.search(r"\b(?:remote|button|battery|batteries)\b", text, re.I):
        keys.remove("remote")
    if "fan" in keys and "structural" in keys and not re.search(r"\b(?:crack\w*|sagg\w*|collaps\w*|hole|water damage|leak\w*)\b", text, re.I):
        keys.remove("structural")
    return keys


def explicit_resolution(text):
    normalized = " ".join(text.lower().replace("’", "'").split())
    subject = r"(?:it|everything|all(?: (?:reported )?(?:issues|problems|repairs))?|both(?: (?:issues|problems|repairs))?|(?:(?:the|my|our) )?(?:dishwasher|shower|shower controls?|shower drain|water leak|leak|hot water|oven|stove|microwave|refrigerator|fridge|freezer|filter|filters|hvac filter|air filters|fan|ceiling fan|toilet|sink|faucet|internet|wi[ -]?fi|connection|tv|remote|lock|door|heater|heating|cooling|ac|air conditioning|washer|dryer|repair|problem|issue))"
    restored = r"(?:(?:is|are|has been|have been) )?(?:fixed|resolved|working now|working normally|now working|back|restored)|works now|works normally|now works|stopped leaking"
    return re.fullmatch(r"(?:yes[,!. ]+)?(?:i (?:can )?confirm(?: that)? )?" + subject + r" (?:" + restored + r")[.!]?(?: (?:thank you|thanks)[.!]?)?", normalized) is not None


def tracked_issues(description, messages):
    issues = {}
    for index, body in enumerate([description, *messages]):
        if index and re.match(r"(?:yes[,!. ]+)?(?:i (?:can )?confirm(?: that)? )?(?:all|both|everything)\b", body.strip(), re.IGNORECASE) and explicit_resolution(body):
            for issue in issues.values():
                issue.update(status="reported_resolved", evidence=body.strip()[:300])
            continue
        if index and len(issues) == 1 and not matching_families(body) and explicit_resolution(body):
            next(iter(issues.values())).update(status="reported_resolved", evidence=body.strip()[:300])
            continue
        for clause in re.split(r"[.!?;\n]+|\bbut\b|\band\b", body, flags=re.I):
            keys = matching_families(clause)
            if "hvac" in keys and "hvac" not in issues and any(key in issues for key in ("microwave", "oven", "dishwasher", "fridge", "laundry", "hot_water")) and not re.search(HVAC_CONTEXT, clause, re.I) and (index > 0 and not re.match(r"\s*(?:also|separately|another problem|another issue|in addition)\b", clause, re.I) or re.match(r"\s*(?:it|this|that|still|not|no|doesn[’']?t|won[’']?t|isn[’']?t)\b", clause, re.I)):
                keys.remove("hvac")

            negative = re.search(r"\b(?:not|no|never|isn't|isnt|hasn't|hasnt|won't|wont|still|again|returned|recurr\w*|was|previously|thought|says|said|claims|if|hope|maybe|might|should|would|will|tomorrow|need|want|please)\b", clause, re.I)
            healthy = explicit_resolution(clause) or re.search(r"\b(?:works (?:fine|normally|properly)|(?:is|are) (?:fine|okay|ok|working (?:fine|normally|properly)))\s*$", clause.strip(), re.I)
            for key in keys:
                if key not in issues and healthy:
                    continue
                issue = issues.setdefault(key, {"key": key, "title": FAMILIES[key][1], "status": "open", "evidence": clause.strip()[:300]})
                if index and len(keys) == 1 and explicit_resolution(clause) and not negative and "?" not in body and (len(matching_families(body)) > 1 or not re.search(r"\b(?:not|never|still|again|think|maybe|apparently|according)\b|don['’]t|aren['’]t", body, re.IGNORECASE)):
                    issue.update(status="reported_resolved", evidence=clause.strip()[:300])
                elif negative or re.search(r"\b(?:broken|leaking|failed|clogged|blocked|stuck|doesn't|doesnt|cannot|can't)\b", clause, re.I):
                    issue.update(status="open", evidence=clause.strip()[:300])
    return list(issues.values())
