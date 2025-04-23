def add_jira_args(parser):
    """Add Jira-related command line arguments to the parser."""

    jira_group = parser.add_argument_group("Jira Integration")

    jira_group.add_argument(
        "--jira-server-url",
        help="Jira server URL (e.g., https://your-domain.atlassian.net)",
    )

    jira_group.add_argument(
        "--jira-email",
        help="Email address associated with your Jira account",
    )

    jira_group.add_argument(
        "--jira-api-token",
        help="Jira API token for authentication",
    )
