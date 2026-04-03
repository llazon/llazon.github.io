---
layout: post
title: "CloudTrail Deep Dives for Incident Response"
date: 2025-08-04
categories: aws security incident-response
tags: aws cloudtrail security incident-response athena investigation
---

# CloudTrail Deep Dives for Incident Response

When something goes wrong in your AWS environment — unauthorized access, unexpected resource changes, suspicious API calls — CloudTrail is where you go for answers. It records every API call made in your account, and knowing how to query it effectively is the difference between a 30-minute investigation and a 3-day one.

## CloudTrail Basics (Quick Refresher)

CloudTrail logs every AWS API call with:
- Who made the call (IAM identity, source IP)
- What they did (API action, request parameters)
- When it happened (timestamp)
- Where it happened (region, resource ARN)
- Whether it succeeded or failed

By default, CloudTrail keeps 90 days of management events in Event History. For longer retention and data events (S3 object-level, Lambda invocations), you need a trail that delivers to S3.

## Setting Up for Success

Before an incident happens, make sure you have:

```bash
# Create a trail that logs to S3 with encryption
aws cloudtrail create-trail \
  --name org-trail \
  --s3-bucket-name my-cloudtrail-bucket \
  --is-multi-region-trail \
  --enable-log-file-validation \
  --kms-key-id arn:aws:kms:us-east-1:123456789012:key/my-key-id \
  --is-organization-trail

aws cloudtrail start-logging --name org-trail

# Enable data events for S3 (object-level logging)
aws cloudtrail put-event-selectors \
  --trail-name org-trail \
  --event-selectors '[{
    "ReadWriteType": "All",
    "IncludeManagementEvents": true,
    "DataResources": [{
      "Type": "AWS::S3::Object",
      "Values": ["arn:aws:s3"]
    }]
  }]'
```

## Querying with Athena

For anything beyond simple lookups, Athena is the tool. Create a table over your CloudTrail logs:

```sql
CREATE EXTERNAL TABLE cloudtrail_logs (
    eventVersion STRING,
    userIdentity STRUCT<
        type: STRING,
        principalId: STRING,
        arn: STRING,
        accountId: STRING,
        invokedBy: STRING,
        accessKeyId: STRING,
        userName: STRING,
        sessionContext: STRUCT<
            attributes: STRUCT<
                mfaAuthenticated: STRING,
                creationDate: STRING>,
            sessionIssuer: STRUCT<
                type: STRING,
                principalId: STRING,
                arn: STRING,
                accountId: STRING,
                userName: STRING>>>,
    eventTime STRING,
    eventSource STRING,
    eventName STRING,
    awsRegion STRING,
    sourceIPAddress STRING,
    userAgent STRING,
    errorCode STRING,
    errorMessage STRING,
    requestParameters STRING,
    responseElements STRING,
    additionalEventData STRING,
    requestId STRING,
    eventId STRING,
    resources ARRAY<STRUCT<
        arn: STRING,
        accountId: STRING,
        type: STRING>>,
    eventType STRING,
    recipientAccountId STRING,
    sharedEventId STRING
)
PARTITIONED BY (
    account STRING,
    region STRING,
    year STRING,
    month STRING,
    day STRING
)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
STORED AS INPUTFORMAT 'com.amazon.emr.cloudtrail.CloudTrailInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://my-cloudtrail-bucket/AWSLogs/'
```

## Investigation Playbooks

### Scenario 1: Compromised Access Keys

Someone's access key showed up in a public repo. Find everything they did:

```sql
SELECT
    eventTime,
    eventName,
    eventSource,
    sourceIPAddress,
    awsRegion,
    errorCode,
    requestParameters
FROM cloudtrail_logs
WHERE userIdentity.accessKeyId = 'AKIA1234567890EXAMPLE'
    AND year = '2025' AND month = '08'
ORDER BY eventTime DESC
LIMIT 500;
```

Look for:
- API calls from unexpected IP addresses
- Calls to IAM (creating new users/keys)
- Calls to S3 (data exfiltration)
- Calls to EC2 (launching instances for crypto mining)

### Scenario 2: Unauthorized Resource Changes

A security group was modified and you need to find out who did it:

```sql
SELECT
    eventTime,
    userIdentity.arn AS who,
    eventName,
    sourceIPAddress,
    requestParameters
FROM cloudtrail_logs
WHERE eventSource = 'ec2.amazonaws.com'
    AND eventName IN (
        'AuthorizeSecurityGroupIngress',
        'AuthorizeSecurityGroupEgress',
        'RevokeSecurityGroupIngress',
        'RevokeSecurityGroupEgress',
        'CreateSecurityGroup',
        'DeleteSecurityGroup'
    )
    AND year = '2025' AND month = '08'
ORDER BY eventTime DESC;
```

### Scenario 3: Console Login Investigation

Suspicious console logins from unusual locations:

```sql
SELECT
    eventTime,
    userIdentity.userName,
    sourceIPAddress,
    userIdentity.sessionContext.attributes.mfaAuthenticated,
    responseElements,
    errorCode
FROM cloudtrail_logs
WHERE eventName = 'ConsoleLogin'
    AND year = '2025' AND month = '08'
ORDER BY eventTime DESC;
```

Check for:
- Logins without MFA
- Logins from unexpected IP ranges or countries
- Failed login attempts followed by a success (brute force)

### Scenario 4: Data Exfiltration via S3

Find bulk S3 downloads from a specific principal:

```sql
SELECT
    eventTime,
    userIdentity.arn,
    requestParameters,
    sourceIPAddress,
    resources[0].arn AS bucket_arn
FROM cloudtrail_logs
WHERE eventSource = 's3.amazonaws.com'
    AND eventName = 'GetObject'
    AND userIdentity.arn LIKE '%suspicious-role%'
    AND year = '2025' AND month = '08'
ORDER BY eventTime DESC
LIMIT 1000;
```

### Scenario 5: IAM Privilege Escalation

Detect attempts to escalate privileges:

```sql
SELECT
    eventTime,
    userIdentity.arn AS who,
    eventName,
    requestParameters,
    errorCode
FROM cloudtrail_logs
WHERE eventSource = 'iam.amazonaws.com'
    AND eventName IN (
        'CreateUser',
        'CreateRole',
        'AttachUserPolicy',
        'AttachRolePolicy',
        'PutUserPolicy',
        'PutRolePolicy',
        'CreateAccessKey',
        'CreateLoginProfile',
        'UpdateAssumeRolePolicy',
        'AddUserToGroup'
    )
    AND year = '2025' AND month = '08'
ORDER BY eventTime DESC;
```

## Quick CLI Queries

For fast lookups when you don't want to spin up Athena:

```bash
# Recent API calls by a specific user
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=suspicious-user \
  --start-time "2025-08-01T00:00:00Z" \
  --end-time "2025-08-04T23:59:59Z" \
  --query 'Events[*].[EventTime,EventName,EventSource]' \
  --output table

# Recent events for a specific resource
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=i-0123456789abcdef0 \
  --query 'Events[*].[EventTime,EventName,Username]' \
  --output table

# Failed API calls (access denied)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RunInstances \
  --query 'Events[?contains(CloudTrailEvent, `AccessDenied`)].[EventTime,Username]' \
  --output table
```

## Building a Timeline

During an incident, build a timeline. Here's a query that gives you a chronological view of all actions by a compromised identity:

```sql
SELECT
    eventTime,
    eventSource,
    eventName,
    awsRegion,
    sourceIPAddress,
    errorCode,
    CASE
        WHEN errorCode IS NOT NULL THEN 'FAILED'
        ELSE 'SUCCESS'
    END AS status
FROM cloudtrail_logs
WHERE userIdentity.arn = 'arn:aws:iam::123456789012:user/compromised-user'
    AND year = '2025'
ORDER BY eventTime ASC;
```

Export this to a spreadsheet, add annotations, and you've got your incident timeline for the post-mortem.

## Tips for Effective Investigations

- Always check multiple regions — attackers often operate in regions you don't normally use
- Look at `sourceIPAddress` patterns — a sudden change in IP geolocation is a red flag
- Check `userAgent` strings — unusual agents might indicate automated tools
- Failed API calls are just as important as successful ones — they show what the attacker tried
- Cross-reference with VPC Flow Logs for network-level context
- Save your Athena queries — you'll use them again

## Proactive Monitoring

Don't wait for incidents. Set up EventBridge rules for high-risk events:

```bash
aws events put-rule \
  --name "detect-root-login" \
  --event-pattern '{
    "source": ["aws.signin"],
    "detail-type": ["AWS Console Sign In via CloudTrail"],
    "detail": {
      "userIdentity": {
        "type": ["Root"]
      }
    }
  }'
```

CloudTrail is your forensic toolkit. The time to learn how to use it is before you need it, not during an incident at 2am.

---

**References:**
- [CloudTrail Documentation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html)
- [Querying CloudTrail with Athena](https://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html)
- [AWS Incident Response Guide](https://docs.aws.amazon.com/whitepapers/latest/aws-security-incident-response-guide/welcome.html)
