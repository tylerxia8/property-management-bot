"""Read models for the resident maintenance workspace and manager queue."""

from sqlalchemy import text


def homes(session, organization_id, user_id):
    rows = (
        session.execute(
            text("""
        SELECT h.* FROM app_maintenance_homes() h
        WHERE EXISTS (SELECT 1 FROM lease_parties lp WHERE lp.organization_id = :org
          AND lp.lease_id = h.lease_id AND lp.user_id = :user)
        ORDER BY h.property_name, h.unit_label, h.lease_id
    """),
            {"org": organization_id, "user": user_id},
        )
        .mappings()
        .all()
    )
    return [
        {**dict(row), "lease_id": str(row["lease_id"]), "unit_id": str(row["unit_id"])}
        for row in rows
    ]


def ticket_list(session, organization_id, user_id, manager, limit, before):
    rows = (
        session.execute(
            text("""
        SELECT t.id, t.ticket_number, t.status, t.category, t.description, t.emergency,
               t.urgent_triage, t.created_at, h.property_name, h.unit_label
        FROM maintenance_tickets t
        LEFT JOIN app_maintenance_homes() h ON h.lease_id = t.lease_id
        WHERE t.organization_id = :org AND (:manager OR t.reporter_user_id = :user)
          AND (CAST(:before AS bigint) IS NULL OR t.ticket_number < :before)
        ORDER BY t.ticket_number DESC LIMIT :limit
    """),
            {
                "org": organization_id,
                "user": user_id,
                "manager": manager,
                "limit": limit + 1,
                "before": before,
            },
        )
        .mappings()
        .all()
    )
    items = []
    for row in rows[:limit]:
        item = dict(row)
        item["id"] = str(row["id"])
        item["created_at"] = row["created_at"].isoformat()
        item["priority"] = (
            "EMERGENCY"
            if row["emergency"]
            else "URGENT_TRIAGE"
            if row["urgent_triage"]
            else "ROUTINE_REVIEW_PENDING"
        )
        item.pop("urgent_triage")
        items.append(item)
    return {
        "items": items,
        "next_cursor": str(items[-1]["ticket_number"]) if len(rows) > limit else None,
    }


def ticket_details(session, organization_id, ticket_id):
    row = (
        session.execute(
            text("""
        SELECT t.description, t.created_at, h.property_name, h.unit_label,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('id',m.id,'body',m.body,'created_at',m.created_at) ORDER BY m.created_at,m.id)
          FROM ticket_messages m WHERE m.organization_id = t.organization_id AND m.ticket_id = t.id), '[]'::jsonb) AS messages,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('id',m.id,'status',m.status,'rejection_reason',m.rejection_reason,'content_type',COALESCE(m.detected_type,m.declared_content_type)) ORDER BY m.created_at,m.id)
          FROM media_objects m WHERE m.organization_id = t.organization_id AND m.ticket_id = t.id), '[]'::jsonb) AS media,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('status',m.status,'reason',m.reason,'created_at',m.created_at) ORDER BY m.created_at,m.id)
          FROM maintenance_status_updates m WHERE m.organization_id = t.organization_id AND m.ticket_id = t.id), '[]'::jsonb) AS history
        FROM maintenance_tickets t
        LEFT JOIN app_maintenance_homes() h ON h.lease_id = t.lease_id
        WHERE t.organization_id = :org AND t.id = :id
    """),
            {"org": organization_id, "id": ticket_id},
        )
        .mappings()
        .one()
    )
    return {**dict(row), "created_at": row["created_at"].isoformat()}


def report_once(session, principal, key, hashed, create, load):
    from uuid import uuid4
    from grok_bot.errors import problem

    # Serialize retries for this actor and key, including simultaneous submissions.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"maintenance:{principal.organization_id}:{principal.user_id}:{key}"},
    )
    params = {"org": principal.organization_id, "actor": principal.user_id, "key": key}
    existing = (
        session.execute(
            text(
                "SELECT request_hash, ticket_id FROM maintenance_report_keys WHERE organization_id = :org AND actor_id = :actor AND key = :key"
            ),
            params,
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != hashed:
            problem(
                409,
                "IDEMPOTENCY_CONFLICT",
                "This request key was already used for different details.",
            )
        return load(existing["ticket_id"])
    result = create()
    session.execute(
        text(
            "INSERT INTO maintenance_report_keys (id, organization_id, actor_id, key, request_hash, ticket_id) VALUES (:id,:org,:actor,:key,:hashed,:ticket)"
        ),
        {**params, "id": uuid4(), "hashed": hashed, "ticket": result["id"]},
    )
    return result
