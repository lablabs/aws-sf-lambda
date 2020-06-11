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
        instance_id = event['detail']['EC2InstanceId']
        lifecycle_hook_name = event['detail']['LifecycleHookName']
        auto_scaling_group_name = event['detail']['AutoScalingGroupName']

        try:
            subnet_id = get_subnet_id(instance_id)
            free_enis = get_free_enis(subnet_id)
            eni_id = get_random_eni_id(free_enis)
            ebs_volume = get_ebs_volume(eni_id)

            attach_eni(eni_id, instance_id)
            attach_ebs(ebs_volume["VolumeId"], instance_id)

            complete_lifecycle_action_success(lifecycle_hook_name, auto_scaling_group_name, instance_id)

        except (ResourceNotFound, ResourceAttachError) as e:
            log(e.message)
            complete_lifecycle_action_failure(lifecycle_hook_name, auto_scaling_group_name, instance_id)


def get_ebs_volume(eni_id):
    """
    Get the ebs volumes that is bound to the right ENI.
    """
    ebs_volume = None
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
        ebs_volume = result['Volumes'][0]
        log("Free EBS volume: {}".format(ebs_volume["VolumeId"]))

    except ClientError as e:
        log("Error describing the instance {}: {}".format(eni_id, e.response['Error']))

    if not ebs_volume or len(ebs_volume) == 0:
        raise ResourceNotFound(
            "EBS",
            "No EBS for ENI ID '{}' has been found".format(eni_id)
        )

    return ebs_volume


def get_free_enis(internal_subnet):
    """
    Get all free NetworkInterfaces in the internal subnet with the tag.
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
                "Values": [internal_subnet]
            },
            {
                "Name": "status",
                "Values": ["available"]
            }
        ])
        free_enis = result['NetworkInterfaces']
        log("free_enis: {}".format([eni["NetworkInterfaceId"] for eni in free_enis]))

    except ClientError as e:
        log("Error describing the instance {}: {}".format(internal_subnet, e.response['Error']))

    if not free_enis or len(free_enis) == 0:
        raise ResourceNotFound(
            "ENI",
            "No ENI for subnet ID '{}' has been found".format(internal_subnet)
        )

    return free_enis


def get_random_eni_id(enis):
    eni_to_attach = random.choice(enis)
    return eni_to_attach["NetworkInterfaceId"]


def get_subnet_id(instance_id):
    """
    Get id of subnet where the instance is running.
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
    Attach eni to instance.
    """
    attachment = None

    log("Attaching '{}' eni to '{}' instance".format(eni_id, instance_id))
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
    Attach eni to instance.
    """
    attachment_state = None
    log("Attaching '{}' ebs to '{}' instance".format(ebs_id, instance_id))
    if ebs_id and instance_id:
        try:
            attachment = ec2_client.attach_volume(
                VolumeId=ebs_id,
                InstanceId=instance_id,
                Device=STATIC_VOLUME
            )
            attachment_state = attachment['State']
        except ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']))

    if not attachment_state:
        raise ResourceAttachError("EBS")

    return attachment_state


def complete_lifecycle_action_success(hook_name, group_name, instance_id):
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hook_name,
            AutoScalingGroupName=group_name,
            InstanceId=instance_id,
            LifecycleActionResult='CONTINUE'
        )
        log("Lifecycle hook CONTINUEd for: {}".format(instance_id))
    except ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(instance_id, e.response['Error']))
        log('{"Error": "1"}')


def complete_lifecycle_action_failure(hook_name, group_name, instance_id):
    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hook_name,
            AutoScalingGroupName=group_name,
            InstanceId=instance_id,
            LifecycleActionResult='ABANDON'
        )
        log("Lifecycle hook ABANDONed for: {}".format(instance_id))
    except ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(instance_id, e.response['Error']))
        log('{"Error": "1"}')


def log(error):
    print('{}Z {}'.format(datetime.utcnow().isoformat(), error))


class ResourceNotFound(Exception):
    """Raised when resource is not found"""
    def __init__(self, resource_type, message):
        self.resource_type = resource_type
        self.message = message
        super().__init__(self.message)


class ResourceAttachError(Exception):
    """Raised when resource attachment fails"""
    def __init__(self, resource_type):
        self.resource_type = resource_type
        self.message = "Resource {} has not been attached successfully".format(resource_type)
        super().__init__(self.message)
