import os
import random
from datetime import datetime

# boto3 and botocore are provided by AWS Lambda runtime
# https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html
import boto3
from botocore.exceptions import ClientError

ec2_client = boto3.client('ec2')
asg_client = boto3.client('autoscaling')

TAG_STACK_NAME = os.environ['TAG_STACK_NAME']
TAG_STACK_VALUE = os.environ['TAG_STACK_VALUE']
TAG_INVENTORY_NAME = os.environ['TAG_INVENTORY_NAME']

STATIC_VOLUME = '/dev/xvdz'


def handle(event, context):  # noqa
    if event["detail-type"] == "EC2 Instance-launch Lifecycle Action":
        try:
            instance_id = get_instance_id(event)

            subnet_id = get_subnet_id(instance_id)
            free_enis = get_free_enis(subnet_id)
            eni_id = get_random_eni_id(free_enis)
            ebs_volume_id = get_ebs_volume_id(eni_id)

            attach_eni(eni_id, instance_id)
            attach_ebs(ebs_volume_id, instance_id)

            complete_lifecycle_action_success(event)

        except (EventDataError, ResourceNotFound, ResourceAttachError) as e:
            log("{}: {}".format(e.description, e.message))
            complete_lifecycle_action_failure(event)


def get_ebs_volume_id(eni_id):
    """
    Get the EBS volume ID that is bound to the right ENI.
    """
    ebs_volume_id = None
    try:
        result = ec2_client.describe_volumes(Filters=[
            {
                "Name": "tag:{}".format(TAG_INVENTORY_NAME),
                "Values": [eni_id]
            },
            {
                "Name": "status",
                "Values": ["available"]
            }
        ])
        ebs_volume_id = result['Volumes'][0]["VolumeId"]
        log("Free EBS volume ID: {}".format(ebs_volume_id))

    except ClientError as e:
        log("Error describing the instance {}: {}".format(eni_id, e.response['Error']))

    if not ebs_volume_id or len(ebs_volume_id) == 0:
        raise ResourceNotFound(
            "EBS",
            "No EBS volume for ENI ID '{}' has been found".format(eni_id)
        )

    return ebs_volume_id


def get_free_enis(subnet_id):
    """
    Get all free NetworkInterfaces in the subnet with the tag.
    """
    free_enis = None
    try:
        result = ec2_client.describe_network_interfaces(Filters=[
            {
                "Name": "tag:{}".format(TAG_STACK_NAME),
                "Values": [TAG_STACK_VALUE]
            },
            {
                "Name": "subnet-id",
                "Values": [subnet_id]
            },
            {
                "Name": "status",
                "Values": ["available"]
            }
        ])
        free_enis = result['NetworkInterfaces']
        log("Free ENI IDs: {}".format([eni["NetworkInterfaceId"] for eni in free_enis]))

    except ClientError as e:
        log("Error describing the instance {}: {}".format(subnet_id, e.response['Error']))

    if not free_enis or len(free_enis) == 0:
        raise ResourceNotFound(
            "ENI",
            "No ENI for subnet ID '{}' has been found".format(subnet_id)
        )

    return free_enis


def get_random_eni_id(enis):
    eni_to_attach = random.choice(enis)
    return eni_to_attach["NetworkInterfaceId"]


def get_subnet_id(instance_id):
    """
    Get ID of subnet where the instance is running.
    """
    vpc_subnet_id = None
    try:
        result = ec2_client.describe_instances(InstanceIds=[instance_id])
        vpc_subnet_id = result['Reservations'][0]['Instances'][0]['SubnetId']

    except ClientError as e:
        log("Error describing the instance {}: {}".format(instance_id, e.response['Error']))

    if not vpc_subnet_id:
        raise ResourceNotFound(
            "subnet",
            "No subnet for instance ID '{}' has been found".format(instance_id)
        )

    return vpc_subnet_id


def attach_eni(eni_id, instance_id):
    """
    Attach ENI to the instance.
    """
    attachment = None

    log("Attaching '{}' ENI to '{}' instance".format(eni_id, instance_id))
    if eni_id and instance_id:
        try:
            attach_interface = ec2_client.attach_network_interface(
                NetworkInterfaceId=eni_id,
                InstanceId=instance_id,
                DeviceIndex=1
            )
            attachment = attach_interface['AttachmentId']
        except ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']))

    if not attachment:
        raise ResourceAttachError("ENI")

    return attachment


def attach_ebs(ebs_id, instance_id):
    """
    Attach EBS volume to the instance.
    """
    attachment_state = None
    log("Attaching '{}' EBS volume to '{}' instance".format(ebs_id, instance_id))
    if ebs_id and instance_id:
        try:
            attachment = ec2_client.attach_volume(
                VolumeId=ebs_id,
                InstanceId=instance_id,
                Device=STATIC_VOLUME
            )
            attachment_state = attachment['State']
        except ClientError as e:
            log("Error attaching EBS volume: {}".format(e.response['Error']))

    if not attachment_state:
        raise ResourceAttachError("EBS")

    return attachment_state


def complete_lifecycle_action_success(event):
    return complete_lifecycle_action(event, lifecycle_action_result='CONTINUE')


def complete_lifecycle_action_failure(event):
    return complete_lifecycle_action(event, lifecycle_action_result='ABANDON')


def complete_lifecycle_action(event, lifecycle_action_result):
    assert lifecycle_action_result in ['CONTINUE', 'ABANDON']
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=get_lifecycle_hook_name(event),
            AutoScalingGroupName=get_auto_scaling_group_name(event),
            InstanceId=get_instance_id(event),
            LifecycleActionResult=lifecycle_action_result,
        )
        log("Lifecycle hook {}ed for: {}".format(
            lifecycle_action_result,
            get_instance_id(event)
        ))
    except ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(
            get_instance_id(event),
            e.response['Error']
        ))
        log('{"Error": "1"}')


def get_instance_id(event):
    try:
        instance_id = event['detail']['EC2InstanceId']
        log("event['detail']['EC2InstanceId]' = {}".format(instance_id))
        return instance_id
    except KeyError:
        log("Key error: event={}".format(event))
        raise EventDataError("Cannot read EC2 instance ID form event detail")


def get_lifecycle_hook_name(event):
    return event['detail']['LifecycleHookName']


def get_auto_scaling_group_name(event):
    return event['detail']['AutoScalingGroupName']


def log(error):
    print('{}Z {}'.format(datetime.utcnow().isoformat(), error))


class EventDataError(Exception):
    """Raised when event data are not formatted as expected"""
    description = "Event data error"

    def __init__(self, message):
        self.message = message


class ResourceNotFound(Exception):
    """Raised when resource is not found"""
    description = "Resource not found error"

    def __init__(self, resource_type, message):
        self.resource_type = resource_type
        self.message = message
        super().__init__(self.message)


class ResourceAttachError(Exception):
    """Raised when resource attachment fails"""
    description = "Resource attachment error"

    def __init__(self, resource_type):
        self.resource_type = resource_type
        self.message = "Resource {} has not been attached successfully".format(resource_type)
        super().__init__(self.message)
