---
layout: post
title: "S3 Lifecycle Policies & Object Tagging Automation"
date: 2025-02-03
categories: aws storage automation
tags: aws s3 lifecycle tagging automation cost-optimization
---

# S3 Lifecycle Policies & Object Tagging Automation

S3 is deceptively simple on the surface — you put objects in, you get objects out. But once you're managing millions of objects across dozens of buckets, storage costs creep up fast. Lifecycle policies and object tagging are the tools that keep things under control, and combining them is where the real power is.

## The Cost Problem

S3 Standard is $0.023 per GB/month. That doesn't sound like much until you realize you've got 50TB of logs that nobody has looked at in six months, or a bucket full of build artifacts from two years ago. The storage classes exist for a reason:

| Storage Class | Cost (per GB/month) | Use Case |
|--------------|-------------------|----------|
| Standard | $0.023 | Frequently accessed |
| Intelligent-Tiering | $0.023 + monitoring fee | Unknown access patterns |
| Standard-IA | $0.0125 | Infrequent access, rapid retrieval |
| Glacier Instant | $0.004 | Archive, millisecond retrieval |
| Glacier Flexible | $0.0036 | Archive, minutes to hours |
| Glacier Deep Archive | $0.00099 | Long-term archive, 12+ hours |

Moving data to the right tier at the right time is the whole game.

## Lifecycle Policies: The Basics

A lifecycle policy is a set of rules that automatically transition or expire objects. Here's a straightforward example:

```json
{
  "Rules": [
    {
      "ID": "TransitionAndExpireLogs",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "logs/"
      },
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
```

Apply it with the CLI:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket my-log-bucket \
  --lifecycle-configuration file://lifecycle.json
```

This moves logs to Standard-IA after 30 days, Glacier after 90, and deletes them after a year. Simple and effective.

## Tag-Based Lifecycle Rules

Prefix-based rules work fine for well-organized buckets, but real-world buckets are messy. Tags give you much more flexibility:

```json
{
  "Rules": [
    {
      "ID": "ArchiveProcessedData",
      "Status": "Enabled",
      "Filter": {
        "Tag": {
          "Key": "status",
          "Value": "processed"
        }
      },
      "Transitions": [
        {
          "Days": 7,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "ID": "DeleteTempFiles",
      "Status": "Enabled",
      "Filter": {
        "Tag": {
          "Key": "lifecycle",
          "Value": "temporary"
        }
      },
      "Expiration": {
        "Days": 3
      }
    }
  ]
}
```

Now your application can tag objects at upload time and the lifecycle policy handles the rest.

## Bulk Tagging Existing Objects

The tricky part is retroactively tagging objects that are already in your buckets. S3 Batch Operations is the tool for this, but it requires some setup.

### Step 1: Generate an Inventory

Enable S3 Inventory on your bucket to get a manifest of all objects:

```bash
aws s3api put-bucket-inventory-configuration \
  --bucket my-bucket \
  --id weekly-inventory \
  --inventory-configuration '{
    "Id": "weekly-inventory",
    "IsEnabled": true,
    "Destination": {
      "S3BucketDestination": {
        "Bucket": "arn:aws:s3:::my-inventory-bucket",
        "Format": "CSV",
        "Prefix": "inventory"
      }
    },
    "Schedule": {
      "Frequency": "Weekly"
    },
    "IncludedObjectVersions": "Current",
    "OptionalFields": ["Size", "LastModifiedDate", "StorageClass"]
  }'
```

### Step 2: Create a Batch Operations Job

Once you have an inventory manifest, create a batch job to apply tags:

```bash
aws s3control create-job \
  --account-id 123456789012 \
  --operation '{"S3PutObjectTagging":{"TagSet":[{"Key":"lifecycle","Value":"archive"}]}}' \
  --manifest '{"Spec":{"Format":"S3InventoryReport_CSV_20211130","Fields":["Bucket","Key"]},"Location":{"ObjectArn":"arn:aws:s3:::my-inventory-bucket/inventory/my-bucket/weekly-inventory/2025-01-26T00-00Z/manifest.json","ETag":"abc123"}}' \
  --report '{"Bucket":"arn:aws:s3:::my-report-bucket","Prefix":"batch-reports","Format":"Report_CSV_20180820","Enabled":true,"ReportScope":"AllTasks"}' \
  --priority 1 \
  --role-arn arn:aws:iam::123456789012:role/S3BatchRole \
  --region us-east-1
```

### Step 3: Selective Tagging with a Lambda Filter

For more complex logic — say, tagging objects based on their age or content type — pair Batch Operations with a Lambda function:

```python
import boto3

s3 = boto3.client('s3')

def lambda_handler(event, context):
    results = []

    for task in event['tasks']:
        bucket = task['s3BucketArn'].split(':::')[1]
        key = task['s3Key']

        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            content_type = head.get('ContentType', '')
            size = head.get('ContentLength', 0)

            # Tag large media files for archival
            if size > 100_000_000 and content_type.startswith('video/'):
                s3.put_object_tagging(
                    Bucket=bucket,
                    Key=key,
                    Tagging={
                        'TagSet': [
                            {'Key': 'lifecycle', 'Value': 'archive'},
                            {'Key': 'tagged-by', 'Value': 'batch-automation'}
                        ]
                    }
                )

            results.append({
                'taskId': task['taskId'],
                'resultCode': 'Succeeded',
                'resultString': 'Tagged'
            })
        except Exception as e:
            results.append({
                'taskId': task['taskId'],
                'resultCode': 'PermanentFailure',
                'resultString': str(e)
            })

    return {
        'invocationSchemaVersion': '1.0',
        'treatMissingKeysAs': 'PermanentFailure',
        'invocationId': event['invocationId'],
        'results': results
    }
```

## Removing Tags at Scale

Sometimes you need to remove tags — maybe a tag was applied incorrectly, or you need to reset objects back to a default lifecycle. This is something I've had to deal with recently, and the approach is similar: S3 Batch Operations with a `S3DeleteObjectTagging` operation, or a targeted Lambda that removes specific tag keys while preserving others.

```bash
aws s3control create-job \
  --account-id 123456789012 \
  --operation '{"S3DeleteObjectTagging":{}}' \
  --manifest '{"Spec":{"Format":"S3InventoryReport_CSV_20211130","Fields":["Bucket","Key"]},"Location":{"ObjectArn":"arn:aws:s3:::my-inventory-bucket/inventory/manifest.json","ETag":"abc123"}}' \
  --report '{"Bucket":"arn:aws:s3:::my-report-bucket","Prefix":"tag-removal","Format":"Report_CSV_20180820","Enabled":true,"ReportScope":"FailedTasksOnly"}' \
  --priority 1 \
  --role-arn arn:aws:iam::123456789012:role/S3BatchRole \
  --region us-east-1
```

Note: `S3DeleteObjectTagging` removes ALL tags. If you need to remove specific tags while keeping others, you'll need the Lambda approach — read existing tags, filter out the ones you don't want, and write back the rest.

## Monitoring and Validation

After setting up lifecycle policies, verify they're working:

```bash
# Check lifecycle configuration
aws s3api get-bucket-lifecycle-configuration --bucket my-bucket

# Check storage class distribution using S3 Storage Lens
# or query S3 Inventory reports with Athena

# Verify specific object tags
aws s3api get-object-tagging --bucket my-bucket --key path/to/object
```

S3 Storage Lens dashboards are great for tracking how your storage distribution changes over time after lifecycle policies kick in.

## Tips From the Trenches

- Lifecycle transitions have minimum duration requirements (e.g., 30 days before moving to Standard-IA)
- Objects smaller than 128KB won't transition to Standard-IA or One Zone-IA — they'll stay in Standard
- Glacier retrieval costs can surprise you — make sure you actually need the data before restoring
- Test lifecycle rules on a non-production bucket first
- Use S3 Storage Class Analysis to identify buckets that would benefit from lifecycle policies
- Tag objects at upload time whenever possible — retroactive tagging is always more work

---

**References:**
- [S3 Lifecycle Configuration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)
- [S3 Batch Operations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops.html)
- [S3 Storage Lens](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html)
- [S3 Pricing](https://aws.amazon.com/s3/pricing/)
