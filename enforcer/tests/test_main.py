# Standard Library Imports
import json
import unittest
import mock

# Third party imports
from googleapiclient import discovery
from google.cloud import storage, resource_manager

# Local Imports
import main
from main import get_addresses, delete_addresses, exclusions_from_bucket, project_ids_list


class EnforcerTest(unittest.TestCase):

    def setUp(self):
        # Mock Project ID
        self.project = "python-test-case"

    @mock.patch.object(storage, 'Client')
    def test_exclusions_from_bucket(self, mock_client):
        with open('tests/fixtures/exclusions.jsonl') as file:
            exclusions = file.read()
        mock_client.return_value.bucket.return_value.get_blob.return_value.download_as_string.return_value = exclusions
        mock_client = mock.MagicMock()
        response = exclusions_from_bucket()
        self.assertEqual(response[0], '123456')
        self.assertEqual(response[1], '654321')
        self.assertEqual(response[2], 'xpn')

    @mock.patch.object(resource_manager, 'Client')
    @mock.patch.object(main, 'exclusions_from_bucket')
    def test_project_ids_list(self, mock_exclusions_from_bucket, mock_client):
        # Import Project class from Google Cloud Resource Manager
        from google.cloud.resource_manager.project import Project
        # Create dummy client object to use in mock projects
        client = object()
        # Mock return value of exclusions_from_bucket
        mock_exclusions_from_bucket.return_value = ['654321', '123456', 'xpn']
        mock_exclusions_from_bucket = mock.MagicMock()
        # Test Case Project A
        project_a_id = "python-test-case"
        display_name = "Python Test Case"
        labels = {"foo": "bar"}
        mock_project_a = Project(project_a_id, client, name=display_name, labels=labels)
        # Test Case Project B
        project_b_id = "test-xpn"
        display_name = "Test Exclusion"
        mock_project_b = Project(project_b_id, client, name=display_name, labels=labels)
        # Test Case List of Projects
        projects_list = [mock_project_a, mock_project_b]
        # Mock client.list_projects()
        mock_client.return_value.list_projects.return_value = projects_list
        mock_client = mock.MagicMock()
        # Execute function and store the output in a variable
        folder_id = "987654321"
        result = project_ids_list(folder_id)
        # Assert first return value is 'python-test-case'
        self.assertEqual(result[0], 'python-test-case')
        # Assert length is only one project (one gets excluded)
        self.assertEqual(len(result), 1)

    @mock.patch.object(discovery, 'build')
    def test_get_addresses2(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.addresses().aggregatedList() response JSON data
        with open('tests/fixtures/gce.addresses.aggregatedList.json') as json_file:
            addresses_json = json.load(json_file)
        # Mock service.addresses().aggregatedList().execute() response
        mock_service.addresses.return_value.aggregatedList.return_value.execute.return_value = addresses_json
        # Mock service.addresses().aggregatedList_next() to avoid loop
        mock_service.addresses.return_value.aggregatedList_next.return_value = None
        # Make call with mocked values
        response = get_addresses(mock_service, self.project)
        self.assertEqual(response['regions/us-central1']['addresses'][0]['address'], '123.123.123.123')
        # Mock Error
        mock_get_error = mock.MagicMock()
        mock_error = SystemError()
        # Mock aggregatedList Error
        mock_get_error.aggregatedList.return_value.execute.return_value = mock_error
        mock_service.addresses = mock.MagicMock(return_value=mock_get_error)
        # Assertion
        self.assertRaises(SystemError, get_addresses(mock_service, self.project))

    @mock.patch.object(discovery, 'build')
    def test_delete_regional_reserved_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.addresses().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            delete_ip = json.load(json_file)
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-reserved-regional.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.addresses.return_value.delete.return_value.execute.return_value = delete_ip
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')

    @mock.patch.object(discovery, 'build')
    def test_delete_global_reserved_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.addresses().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            delete_ip = json.load(json_file)
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-reserved-global.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.globalAddresses.return_value.delete.return_value.execute.return_value = delete_ip
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')

    @mock.patch.object(discovery, 'build')
    def test_delete_global_inuse_forwarding_rule_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.globalForwardingRules().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            gce_operation = json.load(json_file)
        # Map imported JSON payload to service.globalForwardingRules().delete() return value
        mock_service.globalForwardingRules.return_value.delete.return_value.execute.return_value = gce_operation
        mock_service.globalOperations.return_value.get.return_value.execute.return_value = gce_operation
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-inuse-global.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.globalAddresses.return_value.delete.return_value.execute.return_value = gce_operation
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')

    @mock.patch.object(discovery, 'build')
    def test_delete_regional_inuse_forwarding_rule_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.globalForwardingRules().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            gce_operation = json.load(json_file)
        # Map imported JSON payload to service.globalForwardingRules().delete() return value
        mock_service.forwardingRules.return_value.delete.return_value.execute.return_value = gce_operation
        mock_service.regionOperations.return_value.get.return_value.execute.return_value = gce_operation
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-inuse-regional-forwarding-rule.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.addresses.return_value.delete.return_value.execute.return_value = gce_operation
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')

    @mock.patch.object(discovery, 'build')
    def test_delete_regional_inuse_instance_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.globalForwardingRules().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            gce_operation = json.load(json_file)
        # Map imported JSON payload to service.globalForwardingRules().delete() return value
        mock_service.instances.return_value.delete.return_value.execute.return_value = gce_operation
        mock_service.zoneOperations.return_value.get.return_value.execute.return_value = gce_operation
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-inuse-regional-instance.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.addresses.return_value.delete.return_value.execute.return_value = gce_operation
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')

    @mock.patch.object(discovery, 'build')
    def test_delete_regional_inuse_router_address(self, mock_service):
        # Mock Discovery API
        mock_service = mock.MagicMock()
        # Import service.routers().delete() response JSON data
        with open('tests/fixtures/gce.operation.response.json') as json_file:
            gce_operation = json.load(json_file)
        # Map imported JSON payload to service.routers().delete() return value
        mock_service.routers.return_value.delete.return_value.execute.return_value = gce_operation
        mock_service.regionOperations.return_value.get.return_value.execute.return_value = gce_operation
        # Import get-addresses response JSON data
        with open('tests/fixtures/address-inuse-regional-router.json') as json_file:
            address = json.load(json_file)
        # Map imported JSON payload to service.addresses().delete() return value
        mock_service.addresses.return_value.delete.return_value.execute.return_value = gce_operation
        # Make call with mocked return values
        response = delete_addresses(mock_service, self.project, address)
        # Assertion (to test delete
        self.assertEquals(response['operationType'], 'delete')
