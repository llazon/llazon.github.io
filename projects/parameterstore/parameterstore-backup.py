#!/usr/bin/env python

import boto3
import time
import json
import math
import gnupg

# static variables
S3_BUCKET1 = "blah"
AWS_REGION1 = "us-east-1"
#
S3_BUCKET2 = "blah-2"
AWS_REGION2 = "us-east-2"
#
ENCRYPTION_KEY_ARN = ""
TODAY = time.strftime("%Y%m%d")

gpg = gnupg.GPG(gnupghome='/tmp')
gpg.encoding = 'utf-8'
gpg.verbose = False

key_data = open('blah.gpg').read()
import_result = gpg.import_keys(key_data)
print(import_result.results)

public_keys = gpg.list_keys()

# param variables
params = []
params_names = []
params_values = {}
str_params = ''

# boto
s3_1 = boto3.client('s3', region_name=AWS_REGION1)
s3_2 = boto3.client('s3', region_name=AWS_REGION2)
ssm = boto3.client('ssm', region_name=AWS_REGION1)

# describe parameters (without values)
ssm_paginator = ssm.get_paginator('describe_parameters')

page_iterator = ssm_paginator.paginate()

for page in page_iterator:
    for item in page['Parameters']:
        params.append(item)
        params_names.append(item['Name'])

# get values
params_names_loop = math.ceil(len(params_names) / 10) + 1

for x in range(1, params_names_loop):
    response = ssm.get_parameters(Names=params_names[((x-1)*10):(x*10)], WithDecryption=True)

    for item in response['Parameters']:
        params_values[item['Name']] = item['Value']
        itemjson = json.dumps(item, default=str)

# add values to parameters
for param in params:
    param['Value'] = params_values[param['Name']]
    str_params += json.dumps(param, default=str)+"\n"

# encrypt binary data and convert to string
encrypted_ascii_data = gpg.encrypt(str_params, [ENCRYPTION_KEY_ARN], always_trust=True, armor=True)
encrypted_string_data = str(encrypted_ascii_data)
print(encrypted_ascii_data.ok)
print(encrypted_ascii_data.status)
print(encrypted_ascii_data.stderr)

# write to s3 bucket
def lambda_handler(event, context):
    s3_1.put_object(Bucket=S3_BUCKET1, Key="parameterstore/backup/parameterstore-backup-"+TODAY+".gpg", Body=encrypted_string_data)
    s3_2.put_object(Bucket=S3_BUCKET2, Key="parameterstore/backup/parameterstore-backup-"+TODAY+".gpg", Body=encrypted_string_data)
