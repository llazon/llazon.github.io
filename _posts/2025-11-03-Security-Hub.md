---
layout: post
title: "The New AWS Security Hub: GuardDuty, Inspector, and CSPM Under One Roof"
date: 2025-11-03
categories: aws security compliance
tags: aws security-hub guardduty inspector cspm compliance unified-security
---

# The New AWS Security Hub: GuardDuty, Inspector, and CSPM Under One Roof

AWS has been steadily consolidating its security services, and the new Security Hub is the culmination of that effort. What used to be a collection of separate services — GuardDuty for threat detection, Inspector for vulnerability scanning, and various CSPM (Cloud Security Posture Management) tools — now lives under a unified experience in Security Hub. If you've been managing these services independently, it's time to take a fresh look.

## What Changed

The old Security Hub was primarily an aggregator — it pulled findings from other services and displayed them in one place. The new Security Hub is more than that:

- GuardDuty threat detection is now natively integrated, not just a findings source
- Inspector vulnerability scanning is built in with automated assessment pipelines
- CSPM capabilities replace the old Security Hub standards with more comprehensive posture checks
- Unified scoring gives you a single security score across all three domains
- Automated remediation workflows are first-class features, not bolted-on afterthoughts

## Enabling the Unified Experience

If you already have Security Hub enabled, the new features roll out automatically. For new setups:

```bash
# Enable Security Hub with all integrated services
aws securityhub enable-security-hub \
  --enable-default-standards \
  --control-finding-generator SECURITY_CONTROL

# Verify GuardDuty integration
aws guardduty list-detectors

# Verify Inspector integration
aws inspector2 list-coverage \
  --query 'coveredResources[*].[resourceId,resourceType,scanStatus.statusCode]' \
  --output table
```

### Multi-Account Setup

For organizations, delegate Security Hub administration:

```bash
# Designate admin account
aws securityhub enable-organization-admin-account \
  --admin-account-id 222222222222

# Auto-enable for new accounts
aws securityhub update-organization-configuration \
  --auto-enable \
  --auto-enable-standards
```

## The Three Pillars

### 1. Threat Detection (GuardDuty)

GuardDuty's findings now appear directly in Security Hub with full context. No more switching between consoles. The key detection categories:

- Account compromise indicators
- EC2 instance compromise (crypto mining, C2 communication)
- S3 bucket compromise (unusual access patterns)
- EKS and ECS runtime threat detection
- RDS login anomalies
- Lambda function abuse

What's improved: GuardDuty findings now automatically correlate with Inspector vulnerability data. If GuardDuty detects suspicious activity on an instance that Inspector flagged as having a critical CVE, Security Hub surfaces that connection.

```bash
# View GuardDuty findings through Security Hub
aws securityhub get-findings \
  --filters '{"ProductName":[{"Value":"GuardDuty","Comparison":"EQUALS"}],"SeverityLabel":[{"Value":"HIGH","Comparison":"EQUALS"}]}' \
  --query 'Findings[*].[Title,Severity.Label,CreatedAt,Resources[0].Id]' \
  --output table
```

### 2. Vulnerability Management (Inspector)

Inspector now runs continuously (not just on-demand assessments) and covers:

- EC2 instances (OS and package vulnerabilities)
- ECR container images
- Lambda functions (dependency vulnerabilities)
- Code scanning for Lambda

The integration with Security Hub means vulnerability findings are automatically prioritized alongside threat findings:

```bash
# View Inspector findings by severity
aws securityhub get-findings \
  --filters '{"ProductName":[{"Value":"Inspector","Comparison":"EQUALS"}],"SeverityLabel":[{"Value":"CRITICAL","Comparison":"EQUALS"}]}' \
  --sort-criteria '{"Field":"SeverityLabel","SortOrder":"desc"}' \
  --query 'Findings[*].[Title,Severity.Label,Resources[0].Type,Resources[0].Id]' \
  --output table
```

### 3. Cloud Security Posture Management (CSPM)

This is where the biggest change happened. The old "Security Standards" (CIS, AWS Foundational) have been replaced with a unified set of security controls that map to multiple frameworks simultaneously:

- AWS Foundational Security Best Practices
- CIS AWS Foundations Benchmark
- PCI DSS
- NIST 800-53
- SOC 2

A single control can satisfy requirements across multiple frameworks, which means less duplicate work:

```bash
# View your security score
aws securityhub get-security-control-definitions \
  --query 'SecurityControlDefinitions[*].[SecurityControlId,Title,SeverityRating]' \
  --output table

# Check compliance status
aws securityhub get-findings \
  --filters '{"ComplianceStatus":[{"Value":"FAILED","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' \
  --sort-criteria '{"Field":"SeverityLabel","SortOrder":"desc"}' \
  --max-items 20
```

## Automated Remediation

The new Security Hub supports automated remediation through EventBridge and custom actions:

```bash
# Create an EventBridge rule for auto-remediation
aws events put-rule \
  --name "remediate-public-s3" \
  --event-pattern '{
    "source": ["aws.securityhub"],
    "detail-type": ["Security Hub Findings - Imported"],
    "detail": {
      "findings": {
        "ProductName": ["Security Hub"],
        "Compliance": {"Status": ["FAILED"]},
        "Title": [{"prefix": "S3"}],
        "Severity": {"Label": ["CRITICAL", "HIGH"]}
      }
    }
  }'
```

Example: Auto-remediate public S3 buckets with a Lambda function:

```python
import boto3

s3 = boto3.client('s3')

def lambda_handler(event, context):
    for finding in event['detail']['findings']:
        for resource in finding['Resources']:
            if resource['Type'] == 'AwsS3Bucket':
                bucket_name = resource['Details']['AwsS3Bucket']['Name'] if 'Details' in resource else resource['Id'].split(':')[-1]

                # Block public access
                s3.put_public_access_block(
                    Bucket=bucket_name,
                    PublicAccessBlockConfiguration={
                        'BlockPublicAcls': True,
                        'IgnorePublicAcls': True,
                        'BlockPublicPolicy': True,
                        'RestrictPublicBuckets': True
                    }
                )

                print(f"Blocked public access on {bucket_name}")

    return {'status': 'remediated'}
```

## Dashboard and Reporting

Security Hub now provides a unified dashboard with:

- Overall security score (0-100)
- Score breakdown by pillar (threats, vulnerabilities, posture)
- Trend graphs showing improvement over time
- Top findings by severity and resource type

For executive reporting:

```bash
# Export findings to S3 for reporting
aws securityhub create-finding-aggregator \
  --region-linking-mode ALL_REGIONS

# Get summary counts by severity
aws securityhub get-findings \
  --filters '{"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' \
  --query 'Findings | length(@)'
```

## Migration Tips

If you're coming from separate GuardDuty/Inspector/Security Hub setups:

1. Don't disable your existing services — the new Security Hub integrates with them
2. Review your existing suppression rules in GuardDuty — they carry over
3. Check that Inspector is scanning all resource types you care about
4. Update your EventBridge rules to use the new finding format
5. Review the new control IDs — they've changed from the old standard-specific IDs
6. Update any custom integrations that parse Security Hub findings

## What I Like

- Single pane of glass that actually works (not just an aggregator)
- Correlated findings across threat detection and vulnerability data
- The unified security score is useful for tracking progress
- Multi-framework compliance mapping saves significant audit prep time
- Automated remediation is much easier to set up

## What to Watch Out For

- Costs can add up with Inspector scanning at scale — monitor your usage
- The security score can be misleading if you have legitimate exceptions
- Auto-remediation needs careful testing — don't auto-fix things in production without validation
- Some controls may not apply to your environment — use suppression rules

The consolidation of these services into Security Hub is a meaningful improvement. Instead of context-switching between three consoles and mentally correlating findings, you get a unified view of your security posture. It's the kind of change that makes the daily security review actually manageable.

---

**References:**
- [AWS Security Hub Documentation](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html)
- [GuardDuty Documentation](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html)
- [Inspector Documentation](https://docs.aws.amazon.com/inspector/latest/user/what-is-inspector.html)
- [AWS Security Best Practices](https://aws.amazon.com/architecture/security-identity-compliance/)
