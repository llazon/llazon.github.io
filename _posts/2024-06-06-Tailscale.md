---
layout: post
title: "Deploying Tailscale Across AWS EC2 Linux Instances"
date: 2024-06-06
categories: aws networking
tags: aws ec2 tailscale vpn linux security
---

# Deploying Tailscale Across AWS EC2 Linux Instances

[Tailscale](https://tailscale.com/) is a modern VPN built on top of the WireGuard protocol that makes creating secure networks between devices incredibly simple. That all sounds great, but in reality things are always a bit more complicated.  I highly recommend following the documentation from Tailscale, and I'll highlight the places I diverge from the docs.

Let's walk through how to systematically deploy Tailscale across your AWS EC2 Linux instances with the end goal to have a fully automated system.

## Prerequisites

Before starting, ensure you have:

- An AWS account with EC2 instances running Linux
- Administrator access to these instances
- A [Tailscale account](https://tailscale.com/start) (free tier available)
- AWS CLI configured on your local machine
- bash!

## Set Up Your Tailscale Account

1. Sign up for a Tailscale account at [tailscale.com](https://tailscale.com/start)
2. Navigate to the [Admin Console](https://login.tailscale.com/admin/settings/keys)
3. Go to "Settings" → "Keys"
4. Create an auth key for automated deployments:
   - Click "Generate auth key"
   - Set an expiration (for production, consider 90 days)
   - Enable "Reusable" if you plan to use this key for multiple instances
   - Consider enabling "Ephemeral" if you want instances to disappear from your network when they shut down
   - Click "Create"
5. Copy the generated key for use in the installation steps

## Installation Script

Here is a bash script that can be used to install and configure Tailscale on any Linux instance:

```bash
#!/bin/bash

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale with auth key and configure it to start on boot
# Replace YOUR_AUTH_KEY with your actual Tailscale auth key
tailscale up --authkey YOUR_AUTH_KEY --hostname "aws-$(hostname)-$(curl -s http://169.254.169.254/latest/meta-data/instance-id | cut -c-8)"

# Ensure Tailscale starts on boot
if [ -f /etc/systemd/system/tailscaled.service ]; then
    systemctl enable tailscaled
elif [ -f /etc/init.d/tailscale ]; then
    update-rc.d tailscale defaults
fi

# Optional: Configure Tailscale to exit when the instance is stopping/terminating
cat > /usr/local/bin/tailscale-exit.sh << 'EOF'
#!/bin/bash
tailscale down
EOF

chmod +x /usr/local/bin/tailscale-exit.sh

# Add to cloud-init scripts if available
if [ -d /var/lib/cloud/scripts/per-boot ]; then
    ln -sf /usr/local/bin/tailscale-exit.sh /var/lib/cloud/scripts/per-boot/tailscale-up.sh
fi
```

## Deploy to New Instances

When launching new EC2 instances, you can automatically install Tailscale using the EC2 User Data feature:

1. When launching an EC2 instance, expand the "Advanced details" section
2. Scroll down to "User data"
3. Paste your Tailscale installation script (with your actual auth key)
4. Launch the instance

Example user data script:

```bash
#!/bin/bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --authkey YOUR_AUTH_KEY --hostname "aws-$(hostname)-$(curl -s http://169.254.169.254/latest/meta-data/instance-id | cut -c-8)"
```

## Deploy to Existing Instances with AWS Systems Manager

For existing EC2 instances, you can use AWS Systems Manager Run Command:

1. Ensure the SSM Agent is installed on your EC2 instances
2. In the AWS Console, navigate to AWS Systems Manager → Run Command
3. Click "Run command"
4. Search for and select "AWS-RunShellScript"
5. Under "Commands", paste your Tailscale installation script (with your actual auth key)
6. Select your target instances using tags, instance IDs, or resource groups
7. Configure other options as needed
8. Click "Run"

## Automate Deployment with CloudFormation or Terraform

For infrastructure-as-code, you can include Tailscale deployment in your templates.

### CloudFormation Example:

```yaml
Resources:
  MyEC2Instance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-12345678
      InstanceType: t3.micro
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          curl -fsSL https://tailscale.com/install.sh | sh
          tailscale up --authkey ${TailscaleAuthKey} --hostname "aws-$(hostname)-$(curl -s http://169.254.169.254/latest/meta-data/instance-id | cut -c-8)"
```

### Terraform Example:

```hcl
resource "aws_instance" "web" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  user_data = <<-EOF
              #!/bin/bash
              curl -fsSL https://tailscale.com/install.sh | sh
              tailscale up --authkey ${var.tailscale_auth_key} --hostname "aws-$(hostname)-$(curl -s http://169.254.169.254/latest/meta-data/instance-id | cut -c-8)"
              EOF

  tags = {
    Name = "TailscaleInstance"
  }
}
```

## Configure Advanced Tailscale Features

### Subnet Routing

To advertise an EC2 instance's subnet through Tailscale:

```bash
# Enable IP forwarding
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Start tailscale with subnet routing
tailscale up --authkey YOUR_AUTH_KEY --advertise-routes=10.0.0.0/16
```

Then approve the subnet routes in the Tailscale admin console.

### Auto-Approvals

For larger deployments, you can set up automated ACL rules in your Tailscale admin console:

```json
{
  "acls": [
    {
      "action": "accept",
      "users": ["autogroup:aws"],
      "ports": ["*:*"]
    }
  ],
  "tagOwners": {
    "tag:aws": ["autogroup:admin"],
  },
  "autoApprovers": {
    "routes": {
      "10.0.0.0/16": ["tag:aws"],
    }
  }
}
```

## Monitor Your Tailscale Network

1. Use the Tailscale admin console to view all connected machines
2. Implement monitoring of the tailscaled service using CloudWatch:

```bash
#!/bin/bash
if ! systemctl is-active --quiet tailscaled; then
  aws cloudwatch put-metric-data --namespace "Tailscale" --metric-name "ServiceDown" --value 1 --region us-east-1
  systemctl restart tailscaled
else
  aws cloudwatch put-metric-data --namespace "Tailscale" --metric-name "ServiceDown" --value 0 --region us-east-1
fi
```

## Troubleshooting

### Check Tailscale Status

```bash
tailscale status
```

### Troubleshoot Connectivity Issues

```bash
# Check if Tailscale daemon is running
sudo systemctl status tailscaled

# View logs
sudo journalctl -u tailscaled

# Restart Tailscale
sudo systemctl restart tailscaled
```

### Common Issues

- **Auth Key Expiration**: If instances suddenly disconnect, check if your auth key has expired.
- **IP Forwarding**: For subnet routing, verify that IP forwarding is enabled with `sysctl net.ipv4.ip_forward`.
- **Firewall Rules**: Ensure that your security groups allow UDP port 41641 outbound for Tailscale's DERP servers.
- **DNS Issues**: Tailscale includes Magic DNS; check for conflicts with custom DNS configurations.

## Security Best Practices

1. **Rotate Auth Keys**: Set expiration dates and rotate keys regularly
2. **Use ACL Policies**: Restrict which nodes can communicate with each other
3. **Enable MFA**: Require multi-factor authentication for your Tailscale account
4. **Audit Access**: Regularly review the devices connected to your Tailscale network
5. **Consider Ephemeral Nodes**: For temporary instances, use ephemeral node configuration

## Conclusion

Deploying Tailscale across your AWS EC2 Linux instances provides a secure, easy-to-manage networking layer that simplifies many common infrastructure challenges. Whether you're connecting a few instances or managing a large fleet, Tailscale's mesh network approach provides a more straightforward alternative to traditional VPN solutions.

By following this guide, you can systematically deploy Tailscale across your AWS infrastructure, ensuring secure communication between your instances while maintaining ease of management.

## Additional Resources

- [Tailscale Documentation](https://tailscale.com/kb/)
- [AWS Systems Manager Documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-systems-manager.html)
- [Tailscale GitHub Repository](https://github.com/tailscale)
- [WireGuard Protocol](https://www.wireguard.com/)
