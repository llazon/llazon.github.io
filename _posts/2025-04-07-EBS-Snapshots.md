---
layout: post
title: "EBS Snapshot Management at Scale"
date: 2025-04-07
categories: aws storage automation
tags: aws ebs snapshots automation cost-optimization backup
---

# EBS Snapshot Management at Scale

EBS snapshots are one of those things that start simple and quietly become a cost problem. You create a few snapshots for backups, someone sets up a nightly cron job, and six months later you're paying for terabytes of snapshots that nobody remembers creating. I recently went through a cleanup exercise that saved us a meaningful chunk of our monthly bill, and I want to share the approach.

## The Problem

Here's what I found when I audited our snapshot situation:

- Over 2,000 snapshots across multiple accounts
- Many attached to volumes that no longer existed
- No consistent tagging or naming convention
- Some snapshots were years old with no clear owner
- Monthly cost was well into four figures just for snapshot storage

Sound familiar?

## Step 1: Get Visibility

Before you can clean up, you need to see what you have. This script dumps all snapshots with their associated volume status:

```bash
#!/bin/bash
# List all snapshots with volume status

aws ec2 describe-snapshots \
  --owner-ids self \
  --query 'Snapshots[*].[SnapshotId,VolumeId,StartTime,VolumeSize,Description,Tags[?Key==`Name`].Value|[0]]' \
  --output table \
  --region us-east-1
```

For a more detailed audit, check if the source volume still exists:

```bash
#!/bin/bash
# Find orphaned snapshots (source volume deleted)

SNAPSHOTS=$(aws ec2 describe-snapshots \
  --owner-ids self \
  --query 'Snapshots[*].[SnapshotId,VolumeId,VolumeSize,StartTime]' \
  --output text \
  --region us-east-1)

echo "SnapshotId | VolumeId | Size(GB) | Created | Volume Status"
echo "---------- | -------- | -------- | ------- | -------------"

while IFS=$'\t' read -r snap_id vol_id size created; do
  if [ "$vol_id" != "vol-ffffffff" ]; then
    vol_status=$(aws ec2 describe-volumes \
      --volume-ids "$vol_id" \
      --query 'Volumes[0].State' \
      --output text 2>/dev/null || echo "DELETED")
  else
    vol_status="NO_VOLUME"
  fi
  echo "$snap_id | $vol_id | ${size}GB | $created | $vol_status"
done <<< "$SNAPSHOTS"
```

## Step 2: Establish a Tagging Strategy

Before creating any new snapshots, establish tags that make lifecycle management possible:

```bash
# Tag format for automated snapshots
aws ec2 create-tags \
  --resources snap-0123456789abcdef0 \
  --tags \
    Key=Name,Value="web-server-daily-backup" \
    Key=Environment,Value=production \
    Key=Owner,Value=ops-team \
    Key=Retention,Value=30 \
    Key=CreatedBy,Value=automated
```

The `Retention` tag is key — it tells your cleanup automation how long to keep the snapshot.

## Step 3: Automate Snapshot Creation

AWS Data Lifecycle Manager (DLM) is the right tool for this. It handles creation, retention, and cleanup:

```bash
# Create a lifecycle policy for daily snapshots with 7-day retention
aws dlm create-lifecycle-policy \
  --description "Daily snapshots for production volumes" \
  --state ENABLED \
  --execution-role-arn arn:aws:iam::123456789012:role/AWSDataLifecycleManagerDefaultRole \
  --policy-details '{
    "PolicyType": "EBS_SNAPSHOT_MANAGEMENT",
    "ResourceTypes": ["VOLUME"],
    "TargetTags": [
      {"Key": "Backup", "Value": "daily"}
    ],
    "Schedules": [
      {
        "Name": "DailySnapshots",
        "CreateRule": {
          "Interval": 24,
          "IntervalUnit": "HOURS",
          "Times": ["03:00"]
        },
        "RetainRule": {
          "Count": 7
        },
        "TagsToAdd": [
          {"Key": "CreatedBy", "Value": "DLM"},
          {"Key": "Type", "Value": "daily-backup"}
        ],
        "CopyTags": true
      }
    ]
  }'
```

Tag your volumes to opt them into the policy:

```bash
aws ec2 create-tags \
  --resources vol-0123456789abcdef0 \
  --tags Key=Backup,Value=daily
```

## Step 4: Clean Up Orphaned Snapshots

For the existing mess, here's a cleanup script that identifies and optionally deletes orphaned snapshots:

```bash
#!/bin/bash
# Delete snapshots older than N days whose source volume no longer exists
# DRY RUN by default — remove --dry-run flag to actually delete

DAYS_OLD=90
DRY_RUN=true
REGION="us-east-1"
CUTOFF_DATE=$(date -d "-${DAYS_OLD} days" +%Y-%m-%dT%H:%M:%S 2>/dev/null || \
              date -v-${DAYS_OLD}d +%Y-%m-%dT%H:%M:%S)

echo "Finding snapshots older than $DAYS_OLD days (before $CUTOFF_DATE)..."

SNAPSHOTS=$(aws ec2 describe-snapshots \
  --owner-ids self \
  --query "Snapshots[?StartTime<='${CUTOFF_DATE}'].[SnapshotId,VolumeId,VolumeSize,StartTime]" \
  --output text \
  --region "$REGION")

TOTAL=0
ORPHANED=0
TOTAL_SIZE=0

while IFS=$'\t' read -r snap_id vol_id size created; do
  [ -z "$snap_id" ] && continue
  TOTAL=$((TOTAL + 1))

  # Check if volume still exists
  vol_exists=$(aws ec2 describe-volumes \
    --volume-ids "$vol_id" \
    --query 'Volumes[0].VolumeId' \
    --output text \
    --region "$REGION" 2>/dev/null)

  if [ "$vol_exists" = "None" ] || [ -z "$vol_exists" ]; then
    ORPHANED=$((ORPHANED + 1))
    TOTAL_SIZE=$((TOTAL_SIZE + size))
    echo "ORPHANED: $snap_id | vol: $vol_id | ${size}GB | $created"

    if [ "$DRY_RUN" = false ]; then
      aws ec2 delete-snapshot --snapshot-id "$snap_id" --region "$REGION"
      echo "  -> DELETED"
    fi
  fi
done <<< "$SNAPSHOTS"

echo ""
echo "Summary: $ORPHANED orphaned snapshots out of $TOTAL total (${TOTAL_SIZE}GB)"
if [ "$DRY_RUN" = true ]; then
  echo "DRY RUN — no snapshots were deleted. Set DRY_RUN=false to delete."
fi
```

## Step 5: Monitor Ongoing Costs

Set up a CloudWatch alarm to catch snapshot cost creep:

```bash
# Create a budget alarm for EBS snapshot costs
aws budgets create-budget \
  --account-id 123456789012 \
  --budget '{
    "BudgetName": "EBS-Snapshot-Monthly",
    "BudgetLimit": {"Amount": "500", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST",
    "CostFilters": {
      "Service": ["Amazon Elastic Compute Cloud - Compute"],
      "UsageType": ["EBS:SnapshotUsage"]
    }
  }' \
  --notifications-with-subscribers '[{
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80
    },
    "Subscribers": [{
      "SubscriptionType": "EMAIL",
      "Address": "[email]"
    }]
  }]'
```

## Cross-Region and Cross-Account Copies

If you're copying snapshots for DR, automate that too:

```bash
# Copy snapshot to another region
aws ec2 copy-snapshot \
  --source-region us-east-1 \
  --source-snapshot-id snap-0123456789abcdef0 \
  --destination-region us-west-2 \
  --description "DR copy from us-east-1"
```

DLM supports cross-region copy rules natively — use those instead of rolling your own.

## Lessons Learned

- DLM should be your default for snapshot management — stop writing cron jobs
- Tag everything. Untagged snapshots are the ones that become orphans
- Run the orphan audit monthly, not yearly
- Snapshot costs are proportional to changed data, not volume size (incremental)
- Don't forget about snapshots in AMIs — deregistering an AMI doesn't delete its snapshots
- Set up budget alerts before you have a cost problem, not after

The cleanup exercise took about a day and the DLM setup took another half day. The monthly savings made it one of the highest-ROI tasks I've done all quarter.

---

**References:**
- [AWS Data Lifecycle Manager](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snapshot-lifecycle.html)
- [EBS Snapshot Pricing](https://aws.amazon.com/ebs/pricing/)
- [EBS Snapshots Documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSSnapshots.html)
