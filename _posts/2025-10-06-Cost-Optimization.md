---
layout: post
title: "AWS Cost Optimization: Patterns That Save Real Money"
date: 2025-10-06
categories: aws cost-optimization finops
tags: aws cost-optimization finops savings-plans reserved-instances right-sizing
---

# AWS Cost Optimization: Patterns That Save Real Money

Cost optimization isn't a one-time project — it's an ongoing practice. After years of managing AWS bills across multiple accounts, I've found that the biggest savings come from a handful of repeatable patterns. Here's what actually moves the needle.

## Start With Visibility

You can't optimize what you can't see. Before making any changes:

```bash
# Enable Cost Explorer (if not already)
aws ce get-cost-and-usage \
  --time-period Start=2025-09-01,End=2025-10-01 \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[0].Groups[*].[Keys[0],Metrics.UnblendedCost.Amount]' \
  --output table
```

Set up Cost Anomaly Detection — it's free and catches unexpected spikes:

```bash
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "MonitorName": "ServiceMonitor",
    "MonitorType": "DIMENSIONAL",
    "MonitorDimension": "SERVICE"
  }'

aws ce create-anomaly-subscription \
  --anomaly-subscription '{
    "SubscriptionName": "DailyAlerts",
    "MonitorArnList": ["arn:aws:ce::123456789012:anomalymonitor/monitor-id"],
    "Subscribers": [{"Address": "[email]", "Type": "EMAIL"}],
    "Frequency": "DAILY",
    "ThresholdExpression": {
      "Dimensions": {
        "Key": "ANOMALY_TOTAL_IMPACT_ABSOLUTE",
        "Values": ["100"],
        "MatchOptions": ["GREATER_THAN_OR_EQUAL"]
      }
    }
  }'
```

## Pattern 1: Right-Size Your Instances

This is consistently the biggest win. Most instances are over-provisioned because someone picked a size "just in case" and never revisited it.

Use AWS Compute Optimizer:

```bash
aws compute-optimizer get-ec2-instance-recommendations \
  --query 'instanceRecommendations[*].[instanceArn,currentInstanceType,recommendationOptions[0].instanceType,recommendationOptions[0].projectedUtilizationMetrics]' \
  --output table
```

Rules of thumb:
- If average CPU is under 20%, you're probably one or two sizes too big
- If average CPU is under 5%, you might not need the instance at all
- Check memory utilization too (requires CloudWatch agent)
- Right-size in staging first, then production

## Pattern 2: Savings Plans

Savings Plans give you up to 72% discount in exchange for a 1 or 3 year commitment to a dollar amount of usage per hour.

```bash
# Get Savings Plans recommendations
aws ce get-savings-plans-purchase-recommendation \
  --savings-plans-type "COMPUTE_SP" \
  --term-in-years "ONE_YEAR" \
  --payment-option "NO_UPFRONT" \
  --lookback-period-in-days "THIRTY_DAYS"
```

My approach:
- Start with Compute Savings Plans (most flexible — covers EC2, Fargate, Lambda)
- Commit to your baseline usage, not your peak
- Use 1-year No Upfront to start — you can always add more
- Review utilization monthly and adjust

## Pattern 3: Kill Zombie Resources

These are the resources nobody is using but everyone is paying for:

### Unattached EBS Volumes

```bash
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query 'Volumes[*].[VolumeId,Size,CreateTime,VolumeType]' \
  --output table
```

### Unused Elastic IPs

```bash
aws ec2 describe-addresses \
  --query 'Addresses[?AssociationId==`null`].[PublicIp,AllocationId]' \
  --output table
```

### Old Snapshots

```bash
# Snapshots older than 180 days
CUTOFF=$(date -d "-180 days" +%Y-%m-%dT%H:%M:%S)
aws ec2 describe-snapshots \
  --owner-ids self \
  --query "Snapshots[?StartTime<='${CUTOFF}'].[SnapshotId,VolumeSize,StartTime]" \
  --output table
```

### Idle Load Balancers

```bash
# ALBs with zero healthy targets
for alb_arn in $(aws elbv2 describe-load-balancers --query 'LoadBalancers[*].LoadBalancerArn' --output text); do
  target_groups=$(aws elbv2 describe-target-groups --load-balancer-arn "$alb_arn" --query 'TargetGroups[*].TargetGroupArn' --output text)
  for tg in $target_groups; do
    healthy=$(aws elbv2 describe-target-health --target-group-arn "$tg" --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`]' --output text)
    if [ -z "$healthy" ]; then
      echo "IDLE: $alb_arn (target group: $tg)"
    fi
  done
done
```

## Pattern 4: S3 Storage Optimization

S3 costs sneak up on you. Use Storage Lens for visibility and lifecycle policies for automation:

```bash
# Check your biggest buckets
aws s3api list-buckets --query 'Buckets[*].Name' --output text | tr '\t' '\n' | \
while read bucket; do
  size=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/S3 \
    --metric-name BucketSizeBytes \
    --dimensions Name=BucketName,Value=$bucket Name=StorageType,Value=StandardStorage \
    --start-time $(date -d "-1 day" +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date +%Y-%m-%dT%H:%M:%S) \
    --period 86400 \
    --statistics Average \
    --query 'Datapoints[0].Average' \
    --output text 2>/dev/null)
  if [ "$size" != "None" ] && [ -n "$size" ]; then
    size_gb=$(echo "scale=2; $size / 1073741824" | bc)
    echo "$bucket: ${size_gb}GB"
  fi
done | sort -t: -k2 -rn | head -20
```

Quick wins:
- Enable S3 Intelligent-Tiering for buckets with unknown access patterns
- Set lifecycle policies to transition old data to Glacier
- Delete incomplete multipart uploads (they cost money and are invisible)

```bash
# Clean up incomplete multipart uploads
aws s3api list-multipart-uploads --bucket my-bucket \
  --query 'Uploads[*].[Key,UploadId,Initiated]' --output text
```

## Pattern 5: NAT Gateway Optimization

NAT Gateways are $0.045/hour plus $0.045/GB processed. For high-traffic environments, this adds up fast.

- Use VPC endpoints for AWS service traffic (see my July post)
- Consider NAT instances for development environments
- Use a single NAT Gateway in non-production (instead of one per AZ)
- Monitor NAT Gateway bytes processed in CloudWatch

## Pattern 6: Reserved Capacity for Databases

RDS Reserved Instances still offer the best discounts for databases:

```bash
aws rds describe-reserved-db-instances-offerings \
  --db-instance-class db.r6g.xlarge \
  --duration 31536000 \
  --product-description postgresql \
  --offering-type "No Upfront" \
  --query 'ReservedDBInstancesOfferings[*].[OfferingType,Duration,FixedPrice,RecurringCharges[0].RecurringChargeAmount]' \
  --output table
```

## Pattern 7: Spot Instances for Fault-Tolerant Workloads

Spot instances are 60-90% cheaper than On-Demand. Use them for:
- CI/CD build agents
- Batch processing
- Dev/test environments
- Any workload that can handle interruption

```hcl
# Terraform example: Mixed instance policy for ASG
resource "aws_autoscaling_group" "workers" {
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 1
      on_demand_percentage_above_base_capacity = 25
      spot_allocation_strategy                 = "capacity-optimized"
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.worker.id
        version            = "$Latest"
      }

      override {
        instance_type = "m5.xlarge"
      }
      override {
        instance_type = "m5a.xlarge"
      }
      override {
        instance_type = "m6i.xlarge"
      }
    }
  }
}
```

## Monthly Review Checklist

Run through this every month:

1. Check Cost Explorer for unexpected increases
2. Review Compute Optimizer recommendations
3. Scan for zombie resources (unattached volumes, unused EIPs)
4. Check Savings Plans utilization
5. Review data transfer costs (often overlooked)
6. Verify lifecycle policies are working (check S3 storage class distribution)

## The 80/20 Rule

In my experience, 80% of savings come from:
- Right-sizing instances
- Savings Plans / Reserved Instances
- Deleting unused resources
- S3 lifecycle policies

Everything else is optimization at the margins. Start with these four and you'll make a meaningful dent in your bill.

---

**References:**
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [AWS Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html)
- [Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html)
- [AWS Well-Architected Cost Optimization Pillar](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html)
