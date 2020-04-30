# aws-sf-lambda

[<img src="ll-logo.png">](https://lablabs.io/)

We help companies build, run, deploy and scale software and infrastructure by embracing the right technologies and principles. Check out our website at https://lablabs.io/

---

## Description

A lambda function which is supposed to be used as a lifecycle hook in AWS ASGs. The function handles the assigment of EBS volumes and ENI interfaces to instances that are managed by the ASG. This comes in hand when the AWS ASGs are used to manage a service deployed on EC2 instances which need to have static IPs and persistent storage.

## Features

- Attachment of static ENIs and EBS volumes to an EC2 instance launched by AWS ASGs

## Prerequisites

- AWS ASGs configured with lifecycle hooks. See [aws-sf-terraform](https://github.com/adys/aws-sf-terraform).

## Contributing and reporting issues

Feel free to create an issue in this repository if you have questions, suggestions or feature requests.

## Usage

push.sh can be used to build and push the zip artifact of the function to an S3 bucket.

## License

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

See [LICENSE](LICENSE) for full details.

    Licensed to the Apache Software Foundation (ASF) under one
    or more contributor license agreements.  See the NOTICE file
    distributed with this work for additional information
    regarding copyright ownership.  The ASF licenses this file
    to you under the Apache License, Version 2.0 (the
    "License"); you may not use this file except in compliance
    with the License.  You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing,
    software distributed under the License is distributed on an
    "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
    KIND, either express or implied.  See the License for the
    specific language governing permissions and limitations
    under the License.
