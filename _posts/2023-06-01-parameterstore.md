---
layout: post
title:  "Back-up your AWS Parameter Store"
date: 2023-06-01 00:00:00 -0000
categories:
---

# Overview
Let's build a fun utility that may just save your butt one day!  We can run a daily backup of our Parameter Store that is generated via a Lambda, GPG encrypted, and stored in S3.  The result will be stored as a JSON blob making it fairly easy to parse out exactly what you need.  This will come in handy for creating a diff to see what changed from one day to the next or doing a full restore.  The output contains the metadata for each parameter store entry allowing a restore to be associated with KMS keys or an output with unencrypted values.

The output looks like:

    {
    "Name": "/blah/blah/blah", 
        "Type": "SecureString", 
        "KeyId": "alias/blah", 
        "LastModifiedDate": "2024-03-18 13:13:21.836000-07:00", 
        "LastModifiedUser": "arn:aws:iam::043833176966:user/blah", 
        "Version": 2, 
        "Tier": "Standard", 
        "Policies": [], 
        "DataType": "text", 
        "Value": "1234567890"
    }

# Write it
Or borrow it, I don't mind.  This is meant to run as a Lambda, but runs just fine on an EC2 instance for testing.  Download or clone from here:

[parameterstore-backup.py](https://github.com/llazon/llazon.github.io/blob/main/projects/parameterstore/parameterstore-backup.py)

# Build it
Build the script above for Lambda.  Zip it up and copy it to S3!

[build-parameterstore-backup.sh](https://github.com/llazon/llazon.github.io/blob/main/projects/parameterstore/build-parameterstore-backup.sh)

# Configure it
Use Terraform to configure your Lambda

    resource "aws_lambda_function" "parameterstore-backup" {
        function_name = "parameterstore-backup"

        role = aws_iam_role.parameterstore-backup.arn
        s3_bucket = ""
        s3_key = "parameterstore-backup.zip"
        handler = "parameterstore-backup.lambda_handler"
        runtime = "python3.9"
        architectures = ["arm64"]
        timeout = "900"
        memory_size = "1536"

        vpc_config {
            subnet_ids = [
                aws_subnet.id,
                aws_subnet.id,
                aws_subnet.id,
                aws_subnet.id,
            ]
            security_group_ids = [
                aws_security_group.lambda.id,
            ]
        }

        tags = {
            Name = "parameterstore-backup"
            env = "production"
            tier = "cool tools"
            provisioned = "terraform"
        }

        environment {
            variables = {
                PATH = "$PATH:/opt/gnupg/bin"
            }
        }

        layers = [
            "arn:aws:lambda:us-west-1:123456789:layer:gnupg-arm64",
        ]

    }

# Run it
Use Terraform to configure an Event that runs daily.

    resource "aws_cloudwatch_event_rule" "parameterstore-backup" {
        name = "parameterstore-backup"
        description = "Trigger runs the lambda on a fixed schedule"
        schedule_expression = "rate(1 day)"
    }

    resource "aws_cloudwatch_event_target" "parameterstore-backup" {
        target_id = "parameterstore-backup"
        rule = aws_cloudwatch_event_rule.parameterstore-backup.name
        arn = aws_lambda_function.parameterstore-backup.arn
    }

    resource "aws_lambda_permission" "arameterstore-backup" {
        action = "lambda:InvokeFunction"
        function_name = aws_lambda_function.parameterstore-backup.function_name
        principal = "events.amazonaws.com"
        source_arn = aws_cloudwatch_event_rule.parameterstore-backup.arn
    }

# Restore it

## Make sure you have all the pieces
- Lambda: ops-parameterstore-backup
- S3: s3://blah/parameterstore/backup/parameterstore-backup-DATE.gpg
- GPG Public Key: blah.gpg
- GPG Private Key: blah.gpg.secret
- GPG Passphrase: keep it safe!

## Setup your environment
    mkdir -p ~/parameterstore
    cd ~/parameterstore
    aws s3 cp s3://blah/parameterstore/backup/parameterstore-backup-DATE.gpg .

Copy Private Key: blah.gpg.secret to ~/parameterstore

## Decrypt
    export HOME=~/parameterstore
    gpg --allow-secret-key-import --import blah.gpg.secret
    gpg --output parameterstore-backup.json --decrypt --recipient blah parameterstore-backup-DATE.gpg


