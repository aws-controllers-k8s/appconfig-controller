# Copyright Amazon.com Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may
# not use this file except in compliance with the License. A copy of the
# License is located at
#
#         http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Integration tests for the AppConfig Application resource."""

import boto3
import pytest
import time
import logging
from typing import Dict, Tuple

from acktest.resources import random_suffix_name
from acktest.k8s import resource as k8s
from acktest.k8s import condition

from e2e import service_marker, CRD_GROUP, CRD_VERSION, load_appconfig_resource
from e2e.replacement_values import REPLACEMENT_VALUES

RESOURCE_PLURAL = "applications"

CREATE_WAIT_AFTER_SECONDS = 10
UPDATE_WAIT_AFTER_SECONDS = 10
DELETE_WAIT_AFTER_SECONDS = 10


@pytest.fixture(scope="module")
def appconfig_client():
    return boto3.client("appconfig")


def get_application(appconfig_client, application_id: str) -> dict:
    """Get an AppConfig application by ID."""
    try:
        return appconfig_client.get_application(ApplicationId=application_id)
    except appconfig_client.exceptions.ResourceNotFoundException:
        return None


def get_application_tags(appconfig_client, resource_arn: str) -> dict:
    """Get tags for an AppConfig resource."""
    return appconfig_client.list_tags_for_resource(ResourceArn=resource_arn).get("Tags", {})


def application_exists(appconfig_client, application_id: str) -> bool:
    """Check if an AppConfig application exists."""
    return get_application(appconfig_client, application_id) is not None


@service_marker
@pytest.mark.canary
class TestApplication:
    def _create_application(
        self,
        name: str,
        replacements: Dict[str, str] = {},
    ) -> Tuple[k8s.CustomResourceReference, dict]:
        """Helper to create an Application CR and wait for it to be synced."""
        resource_name = name
        replacements["APPLICATION_NAME"] = resource_name

        all_replacements = {**REPLACEMENT_VALUES, **replacements}

        ref = k8s.CustomResourceReference(
            CRD_GROUP,
            CRD_VERSION,
            RESOURCE_PLURAL,
            resource_name,
            namespace="default",
        )
        resource_data = load_appconfig_resource(
            "application",
            additional_replacements=all_replacements,
        )
        k8s.create_custom_resource(ref, resource_data)
        time.sleep(CREATE_WAIT_AFTER_SECONDS)
        cr = k8s.wait_resource_consumed_by_controller(ref)
        assert cr is not None
        assert "status" in cr
        assert "id" in cr["status"]
        return ref, cr

    def test_create_read_delete(self, appconfig_client):
        """Test creating, reading, and deleting an Application."""
        app_name = random_suffix_name("ack-test-app", 24)

        ref, cr = self._create_application(app_name)

        try:
            # Verify the resource is synced
            condition.assert_synced(ref)

            # Re-fetch the CR to get the latest state (including ARN)
            cr = k8s.get_resource(ref)

            # Verify the CR has the expected fields
            assert cr["spec"]["name"] == app_name
            assert cr["spec"]["description"] == "ACK e2e test application"
            assert cr["status"]["id"] is not None

            application_id = cr["status"]["id"]

            # Verify the resource exists in AWS
            aws_app = get_application(appconfig_client, application_id)
            assert aws_app is not None
            assert aws_app["Name"] == app_name
            assert aws_app["Description"] == "ACK e2e test application"

            # Verify tags in AWS
            resource_arn = cr["status"]["ackResourceMetadata"]["arn"]
            aws_tags = get_application_tags(appconfig_client, resource_arn)
            assert "environment" in aws_tags
            assert aws_tags["environment"] == "test"
            assert "managed-by" in aws_tags
            assert aws_tags["managed-by"] == "ack"

        finally:
            # Delete the resource
            _, deleted = k8s.delete_custom_resource(ref, 3, 5)
            assert deleted
            time.sleep(DELETE_WAIT_AFTER_SECONDS)

            # Verify the resource no longer exists in AWS
            assert not application_exists(appconfig_client, cr["status"]["id"])

    def test_update_description_and_name(self, appconfig_client):
        """Test updating an Application's description and name."""
        app_name = random_suffix_name("ack-test-app", 24)

        ref, cr = self._create_application(app_name)

        try:
            condition.assert_synced(ref)
            application_id = cr["status"]["id"]

            # Capture the synced condition timestamp before patching
            pre_update_time = condition.get_synced_last_transition_time(ref)

            # Update the description
            updates = {
                "spec": {
                    "description": "Updated description",
                },
            }
            k8s.patch_custom_resource(ref, updates)
            time.sleep(UPDATE_WAIT_AFTER_SECONDS)

            # Wait for the controller to reconcile the update
            assert k8s.wait_on_condition_after(
                ref,
                "ACK.ResourceSynced",
                "True",
                last_transition_after=pre_update_time,
                wait_periods=3,
                period_length=10,
            )

            # Verify the update in the CR
            cr = k8s.get_resource(ref)
            assert cr["spec"]["description"] == "Updated description"

            # Verify the update in AWS
            aws_app = get_application(appconfig_client, application_id)
            assert aws_app is not None
            assert aws_app["Description"] == "Updated description"

        finally:
            _, deleted = k8s.delete_custom_resource(ref, 3, 5)
            assert deleted

    def test_update_tags(self, appconfig_client):
        """Test updating an Application's tags."""
        app_name = random_suffix_name("ack-test-app", 24)

        ref, cr = self._create_application(app_name)

        try:
            condition.assert_synced(ref)

            # Re-fetch the CR to get the latest state (including ARN)
            cr = k8s.get_resource(ref)
            resource_arn = cr["status"]["ackResourceMetadata"]["arn"]

            # Capture the synced condition timestamp before patching
            pre_update_time = condition.get_synced_last_transition_time(ref)

            # Update tags: change one, add one, remove one
            # Note: strategic merge patch merges map keys, so to remove
            # a tag we must explicitly set it to None (null).
            updates = {
                "spec": {
                    "tags": {
                        "environment": "production",  # changed
                        "new-tag": "new-value",       # added
                        "managed-by": None,            # removed
                    },
                },
            }
            k8s.patch_custom_resource(ref, updates)
            time.sleep(UPDATE_WAIT_AFTER_SECONDS)

            # Wait for the controller to reconcile the update
            assert k8s.wait_on_condition_after(
                ref,
                "ACK.ResourceSynced",
                "True",
                last_transition_after=pre_update_time,
                wait_periods=3,
                period_length=10,
            )

            # Verify tags in AWS
            aws_tags = get_application_tags(appconfig_client, resource_arn)
            assert aws_tags.get("environment") == "production"
            assert aws_tags.get("new-tag") == "new-value"
            assert "managed-by" not in aws_tags

            # Verify tags in the CR
            cr = k8s.get_resource(ref)
            cr_tags = cr["spec"].get("tags", {})
            assert cr_tags.get("environment") == "production"
            assert cr_tags.get("new-tag") == "new-value"

        finally:
            _, deleted = k8s.delete_custom_resource(ref, 3, 5)
            assert deleted
