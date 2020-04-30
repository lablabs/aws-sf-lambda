import boto3
import botocore
import random
import json
import os
from datetime import datetime

ec2_client = boto3.client('ec2')
asg_client = boto3.client('autoscaling')

TAG_STACK_NAME = os.environ['TAG_STACK_NAME']
TAG_STACK_VALUE = os.environ['TAG_STACK_VALUE']
TAG_INVENTORY_NAME = os.environ['TAG_INVENTORY_NAME']

STATIC_VOLUME = '/dev/xvdz'

def handle(event, context):
    if event["detail-type"] == "EC2 Instance-launch Lifecycle Action":
        instance_id = event['detail']['EC2InstanceId']
        LifecycleHookName = event['detail']['LifecycleHookName']
        AutoScalingGroupName = event['detail']['AutoScalingGroupName']

        subnet_id = get_subnet_id(instance_id)
        log("subnet_id: {} ".format(subnet_id))

        # eni
        free_enis = get_free_enis(subnet_id)
        if len(free_enis) == 0:
            log("No free ENIs found")
            complete_lifecycle_action_failure(LifecycleHookName, AutoScalingGroupName, instance_id)
        log("free_enis: {} ".format([eni["NetworkInterfaceId"] for eni in free_enis]))
        eni_to_attach = random.choice(free_enis)
        eni_id = eni_to_attach["NetworkInterfaceId"]
        eni_attachment = attach_eni(eni_id, instance_id)
        if not eni_attachment:
            complete_lifecycle_action_failure(LifecycleHookName, AutoScalingGroupName, instance_id)

        # ebs
        ebs_volume = get_ebs_volume(eni_id)
        if len(ebs_volume) == 0:
            log("TODO: FAIL...Volume not found")
        log("Free EBS volume: {}".format(ebs_volume["VolumeId"]))
        ebs_attachment = attach_ebs(ebs_volume["VolumeId"], instance_id)
        if not ebs_attachment:
            complete_lifecycle_action_failure(LifecycleHookName, AutoScalingGroupName, instance_id)
        complete_lifecycle_action_success(LifecycleHookName, AutoScalingGroupName, instance_id)


def get_ebs_volume(eni_id):
    """
    Get the ebs volumes that is bound to the right ENI.
    """
    ebs_volume = None
    try:
        result = ec2_client.describe_volumes( Filters=[
            {
                "Name": "tag:{}".format(TAG_INVENTORY_NAME),
                "Values": [eni_id]
            },
            {
                "Name": "status",
                "Values": ["available"]
            }
        ])
        ebs_volume = result['Volumes'][0]

    except botocore.exceptions.ClientError as e:
        log("Error describing the instance {}: {}".format(internal_subnet, e.response['Error']))

    return ebs_volume

def get_free_enis(internal_subnet):
    """
    Get all free NetworkInterfaces in the internal subnet with the tag.
    """
    free_enis = None
    try:
        result = ec2_client.describe_network_interfaces( Filters=[
            {
                "Name": "tag:{}".format(TAG_STACK_NAME),
                "Values": [TAG_STACK_VALUE]
            },
            {
                "Name": "subnet-id",
                "Values": [internal_subnet]
            },
            {
                "Name": "status",
                "Values": ["available"]
            }
        ])
        free_enis = result['NetworkInterfaces']

    except botocore.exceptions.ClientError as e:
        log("Error describing the instance {}: {}".format(internal_subnet, e.response['Error']))

    return free_enis

def get_subnet_id(instance_id):
    """
    Get id of subnet where the instance is running.
    """
    vpc_subnet_id = None
    try:
        result = ec2_client.describe_instances(InstanceIds=[instance_id])
        vpc_subnet_id = result['Reservations'][0]['Instances'][0]['SubnetId']

    except botocore.exceptions.ClientError as e:
        log("Error describing the instance {}: {}".format(instance_id, e.response['Error']))

    return vpc_subnet_id

def attach_eni(eni_id, instance_id):
    """
    Attach eni to instance.
    """
    attachment = None

    log("Attaching '{}' eni to '{}' instance".format(eni_id,instance_id))
    if eni_id and instance_id:
        try:
            attach_interface = ec2_client.attach_network_interface(
                NetworkInterfaceId=eni_id,
                InstanceId=instance_id,
                DeviceIndex=1
            )
            attachment = attach_interface['AttachmentId']
        except botocore.exceptions.ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']))

    return attachment

def attach_ebs(ebs_id, instance_id):
    """
    Attach eni to instance.
    """
    attachment_state = None
    log("Attaching '{}' ebs to '{}' instance".format(ebs_id,instance_id))
    if ebs_id and instance_id:
        try:
            attach_ebs = ec2_client.attach_volume(
                VolumeId=ebs_id,
                InstanceId=instance_id,
                Device=STATIC_VOLUME
            )
            attachment_state = attach_ebs['State']
        except botocore.exceptions.ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']))

    return attachment_state

def complete_lifecycle_action_success(hookname, groupname, instance_id):
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hookname,
            AutoScalingGroupName=groupname,
            InstanceId=instance_id,
            LifecycleActionResult='CONTINUE'
        )
        log("Lifecycle hook CONTINUEd for: {}".format(instance_id))
    except botocore.exceptions.ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(instance_id, e.response['Error']))
        log('{"Error": "1"}')


def complete_lifecycle_action_failure(hookname, groupname, instance_id):
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hookname,
            AutoScalingGroupName=groupname,
            InstanceId=instance_id,
            LifecycleActionResult='ABANDON'
        )
        log("Lifecycle hook ABANDONed for: {}".format(instance_id))
    except botocore.exceptions.ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(instance_id, e.response['Error']))
        log('{"Error": "1"}')


def log(error):
    print('{}Z {}'.format(datetime.utcnow().isoformat(), error))
