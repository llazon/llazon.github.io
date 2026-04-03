---
layout: post
title: "HDR Image Processing on AWS"
date: 2026-03-02
categories: aws media processing
tags: aws image-processing hdr media lambda ec2 imagemagick
---

# HDR Image Processing on AWS

I recently worked on a project that required processing HDR (High Dynamic Range) images at scale on AWS. HDR formats are becoming more common — phone cameras shoot in HDR, professional photographers deliver in HDR, and display technology is catching up. But the tooling for processing these formats in the cloud is still catching up. Here's what I learned.

## HDR Formats: A Quick Primer

The HDR landscape is fragmented:

| Format | Extension | Notes |
|--------|-----------|-------|
| OpenEXR | .exr | Industry standard for VFX, high precision |
| Ultra HDR | .uhdr/.jpg | Google's format, JPEG-compatible with embedded gain map |
| AVIF | .avif | Modern format with HDR support, good compression |
| HEIF | .heic | Apple's preferred format, supports HDR |
| HDR10 | varies | Display standard, usually in video containers |
| Radiance HDR | .hdr | Older format, still used in 3D rendering |

The challenge: most image processing libraries handle SDR (Standard Dynamic Range) well but have varying levels of HDR support.

## Extracting HDR Metadata

Before processing, you need to understand what you're working with. Here's how to extract HDR information from different formats:

```bash
# Using exiftool for general metadata
exiftool -HDR -ColorSpace -BitsPerSample -ProfileDescription image.jpg

# For Ultra HDR (Google's format), check for the gain map
exiftool -XMP:HDRGainMap -XMP:HDRGainMapVersion image.uhdr

# For OpenEXR, use exrinfo or OpenEXR tools
exrinfo test_hdr.exr

# Using ImageMagick to inspect
magick identify -verbose image.exr 2>&1 | grep -E "Type|Depth|Colorspace|Channel"
```

For a more thorough inspection script:

```bash
#!/bin/bash
# extract_hdr_info.sh - Extract HDR metadata from an image

FILE="$1"
if [ -z "$FILE" ]; then
  echo "Usage: $0 <image_file>"
  exit 1
fi

echo "=== File Info ==="
file "$FILE"

echo ""
echo "=== EXIF HDR Data ==="
exiftool -s -HDR* -ColorSpace -BitsPerSample -ProfileDescription \
  -XMP:HDRGainMap* -ICC_Profile:ProfileDescription "$FILE" 2>/dev/null

echo ""
echo "=== ImageMagick Analysis ==="
magick identify -format "Format: %m\nColorspace: %[colorspace]\nDepth: %[depth]\nSize: %wx%h\nChannels: %[channels]\n" "$FILE" 2>/dev/null
```

## Processing HDR Images on Lambda

For lightweight HDR processing, Lambda with a custom layer works well. The trick is getting the right libraries compiled for the Lambda runtime:

```bash
# Build an ImageMagick layer with HDR format support
# This needs to be done on Amazon Linux 2 (or in a Docker container matching the Lambda runtime)

# Install build dependencies
yum install -y gcc make libtool \
  libjpeg-turbo-devel libpng-devel \
  OpenEXR-devel OpenEXR-libs \
  libwebp-devel

# Build ImageMagick with HDR support
wget https://imagemagick.org/archive/ImageMagick.tar.gz
tar xzf ImageMagick.tar.gz
cd ImageMagick-*

./configure \
  --prefix=/opt \
  --with-openexr=yes \
  --with-webp=yes \
  --with-jpeg=yes \
  --with-png=yes \
  --disable-docs

make -j$(nproc)
make install DESTDIR=/tmp/layer

# Package as a Lambda layer
cd /tmp/layer
zip -r /tmp/imagemagick-hdr-layer.zip opt/
```

A Lambda function that converts HDR to SDR with tone mapping:

```python
import subprocess
import boto3
import os

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    # Download the HDR image
    input_path = f'/tmp/input_{os.path.basename(key)}'
    output_path = f'/tmp/output_{os.path.basename(key)}.jpg'

    s3.download_file(bucket, key, input_path)

    # Convert HDR to SDR with tone mapping
    # Using Reinhard tone mapping operator
    result = subprocess.run([
        '/opt/bin/magick', input_path,
        '-colorspace', 'RGB',
        '-evaluate', 'Log', '2',      # Simple tone mapping
        '-colorspace', 'sRGB',
        '-depth', '8',
        '-quality', '90',
        output_path
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"ImageMagick error: {result.stderr}")

    # Upload the SDR version
    output_key = f"sdr/{os.path.basename(key)}.jpg"
    s3.upload_file(output_path, bucket, output_key)

    return {
        'statusCode': 200,
        'body': f'Converted {key} -> {output_key}'
    }
```

## Processing at Scale on EC2

For batch processing or when Lambda's 15-minute timeout isn't enough, use EC2 with a processing queue:

```python
import boto3
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123456789012/hdr-processing'
BUCKET = 'my-image-bucket'

def process_image(message):
    """Process a single HDR image from the SQS queue."""
    body = json.loads(message['Body'])
    key = body['key']
    operation = body.get('operation', 'tone_map')

    input_path = f'/tmp/{os.path.basename(key)}'
    s3.download_file(BUCKET, key, input_path)

    if operation == 'tone_map':
        output_path = tone_map(input_path)
    elif operation == 'extract_gain_map':
        output_path = extract_gain_map(input_path)
    elif operation == 'resize':
        output_path = resize_hdr(input_path, body.get('width', 1920))
    else:
        raise ValueError(f"Unknown operation: {operation}")

    output_key = f"processed/{operation}/{os.path.basename(key)}"
    s3.upload_file(output_path, BUCKET, output_key)

    # Delete the message from the queue
    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message['ReceiptHandle']
    )

    # Cleanup
    os.remove(input_path)
    os.remove(output_path)

def tone_map(input_path):
    output_path = input_path + '.tonemapped.jpg'
    subprocess.run([
        'magick', input_path,
        '-colorspace', 'RGB',
        '-evaluate', 'Log', '2',
        '-colorspace', 'sRGB',
        '-depth', '8',
        '-quality', '92',
        output_path
    ], check=True)
    return output_path

def resize_hdr(input_path, width):
    output_path = input_path + f'.{width}w.exr'
    subprocess.run([
        'magick', input_path,
        '-resize', f'{width}x',
        '-depth', '16',
        output_path
    ], check=True)
    return output_path

# Process messages in parallel
while True:
    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20
    )

    messages = response.get('Messages', [])
    if not messages:
        continue

    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(process_image, messages)
```

## Ultra HDR (Google's Format)

Ultra HDR is interesting because it's backward-compatible with JPEG — regular viewers see the SDR version, but HDR-capable displays use the embedded gain map for HDR rendering.

Working with Ultra HDR requires Google's `libultrahdr` library:

```bash
# Build libultrahdr
git clone https://github.com/google/libultrahdr.git
cd libultrahdr
mkdir build && cd build
cmake ..
make -j$(nproc)

# Convert a standard image to Ultra HDR
./ultrahdr_app -m 0 -p input.jpg -o output.uhdr

# Extract the gain map from an Ultra HDR image
./ultrahdr_app -m 1 -p input.uhdr -o extracted
```

## Cost Considerations

HDR images are larger than SDR equivalents, which affects storage and transfer costs:

- OpenEXR files can be 10-50x larger than equivalent JPEGs
- Processing is CPU-intensive — consider Graviton instances for better price/performance
- Use S3 Intelligent-Tiering for processed images with unpredictable access patterns
- Lambda with ARM64 is 20% cheaper and handles ImageMagick workloads well

For batch processing, Spot Instances are ideal since image processing is inherently interruptible.

## Tips From the Trenches

- Always preserve the original HDR file — tone mapping is lossy and irreversible
- Test your processing pipeline with images from different sources (phones, cameras, renders)
- OpenEXR's compression options matter — ZIP compression is a good default
- Color space handling is critical — get it wrong and your images will look washed out or oversaturated
- ImageMagick 7.x has much better HDR support than 6.x — make sure you're on the latest
- Monitor your Lambda memory usage — HDR images can be memory-hungry during processing

HDR image processing on AWS is doable but requires more setup than standard image pipelines. The tooling is improving rapidly, and as HDR displays become ubiquitous, having a solid processing pipeline will be increasingly important.

---

**References:**
- [OpenEXR](https://openexr.com/)
- [Google Ultra HDR](https://github.com/google/libultrahdr)
- [ImageMagick HDR Support](https://imagemagick.org/script/formats.php)
- [AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/chapter-layers.html)
