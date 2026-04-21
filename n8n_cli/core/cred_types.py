"""Map `n8n-nodes-base.*` types to the credential types they can consume.

Built from n8n's public node catalog. Not exhaustive — extended as real
workflows surface new pairings. For unknown types we fall back to returning
the empty set, which makes `credential list --for-node` return nothing
and prompts the user to pass `--for-node-type` explicitly.
"""

from __future__ import annotations

_MAP: dict[str, tuple[str, ...]] = {
    "n8n-nodes-base.httpRequest": (
        "httpBasicAuth",
        "httpBearerAuth",
        "httpCustomAuth",
        "httpDigestAuth",
        "httpHeaderAuth",
        "httpQueryAuth",
        "oAuth1Api",
        "oAuth2Api",
    ),
    "n8n-nodes-base.googleSheets": ("googleApi", "googleSheetsOAuth2Api"),
    "n8n-nodes-base.googleDrive": ("googleApi", "googleDriveOAuth2Api"),
    "n8n-nodes-base.gmail": ("googleApi", "gmailOAuth2"),
    "n8n-nodes-base.slack": ("slackApi", "slackOAuth2Api"),
    "n8n-nodes-base.notion": ("notionApi", "notionOAuth2Api"),
    "n8n-nodes-base.postgres": ("postgres",),
    "n8n-nodes-base.mongoDb": ("mongoDb",),
    "n8n-nodes-base.mysql": ("mySql",),
    "n8n-nodes-base.redis": ("redis",),
    "n8n-nodes-base.telegram": ("telegramApi",),
    "n8n-nodes-base.openAi": ("openAiApi",),
    "n8n-nodes-base.github": ("githubApi", "githubOAuth2Api"),
    "n8n-nodes-base.gitlab": ("gitlabApi", "gitlabOAuth2Api"),
    "n8n-nodes-base.airtable": ("airtableApi", "airtableTokenApi", "airtableOAuth2Api"),
    "n8n-nodes-base.jira": ("jiraSoftwareApi", "jiraSoftwareCloudApi", "jiraSoftwareServerApi"),
    "n8n-nodes-base.stripe": ("stripeApi",),
    "n8n-nodes-base.twilio": ("twilioApi",),
    "n8n-nodes-base.sendGrid": ("sendGridApi",),
    "n8n-nodes-base.mailgun": ("mailgunApi",),
    "n8n-nodes-base.webhook": (),  # no credential input
    "n8n-nodes-base.manualTrigger": (),
    "n8n-nodes-base.set": (),
    "n8n-nodes-base.code": (),
    "n8n-nodes-base.if": (),
}


def credential_types_for_node_type(node_type: str) -> tuple[str, ...]:
    return _MAP.get(node_type, ())


def credential_types_for_node_name(node_type_or_name: str) -> tuple[str, ...]:
    """Support the `--for-node "HTTP Request"` UX by matching a display name.

    We fall back on a lowercase substring match against the last segment of
    our known types, so 'HTTP Request' maps to 'n8n-nodes-base.httpRequest'.
    """
    if node_type_or_name in _MAP:
        return _MAP[node_type_or_name]
    normalized = node_type_or_name.lower().replace(" ", "")
    for type_name, creds in _MAP.items():
        short = type_name.split(".")[-1].lower()
        if short == normalized:
            return creds
    return ()
