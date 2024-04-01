---
layout: post
title:  "Back-up your AWS Parameter Store"
date: 2023-06-01 00:00:00 -0000
categories:
---

# Overview
A daily backup of our Parameter Store is generated via a Lambda, GPG encrypted, and stored in S3.

# Write it

# Build it

# Configure it

# Run it

# Restore it

## Make sure you have all the pieces
Lambda: ops-parameterstore-backup
S3: s3://smugops/parameterstore/backup/parameterstore-backup-.gpg
GPG Public Key: blah.gpg
GPG Private Key: blah.gpg.secret
GPG Passphrase: keep it safe!
How to decrypt a backup.

## Setup your environment
mkdir -p ~/parameterstore
    cd ~/parameterstore
    aws s3 cp s3://blah/parameterstore/backup/parameterstore-backup-DATE.gpg .
Copy Private Key: blah.gpg.secret to ~/parameterstore

## Decrypt
    export HOME=~/parameterstore
    gpg --allow-secret-key-import --import blah.gpg.secret
    gpg --output parameterstore-backup.json --decrypt --recipient blah parameterstore-backup-DATE.gpg


