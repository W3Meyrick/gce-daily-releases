import time
import json
import re
import logging
import requests
from sys import stdout
from os import environ
from googleapiclient import discovery
from google.cloud import storage, resource_manager
from pprint import pprint

__METADATA_URL = 'http://metadata.google.internal/computeMetadata/v1/'
__METADATA_HEADERS = {'Metadata-Flavor': 'Google'}
__EXCLUSIONS_FILE_NAME = 'oceanEIMExclusion.jsonl'
__NON_EIM_EXCLUSIONS = ["xpn"]


def get_logger(name, log_file, debug=False):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    file_stream = logging.FileHandler(log_file)

    fmt = logging.Formatter('%(asctime)s [%(threadName)s] '
                            '[%(name)s] %(levelname)s: %(message)s')
    file_stream.setFormatter(fmt)
    logger.addHandler(file_stream)
    if debug:
        debug_stream = logging.StreamHandler(stdout)
        debug_stream.setFormatter(fmt)
        logger.addHandler(debug_stream)
        logger.setLevel(logging.DEBUG)

    return logger


__log = get_logger(__name__, 'ocean-ip-enforcer.log', False)


def __get_metadata_path_param(metadata_param):
    ''' Takes parameter to be added to metadata_url path to retrieve either
        a project id (project/project-id) or an instance id (instance/id) '''
    url = __METADATA_URL + metadata_param
    response = requests.get(url, headers=__METADATA_HEADERS)
    return str(response.text)


__FUNCTION_PROJECT_ID = __get_metadata_path_param('project/project-id')


def exclusions_from_bucket():
    """
    Pulls exceptions file from Cloud storage and returns the content as a list of exclusions
    :return: List of JSON
    """
    client = storage.Client()
    bucket = client.bucket(__FUNCTION_PROJECT_ID + '-data-files')
    blob = bucket.get_blob(__EXCLUSIONS_FILE_NAME)
    blob_as_string = blob.download_as_string()
    list_of_dicts = blob_as_string.splitlines()
    list_of_exclusions = []
    for line in list_of_dicts:
        line_dict = json.loads(line)
        values = list(line_dict.values())
        list_of_exclusions.append(values[0])
    list_of_exclusions.extend(__NON_EIM_EXCLUSIONS)
    return list_of_exclusions


def project_ids_list(folder_id):
    projects_to_exclude = exclusions_from_bucket()
    client = resource_manager.Client()
    project_filter = {'parent.type': 'folder', 'parent.id': folder_id}
    projects = list(client.list_projects())
    project_ids = []
    for project in projects:
        if not re.search(r".*({}).*".format("|".join(projects_to_exclude)), project.project_id):
            project_ids.append(project.project_id)
    return project_ids


def get_addresses(service, project):
    request = service.addresses().aggregatedList(project=project)
    addresses = {}

    while request is not None:
        try:
            response = request.execute()

            for name, addresses_scoped_list in response['items'].items():
                value = {k: v for (k, v) in addresses_scoped_list.items() if k == "addresses"}
                if value:
                    addresses[name] = addresses_scoped_list

            request = service.addresses().aggregatedList_next(previous_request=request, previous_response=response)
        except Exception as e:
            __log.error(e)
            return

    return addresses


def delete_addresses(service, project, addresses):
    for k, v in addresses.items():

        if k == "global":
            region = k
        else:
            region = k.split('/')[1]

        for item in v['addresses']:
            if item['addressType'] == "EXTERNAL":

                status = item['status']
                regional = item.get('region')
                address = item["address"]
                name = item['name']

                if status == "IN_USE":
                    zone = item["users"][0].split('/')[-3]
                    consumer_type = item["users"][0].split('/')[-2]
                    consumer_name = item["users"][0].split('/')[-1]

                if status == "RESERVED" and not regional:
                    __log.info("OCEAN deleting IP address {} from {} global reservation.".format(address, project))
                    try:
                        response = delete_global_address_reservation(service, project, name)
                        _log.warning('OCEAN deleted IP address {} from {}'.format(address, project))
                        return response
                    except Exception as e:
                        __log.error(e)

                elif status == "RESERVED" and regional:
                    __log.info("OCEAN deleting IP address {} from {}".format(address, project))
                    try:
                        # delete_address_reservation(service, project, region, name)
                        response = service.addresses().delete(project=project, region=region, address=address).execute()
                        _log.warning('OCEAN deleted IP address {} from {}'.format(address, project))
                        return response
                    except Exception as e:
                        __log.error(e)

                elif status == "IN_USE" and consumer_type == "forwardingRules":
                    if not regional:
                        try:
                            __log.info("OCEAN deleting resource {} from {}.".format(consumer_name, project))
                            operation = delete_global_forwarding_rule(service, project, consumer_name)
                            wait_for_global_operation(service, project, operation['name'])
                            response = delete_global_address_reservation(service, project, name)
                            # TODO: Need if success then log success message (for each case below)
                            __log.warning("OCEAN deleted IP address {} and "
                                          "attached resource {} from {}".format(address, consumer_name, project))
                            return response
                        except Exception as e:
                            __log.error(e)
                    else:
                        try:
                            __log.info("OCEAN deleting resource {} from {}.".format(consumer_name, project))
                            operation = delete_regional_forwarding_rule(service, project, zone, consumer_name)
                            wait_for_regional_operation(service, project, zone, operation['name'])
                            response = delete_address_reservation(service, project, region, item['name'])
                            __log.warning("OCEAN deleted IP address {} and attached resource {} from {}"
                                          .format(address, consumer_name, project))
                            return response
                        except Exception as e:
                            __log.error(e)

                # TODO: Add functionality for instance groups.
                elif status == "IN_USE" and consumer_type == "instances":
                    try:
                        __log.info("OCEAN deleting resource {} from {}.".format(consumer_name, project))
                        operation = delete_compute_instance(service, project, zone, consumer_name)
                        wait_for_zonal_operation(service, project, zone, operation['name'])
                        response = delete_address_reservation(service, project, region, item['name'])
                        __log.warning("OCEAN deleted IP address {} and attached resource {} from {}"
                                      .format(address, consumer_name, project))
                        return response
                    except Exception as e:
                        __log.error(e)

                elif status == "IN_USE" and consumer_type == "routers":
                    try:
                        __log.info("OCEAN deleting resource {} from {}.".format(consumer_name, project))
                        operation = delete_cloud_router(service, project, zone, consumer_name)
                        wait_for_regional_operation(service, project, zone, operation['name'])
                        response = delete_address_reservation(service, project, region, item['name'])
                        __log.warning("OCEAN deleted IP address {} and attached resource {} from {}"
                                      .format(address, consumer_name, project))
                        return response
                    except Exception as e:
                        __log.error(e)

                else:
                    __log.error(
                        "OCEAN: The IP address {} is in use on {} which is not supported.".format(address, zone))
                return response


# TODO: Each delete should be carried out in a try / except with logging.
def delete_address_reservation(service, project, region, address):
    return service.addresses().delete(
        project=project,
        region=region,
        address=address).execute()


def delete_global_address_reservation(service, project, address):
    return service.globalAddresses().delete(
        project=project,
        address=address).execute()


def delete_cloud_router(service, project, region, router):
    return service.routers().delete(
        project=project,
        region=region,
        router=router).execute()


def delete_compute_instance(service, project, zone, name):
    return service.instances().delete(
        project=project,
        zone=zone,
        instance=name).execute()


def delete_global_forwarding_rule(service, project, name):
    return service.globalForwardingRules().delete(
        project=project,
        forwardingRule=name).execute()


def delete_regional_forwarding_rule(service, project, zone, name):
    return service.forwardingRules().delete(
        project=project,
        zone=zone,
        forwardingRule=name).execute()


def wait_for_zonal_operation(service, project, zone, operation):
    __log.info('OCEAN waiting for zonal operation to finish...')
    while True:
        result = service.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation).execute()

        if result['status'] == 'DONE':
            __log.info("done.")
            if 'error' in result:
                __log.error(result['error'])
                raise Exception(result['error'])
            return result

        time.sleep(1)


def wait_for_regional_operation(service, project, region, operation):
    __log.info('OCEAN waiting for regional operation to finish...')
    while True:
        result = service.regionOperations().get(
            project=project,
            region=region,
            operation=operation).execute()

        if result['status'] == 'DONE':
            __log.info("done.")
            if 'error' in result:
                __log.error(result['error'])
                raise Exception(result['error'])
            return result

        time.sleep(1)


def wait_for_global_operation(service, project, operation):
    __log.info('OCEAN waiting for global operation to finish...')
    while True:
        result = service.globalOperations().get(
            project=project,
            operation=operation).execute()

        if result['status'] == 'DONE':
            __log.info("done.")
            if 'error' in result:
                __log.error(result['error'])
                raise Exception(result['error'])
            return result

        time.sleep(1)


def main():
    service = discovery.build('compute', 'v1', cache_discovery=False, credentials=None)

    __log.info("Starting OCEAN IP Enforcer...")

    if __FUNCTION_PROJECT_ID == 'hsbc-6320774-enforcer-test':
        projects = [ "hsbc-6320774-enforcer-test" ]
    elif __FUNCTION_PROJECT_ID == 'hsbc-6320774-enforcer-dev':
        folder_id = "464555476602"
        projects = project_ids_list(folder_id)
    elif __FUNCTION_PROJECT_ID == 'hsbc-6320774-enforcer-prod':
        folder_id = "962521782257"
        projects = project_ids_list(folder_id)
    else:
        __log.error(__FUNCTION_PROJECT_ID + ' is not a valid OCEAN project')
        raise ValueError(__FUNCTION_PROJECT_ID + ' is not a valid OCEAN project')

    for project in projects:
        addresses = get_addresses(service, project)
        if addresses:
            delete_addresses(service, project, addresses)
        else:
            __log.info("No external addresses found in {}.".format(project))

    __log.info("OCEAN IP Enforcer SUCCESS")


if __name__ == '__main__':
    main()
