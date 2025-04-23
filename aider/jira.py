import json
import os
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth


class Jira:
    def __init__(self):
        self.base_url = os.environ.get("JIRA_SERVER_URL")
        self.email = os.environ.get("JIRA_EMAIL")
        self.api_token = os.environ.get("JIRA_API_TOKEN")

        if not all([self.base_url, self.email, self.api_token]):
            raise ValueError(
                "One of the following env variables required for JIRA has not been roperly set: "
                "JIRA_SERVER_URL, JIRA_EMAIL, JIRA_API_TOKEN"
            )

        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.rest_api_endpoint = self.base_url + "/rest/api"
        self.v2_endpoint = self.rest_api_endpoint + "/2"

        self.json_header = {"Accept": "application/json"}
        self.timestamp_format = "%Y-%m-%dT%H:%M:%S.%f%z"

    def _get_comments_content(self, comments):
        return [
            {
                "author": comment["author"]["displayName"],
                "last_updated": datetime.strptime(
                    comment["updated"], self.timestamp_format
                ).isoformat(timespec="minutes"),
                "comment": comment["body"],
            }
            for comment in comments
        ]

    def get_issue(self, issue_key_or_id):
        try:
            response = requests.request(
                method="GET", url=self.v2_endpoint + "/issue" + f"/{issue_key_or_id}"
            )
        except Exception as e:
            raise Exception(f"Could not retrieve issue {issue_key_or_id}:\n{e}")

        if response.status_code != 200:
            raise Exception(
                f"Request for issue {issue_key_or_id} raised error: {response.status_code}"
            )

        return json.loads(response.text)

    def get_issue_content(self, issue_key_or_id):
        issue = self.get_issue(issue_key_or_id)
        summary = issue["fields"]["summary"]
        description = issue["fields"]["description"]

        issue_content = {
            "summary": summary,
            "description": description,
        }

        comments = issue["fields"]["comment"]["comments"]

        if comments:
            comments = self._get_comments_content(comments)

            issue_content["comments"] = comments

        return issue_content
