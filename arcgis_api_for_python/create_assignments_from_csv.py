# -*- coding: UTF-8 -*-
"""
   Copyright 2017 Esri

   Licensed under the Apache License, Version 2.0 (the "License");

   you may not use this file except in compliance with the License.

   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software

   distributed under the License is distributed on an "AS IS" BASIS,

   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

   See the License for the specific language governing permissions and

   limitations under the License.​

   This sample creates assignments from CSV files
"""

import argparse
import csv
import datetime
import logging
import logging.handlers
import os
import traceback
import sys
import arcgis
import arrow
import dateutil


def initialize_logging(log_file):
    """
    Setup logging
    :param log_file: (string) The file to log to
    :return: (Logger) a logging instance
    """
    # initialize logging
    formatter = logging.Formatter("[%(asctime)s] [%(filename)30s:%(lineno)4s - %(funcName)30s()]\
             [%(threadName)5s] [%(name)10.10s] [%(levelname)8s] %(message)s")
    # Grab the root logger
    logger = logging.getLogger()
    # Set the root logger logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger.setLevel(logging.DEBUG)
    # Create a handler to print to the console
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    sh.setLevel(logging.INFO)
    # Create a handler to log to the specified file
    rh = logging.handlers.RotatingFileHandler(log_file, mode='a', maxBytes=10485760)
    rh.setFormatter(formatter)
    rh.setLevel(logging.DEBUG)
    # Add the handlers to the root logger
    logger.addHandler(sh)
    logger.addHandler(rh)
    return logger


def get_assignments_from_csv(csv_file, xField, yField, assignmentTypeField, locationField, dispatcherIdField=None,
                             descriptionField=None, priorityField=None, workOrderIdField=None, dueDateField=None,
                             dateFormat="%m/%d/%Y %H:%M:%S", wkid=102100, attachmentFileField=None, workerField=None, timezone="UTC"):
    """
    Read the assignments from csv
    :param csv_file: (string) The csv file to read
    :param xField: The name of field containing the x geometry
    :param yField: The name of the field containing y geometry
    :param assignmentTypeField: The name of the field containing the assignmentType
    :param locationField: The name of the field containing the location
    :param dispatcherIdField: The name of the field containing the dispatcherId
    :param descriptionField: The name of the field containing the description
    :param priorityField: The name of the field containing the priority
    :param workOrderIdField: The name of the filed containing the workOrderId
    :param dueDateField: The name of the field containing the dueDate
    :param dateFormat: The format that the dueDate is in (defaults to %m/%d/%Y)
    :param wkid: The wkid that the x,y values use (defaults to 102100 which matches assignments FS)
    :param attachmentFileField: The attachment file field to use
    :param workerField: The name of the field containing the worker username
    :param timezone: The timezone the assignments are in
    :return: List<dict> A list of dictionaries, which contain a Feature
    """
    # Parse CSV
    logger = logging.getLogger()
    csvFile = os.path.abspath(csv_file)
    logger.info("Reading CSV file: {}...".format(csvFile))
    assignments_in_csv = []
    with open(csvFile, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            assignments_in_csv.append(row)
    assignments_to_add = []
    for assignment in assignments_in_csv:
        # Create the geometry
        geometry = dict(x=float(assignment[xField]),
                        y=float(assignment[yField]),
                        spatialReference=dict(
                            wkid=int(wkid)))
        # Create the attributes
        attributes = dict(assignmentType=int(assignment[assignmentTypeField]),
                          location=assignment[locationField],
                          status=0,
                          assignmentRead=None)
        # Add optional attributes
        if args.dispatcherIdField: attributes["dispatcherId"] = int(assignment[dispatcherIdField])
        if args.descriptionField: attributes["description"] = assignment[descriptionField]
        if args.priorityField: attributes["priority"] = int(assignment[priorityField])
        if args.workOrderIdField: attributes["workOrderId"] = assignment[workOrderIdField]
        if args.dueDateField:
            d = arrow.Arrow.strptime(assignment[dueDateField], dateFormat).replace(tzinfo=dateutil.tz.gettz(timezone))
            if d.datetime.second == 0 and d.datetime.hour == 0 and d.datetime.minute == 0:
                d = d.replace(hour=23, minute=59, second=59)
            attributes["dueDate"] = d.to('utc').strftime("%m/%d/%Y %H:%M:%S")
        new_assignment = arcgis.features.Feature(geometry=geometry, attributes=attributes)
        # Need this extra dictionary so we can store the attachment file with the feature
        assignment_dict = (dict(assignment=new_assignment))
        if workerField:
            assignment_dict["workerUsername"] = assignment[workerField]
        if args.attachmentFileField:
            assignment_dict["attachmentFile"] = assignment[attachmentFileField]
        assignments_to_add.append(assignment_dict)
    return assignments_to_add


def validate_assignments(assignment_fl, dispatcher_fl, worker_fl, assignments_to_add):
    """
    Checks the assignments against the dispatcher ids and against domains
    :param assignment_fl: (FeatureLayer) The feature layer containing the assignments
    :param dispatcher_fl: (FeatureLayer) The feature layer containing the dispatchers
    :param worker_fl: (FeatureLayer) The feature layer containing the dispatchers
    :param assignments_to_add: List(dict)
    :return:
    """

    # Validate Assignments
    statuses = []
    priorities = []
    assignmentTypes = []
    dispatcherIds = []
    workerIds = []

    # Get the dispatcherIds
    for dispatcher in dispatcher_fl.query().features:
        dispatcherIds.append(dispatcher.attributes["OBJECTID"])

    # Get the workerIds
    for worker in worker_fl.query().features:
        workerIds.append(worker.attributes["OBJECTID"])

    # Get the codes of the domains
    for field in assignment_fl.properties.fields:
        if field.name == "status":
            statuses = [cv.code for cv in field.domain.codedValues]
        if field.name == "priority":
            priorities = [cv.code for cv in field.domain.codedValues]
        if field.name == "assignmentType":
            assignmentTypes = [cv.code for cv in field.domain.codedValues]

    logging.getLogger().info("Validating assignments...")
    # check the values against the fields that have domains
    for assignment in assignments_to_add:
        if assignment["assignment"].attributes["status"] not in statuses:
            logging.getLogger().critical("Invalid Status for: {}".format(assignment["assignment"]))
            return False
        if "priority" in assignment["assignment"].attributes and assignment["assignment"].attributes[
            "priority"] not in priorities:
            logging.getLogger().critical("Invalid Priority for: {}".format(assignment["assignment"]))
            return False
        if assignment["assignment"].attributes["assignmentType"] not in assignmentTypes:
            logging.getLogger().critical("Invalid Assignment Type for: {}".format(assignment["assignment"]))
            return False
        if assignment["assignment"].attributes["dispatcherId"] not in dispatcherIds:
            logging.getLogger().critical("Invalid Dispatcher Id for: {}".format(assignment["assignment"]))
            return False
        if "workerUsername" in assignment and assignment["workerUsername"] and assignment["assignment"].attributes["workerId"] not in workerIds:
            logging.getLogger().critical("Invalid Worker Id for: {}".format(assignment))
            return False
        if "attachmentFile" in assignment and assignment["attachmentFile"]:
            if not os.path.isfile(os.path.abspath(assignment["attachmentFile"])):
                logging.getLogger().critical("Attachment file not found: {}".format(assignment["attachmentFile"]))
                return False
    return True


def main(args):
    # initialize logging
    logger = initialize_logging(args.logFile)
    # Create the GIS
    logger.info("Authenticating...")
    # First step is to get authenticate and get a valid token
    gis = arcgis.gis.GIS(args.org_url, username=args.username, password=args.password)
    # Create a content manager object
    content_manager = arcgis.gis.ContentManager(gis)
    # Get the project and data
    workforce_project = content_manager.get(args.projectId)
    workforce_project_data = workforce_project.get_data()
    assignment_fl = arcgis.features.FeatureLayer(workforce_project_data["assignments"]["url"], gis)
    dispatcher_fl = arcgis.features.FeatureLayer(workforce_project_data["dispatchers"]["url"], gis)
    worker_fl = arcgis.features.FeatureLayer(workforce_project_data["workers"]["url"], gis)
    assignments = get_assignments_from_csv(args.csvFile, args.xField, args.yField, args.assignmentTypeField,
                                           args.locationField, args.dispatcherIdField, args.descriptionField,
                                           args.priorityField, args.workOrderIdField, args.dueDateField,
                                           args.dateFormat, args.wkid, args.attachmentFileField, args.workerField, args.timezone)

    # Set the dispatcher id
    id = None
    dispatchers = dispatcher_fl.query(where="userId='{}'".format(args.username))
    if dispatchers.features:
        id = dispatchers.features[0].attributes["OBJECTID"]
    else:
        logger.critical("{} is not a dispatcher".format(args.username))
        return

    # Set the dispatcherId in the assignment json
    for assignment in [x["assignment"] for x in assignments]:
        if "dispatcherId" not in assignment.attributes:
            assignment.attributes["dispatcherId"] = id

    # set worker ids
    for assignment in assignments:
        if "workerUsername" in assignment and assignment["workerUsername"]:
            workers = worker_fl.query(where="userId='{}'".format(assignment["workerUsername"]))
            if workers.features:
                assignment["assignment"].attributes["workerId"] = workers.features[0].attributes["OBJECTID"]
                assignment["assignment"].attributes["status"] = 1 # assigned
                assignment["assignment"].attributes["assignedDate"] = arrow.now().to('utc').strftime(
                    "%m/%d/%Y %H:%M:%S")
            else:
                logger.critical("{} is not a worker".format(assignment["workerUsername"]))
                return

    logger.info("Validating Assignments...")
    validate_assignments(assignment_fl, dispatcher_fl, worker_fl, assignments)

    # Add the assignments
    logger.info("Adding Assignments...")
    response = assignment_fl.edit_features(
        adds=arcgis.features.FeatureSet([x["assignment"] for x in assignments]))
    logger.info(response)
    # Assign the returned object ids to the assignment dictionary object
    for i in range(len(response["addResults"])):
        assignments[i]["assignment"].attributes["OBJECTID"] = response["addResults"][i]["objectId"]

    # Add the attachments
    logger.info("Adding Any Attachments...")
    if len(assignments) > 0 and "attachmentFile" in assignments[0]:
        attachment_manager = arcgis.features.managers.AttachmentManager(assignment_fl)
        for assignment in assignments:
            if assignment["attachmentFile"] and assignment["attachmentFile"] != "":
                response = attachment_manager.add(assignment["assignment"].attributes["OBJECTID"],
                                       os.path.abspath(assignment["attachmentFile"]))
                logger.info(response)
    logger.info("Completed")


if __name__ == "__main__":
    # Get all of the commandline arguments
    parser = argparse.ArgumentParser("Add Assignments to Workforce Project")
    parser.add_argument('-u', dest='username', help="The username to authenticate with", required=True)
    parser.add_argument('-p', dest='password', help="The password to authenticate with", required=True)
    parser.add_argument('-url', dest='org_url', help="The url of the org/portal to use", required=True)
    # Parameters for workforce
    parser.add_argument('-pid', dest='projectId', help="The id of the project to add assignments to", required=True)
    parser.add_argument('-xField', dest='xField', help="The field that contains the x SHAPE information", required=True)
    parser.add_argument('-yField', dest='yField', help="The field that contains the y SHAPE information", required=True)
    parser.add_argument('-assignmentTypeField', dest='assignmentTypeField',
                        help="The field that contains the assignmentType", required=True)
    parser.add_argument('-locationField', dest='locationField',
                        help="The field that contains the location", required=True)
    parser.add_argument('-dispatcherIdField', dest='dispatcherIdField',
                        help="The field that contains the dispatcherId")
    parser.add_argument('-descriptionField', dest='descriptionField', help="The field that contains the description")
    parser.add_argument('-priorityField', dest='priorityField', help="The field that contains the priority")
    parser.add_argument('-workOrderIdField', dest='workOrderIdField', help="The field that contains the workOrderId")
    parser.add_argument('-dueDateField', dest='dueDateField', help="The field that contains the dispatcherId")
    parser.add_argument('-workerField', dest='workerField', help="The field that contains the workers username")
    parser.add_argument('-attachmentFileField', dest='attachmentFileField',
                        help="The field that contains the file path to the attachment to upload")
    parser.add_argument('-dateFormat', dest='dateFormat', default="%m/%d/%Y %H:%M:%S",
                        help="The format to use for the date (eg. '%m/%d/%Y %H:%M:%S')")
    parser.add_argument('-timezone', dest='timezone', default="UTC", help="The timezone for the assignments")
    parser.add_argument('-csvFile', dest='csvFile', help="The path/name of the csv file to read")
    parser.add_argument('-wkid', dest='wkid', help='The wkid that the x,y values are use', type=int, default=4326)
    parser.add_argument('-logFile', dest='logFile', help='The log file to use', required=True)
    args = parser.parse_args()
    try:
        main(args)
    except Exception as e:
        logging.getLogger().critical("Exception detected, script exiting")
        logging.getLogger().critical(e)
        logging.getLogger().critical(traceback.format_exc().replace("\n", " | "))
