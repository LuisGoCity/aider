import json
import os
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth


class Jira:
    def __init__(self, jira_server_url=None, jira_email=None, jira_api_token=None):
        # First try parameters, then environment variables
        self.base_url = jira_server_url or os.environ.get("JIRA_SERVER_URL")
        self.email = jira_email or os.environ.get("JIRA_EMAIL")
        self.api_token = jira_api_token or os.environ.get("JIRA_API_TOKEN")

        if not all([self.base_url, self.email, self.api_token]):
            raise ValueError(
                "Jira configuration is incomplete. Please provide the following either as"
                " parameters or environment variables: JIRA_SERVER_URL, JIRA_EMAIL, JIRA_API_TOKEN"
            )

        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.rest_api_endpoint = self.base_url + "/rest/api"
        self.v2_endpoint = self.rest_api_endpoint + "/2"

        self.json_header = {"Accept": "application/json"}
        self.timestamp_format = "%Y-%m-%dT%H:%M:%S.%f%z"

    def _make_request(self, method, request_url, **kwargs):
        if method not in ["GET", "PUT", "POST", "DELETE"]:
            raise Exception(f"Invalid method requested: {method}.")

        url = self.v2_endpoint + request_url
        try:
            response = requests.request(
                method=method,
                url=url,
                params=kwargs.get("params"),
                data=kwargs.get("data"),
                json=kwargs.get("json_body"),
                headers=(
                    kwargs.get("json_header") if kwargs.get("json_header") else self.json_header
                ),
                auth=self.auth,
            )
        except Exception as e:
            raise Exception(f"Could not make {method} request to url: {url}.\n {e}")

        if response.status_code not in [200, 204]:
            raise Exception(f"{method} request for url {url} raised error: {response.status_code}")

        if response.status_code == 204:
            print("Request completed successfully but returned no content.")
            return

        return json.loads(response.text)

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
            print(self.v2_endpoint + "/issue" + f"/{issue_key_or_id}")
            response = self._make_request(
                method="GET",
                request_url="/issue" + f"/{issue_key_or_id}",
            )
        except Exception as e:
            raise Exception(f"Could not retrieve issue {issue_key_or_id}:\n{e}")

        return response

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

    def get_status_options(self, project_id=None):
        try:
            response = self._make_request(method="GET", request_url="/status")
        except Exception as e:
            raise Exception(f"Could not retrieve status options for {self.base_url}:\n {e}")

        if not project_id:
            return response

        return [
            response_
            for response_ in response
            if response_.get("scope", {}).get("project", {}).get("id") == project_id
        ]

    def get_ticket_status_options(self, issue_key_or_id):
        status_options = self._make_request(
            method="GET", request_url=f"/issue/{issue_key_or_id}/transitions"
        )
        if not status_options.get("transitions"):
            print(f"No status options available for issue {issue_key_or_id}")
            return

        return status_options["transitions"]

    def set_ticket_to_review(self, issue_key_or_id):
        ticket = self.get_issue(issue_key_or_id)
        current_status = ticket["fields"]["status"]

        if "review" in current_status["name"].lower():
            print("Ticket already in review.")
            return

        status_options = self.get_ticket_status_options(issue_key_or_id)
        to_status = [
            status["id"] for status in status_options if "review" in status["name"].lower()
        ]

        if not to_status:
            print(
                "Could not find a review-like status in jira board for project"
                f" {ticket['fields']['project']['name']}."
            )
            return
        else:
            to_status = to_status[0]

        json_body = {"transition": to_status}
        json_header = {"Accept": "application/json", "Content-Type": "application/json"}
        try:
            self._make_request(
                method="POST",
                request_url=f"/issue/{issue_key_or_id}/transitions",
                json_body=json_body,
                json_header=json_header,
            )
        except Exception as e:
            raise Exception(f"Failed to update status field for issue {issue_key_or_id}:\n {e}")

        print(f"Successfully updated status of issue {issue_key_or_id} to review.")
