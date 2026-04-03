---
layout: post
title: "VPC Endpoints & Private Networking: Keeping Traffic Off the Public Internet"
date: 2025-07-07
categories: aws networking security
tags: aws vpc endpoints privatelink networking security cost-optimization
---

# VPC Endpoints & Private Networking: Keeping Traffic Off the Public Internet

Here's something that surprises a lot of people: when your EC2 instance in a private subnet calls the S3 API, that traffic goes out through your NAT Gateway, across the public internet, and into the S3 endpoint. You're paying NAT Gateway data processing fees for traffic that never needs to leave AWS's network.

VPC endpoints fix this. They keep traffic between your VPC and AWS services entirely within the AWS network — better security, lower latency, and often significant cost savings.

## Two Types of Endpoints

### Gateway Endpoints (Free)

Available for S3 and DynamoDB only. These are route table entries that direct traffic to the service through AWS's internal network.

```bash
# Create a gateway endpoint for S3
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-0123456789abcdef0 \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids rtb-0123456789abcdef0

# Create a gateway endpoint for DynamoDB
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-0123456789abcdef0 \
  --service-name com.amazonaws.us-east-1.dynamodb \
  --route-table-ids rtb-0123456789abcdef0
```

These are free. There is no reason not to have them in every VPC. Seriously — go create them right now if you haven't already.

### Interface Endpoints (PrivateLink)

Available for most AWS services. These create an ENI in your subnet with a private IP address that routes to the service.

```bash
# Create an interface endpoint for SSM
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-0123456789abcdef0 \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.ssm \
  --subnet-ids subnet-0123456789abcdef0 subnet-0123456789abcdef1 \
  --security-group-ids sg-0123456789abcdef0 \
  --private-dns-enabled
```

Interface endpoints cost $0.01/hour per AZ (~$7.20/month) plus $0.01/GB of data processed. This is almost always cheaper than NAT Gateway data processing at $0.045/GB.

## The Cost Math

Let's say you have instances in private subnets making heavy use of AWS APIs (CloudWatch, SSM, KMS, STS, etc.):

**Without VPC endpoints (NAT Gateway):**
- NAT Gateway hourly: $0.045/hour × 730 hours = $32.85/month
- Data processing: 500GB × $0.045/GB = $22.50/month
- Total: ~$55/month

**With interface endpoints (3 services, 2 AZs):**
- Endpoint hourly: 3 × 2 × $0.01 × 730 = $43.80/month
- Data processing: 500GB × $0.01/GB = $5.00/month
- Total: ~$49/month

The savings grow with data volume. At 2TB/month, you're saving over $50/month per VPC. And that's before considering that you might be able to eliminate the NAT Gateway entirely if all your outbound traffic is to AWS services.

## Which Endpoints Do You Need?

Start with the services your instances actually talk to. Here's my priority list:

### Must-Have (if you use these services)
- `com.amazonaws.REGION.s3` (Gateway — free)
- `com.amazonaws.REGION.dynamodb` (Gateway — free)
- `com.amazonaws.REGION.ssm` (for Systems Manager)
- `com.amazonaws.REGION.ssmmessages` (for Session Manager)
- `com.amazonaws.REGION.ec2messages` (for SSM Agent)

### High Value
- `com.amazonaws.REGION.monitoring` (CloudWatch metrics)
- `com.amazonaws.REGION.logs` (CloudWatch Logs)
- `com.amazonaws.REGION.kms` (if using encryption)
- `com.amazonaws.REGION.sts` (for role assumption)
- `com.amazonaws.REGION.ecr.api` and `ecr.dkr` (for container image pulls)

### Situational
- `com.amazonaws.REGION.secretsmanager`
- `com.amazonaws.REGION.sqs`
- `com.amazonaws.REGION.sns`
- `com.amazonaws.REGION.execute-api` (API Gateway)
- `com.amazonaws.REGION.lambda`

## Endpoint Policies

Don't just create endpoints — restrict what they can access. Endpoint policies act as an additional layer of access control:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSpecificBuckets",
      "Effect": "Allow",
      "Principal": "*",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-app-bucket",
        "arn:aws:s3:::my-app-bucket/*",
        "arn:aws:s3:::my-log-bucket",
        "arn:aws:s3:::my-log-bucket/*"
      ]
    }
  ]
}
```

Apply it:

```bash
aws ec2 modify-vpc-endpoint \
  --vpc-endpoint-id vpce-0123456789abcdef0 \
  --policy-document file://endpoint-policy.json
```

This prevents data exfiltration through the S3 endpoint — even if someone compromises an instance, they can only reach the buckets you've explicitly allowed.

## Security Group Configuration

Interface endpoints need security groups. At minimum, allow HTTPS (443) from your VPC CIDR:

```bash
aws ec2 create-security-group \
  --group-name vpc-endpoint-sg \
  --description "Security group for VPC endpoints" \
  --vpc-id vpc-0123456789abcdef0

aws ec2 authorize-security-group-ingress \
  --group-id sg-0123456789abcdef0 \
  --protocol tcp \
  --port 443 \
  --cidr 10.0.0.0/16
```

## Private DNS

When you enable private DNS on an interface endpoint, the default AWS service DNS name (e.g., `ssm.us-east-1.amazonaws.com`) resolves to the endpoint's private IP instead of the public IP. This means your existing code and AWS SDK calls work without any changes.

One gotcha: private DNS requires that your VPC has `enableDnsSupport` and `enableDnsHostnames` set to `true`.

```bash
aws ec2 modify-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --enable-dns-support '{"Value": true}'

aws ec2 modify-vpc-attribute \
  --vpc-id vpc-0123456789abcdef0 \
  --enable-dns-hostnames '{"Value": true}'
```

## Terraform Example

Here's how I manage endpoints in Terraform:

```hcl
locals {
  interface_endpoints = [
    "ssm",
    "ssmmessages",
    "ec2messages",
    "monitoring",
    "logs",
    "kms",
    "sts",
  ]
}

# Gateway endpoints (free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.region}.dynamodb"
  route_table_ids = [aws_route_table.private.id]
}

# Interface endpoints
resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoints)

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
}
```

## Monitoring Endpoint Usage

Check that traffic is actually flowing through your endpoints:

```bash
# Check endpoint status
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-0123456789abcdef0 \
  --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]' \
  --output table

# Enable CloudWatch metrics for the endpoint
# (available for interface endpoints)
# Check CloudWatch for metrics under AWS/PrivateLinkEndpoints
```

Also check your NAT Gateway metrics — if you've set up endpoints correctly, you should see a drop in data processed through the NAT Gateway.

## Common Pitfalls

- Forgetting to add endpoints in all AZs where you have instances
- Not enabling private DNS (traffic still goes through NAT)
- Security groups blocking port 443 to the endpoint
- Endpoint policies that are too restrictive (breaking SDK calls)
- Not updating route tables for gateway endpoints
- Creating interface endpoints for S3/DynamoDB when gateway endpoints are free

VPC endpoints are one of those infrastructure improvements that pay for themselves quickly. Start with the free gateway endpoints for S3 and DynamoDB, then add interface endpoints for your most-used services. Your security posture improves and your AWS bill goes down — that's a rare combination.

---

**References:**
- [VPC Endpoints Documentation](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)
- [VPC Endpoint Pricing](https://aws.amazon.com/privatelink/pricing/)
- [NAT Gateway Pricing](https://aws.amazon.com/vpc/pricing/)
- [VPC Endpoint Policies](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-access.html)
