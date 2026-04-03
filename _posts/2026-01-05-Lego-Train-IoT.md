---
layout: post
title: "Remote Controlled Lego Christmas Tree Train with AWS IoT and Livestream"
date: 2026-01-05
categories: aws iot projects
tags: aws iot lego raspberry-pi livestream kinesis-video fun-projects
---

# Remote Controlled Lego Christmas Tree Train with AWS IoT and Livestream

Every year I try to do a fun holiday project that combines physical hardware with AWS services. This year's project: a Lego train running around the Christmas tree that anyone could control remotely through a web interface, with a live camera feed streamed through AWS.

This was one of those projects where the "how hard can it be?" estimate was off by about 10x, but the end result was worth it.

## The Setup

The physical components:
- Lego Powered Up train set (the newer Bluetooth-enabled motors)
- Raspberry Pi 4 as the bridge between AWS and the train
- USB webcam pointed at the tree
- A circular track around the Christmas tree

The AWS components:
- AWS IoT Core for command and control
- Amazon Kinesis Video Streams for the live camera feed
- A simple S3-hosted static website for the control interface
- API Gateway + Lambda for the web-to-IoT bridge
- CloudFront for distribution

## Architecture

```
[Web Browser] → [CloudFront] → [S3 Static Site]
                                      ↓
                              [API Gateway]
                                      ↓
                              [Lambda Function]
                                      ↓
                              [AWS IoT Core]
                                      ↓ (MQTT)
                              [Raspberry Pi]
                                      ↓ (Bluetooth)
                              [Lego Train Motor]

[Raspberry Pi + Camera] → [Kinesis Video Streams] → [Web Browser (HLS playback)]
```

## AWS IoT Core Setup

First, set up the IoT thing and certificates:

```bash
# Create the IoT thing
aws iot create-thing --thing-name lego-train

# Create certificates
aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile cert.pem \
  --public-key-outfile public.key \
  --private-key-outfile private.key

# Create and attach a policy
aws iot create-policy \
  --policy-name lego-train-policy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "iot:Connect",
          "iot:Publish",
          "iot:Subscribe",
          "iot:Receive"
        ],
        "Resource": [
          "arn:aws:iot:us-east-1:123456789012:client/lego-train",
          "arn:aws:iot:us-east-1:123456789012:topic/train/*",
          "arn:aws:iot:us-east-1:123456789012:topicfilter/train/*"
        ]
      }
    ]
  }'

# Attach policy and thing to certificate
CERT_ARN=$(aws iot list-certificates --query 'certificates[0].certificateArn' --output text)
aws iot attach-policy --policy-name lego-train-policy --target "$CERT_ARN"
aws iot attach-thing-principal --thing-name lego-train --principal "$CERT_ARN"
```

## The Raspberry Pi Controller

The Pi runs a Python script that subscribes to IoT MQTT topics and translates commands into Bluetooth messages for the Lego motor:

```python
import json
import time
from awscrt import mqtt
from awsiot import mqtt_connection_builder
from pybricksdev.ble import find_device
from pybricksdev.connections.pybricks import PybricksHub

# IoT connection
connection = mqtt_connection_builder.mtls_from_path(
    endpoint="your-iot-endpoint.iot.us-east-1.amazonaws.com",
    cert_filepath="cert.pem",
    pri_key_filepath="private.key",
    ca_filepath="AmazonRootCA1.pem",
    client_id="lego-train",
    clean_session=False,
    keep_alive_secs=30
)

connect_future = connection.connect()
connect_future.result()
print("Connected to AWS IoT")

# Train state
current_speed = 0

def on_message(topic, payload, **kwargs):
    global current_speed
    message = json.loads(payload)
    command = message.get('command')

    if command == 'forward':
        current_speed = min(current_speed + 20, 100)
    elif command == 'reverse':
        current_speed = max(current_speed - 20, -100)
    elif command == 'stop':
        current_speed = 0
    elif command == 'speed':
        current_speed = message.get('value', 0)

    print(f"Command: {command}, Speed: {current_speed}")
    set_train_speed(current_speed)

def set_train_speed(speed):
    # Send speed command to Lego hub via Bluetooth
    # Implementation depends on your specific Lego setup
    pass

# Subscribe to command topic
subscribe_future, _ = connection.subscribe(
    topic="train/commands",
    qos=mqtt.QoS.AT_LEAST_ONCE,
    callback=on_message
)
subscribe_future.result()
print("Subscribed to train/commands")

# Keep running
while True:
    time.sleep(1)
```

## The Livestream

Kinesis Video Streams handles the camera feed. The Pi runs the GStreamer-based producer SDK:

```bash
# Install the Kinesis Video Streams producer SDK on the Pi
# (simplified — the actual build process involves cmake and dependencies)

# Stream from the USB camera
gst-launch-1.0 v4l2src device=/dev/video0 \
  ! videoconvert \
  ! video/x-raw,format=I420,width=640,height=480,framerate=15/1 \
  ! x264enc bframes=0 speed-preset=veryfast key-int-max=30 bitrate=500 \
  ! h264parse \
  ! video/x-h264,stream-format=avc,alignment=au \
  ! kvssink stream-name="lego-train-cam" \
    storage-size=128 \
    access-key="$AWS_ACCESS_KEY_ID" \
    secret-key="$AWS_SECRET_ACCESS_KEY" \
    aws-region="us-east-1"
```

On the viewer side, get an HLS streaming URL:

```bash
# Get the HLS streaming session URL
aws kinesisvideo get-data-endpoint \
  --stream-name lego-train-cam \
  --api-name GET_HLS_STREAMING_SESSION_URL

# Use the endpoint to get the actual URL
aws kinesis-video-archived-media get-hls-streaming-session-url \
  --stream-name lego-train-cam \
  --playback-mode LIVE \
  --hls-fragment-selector '{"FragmentSelectorType":"SERVER_TIMESTAMP"}' \
  --endpoint-url "https://your-kvs-endpoint"
```

## The Web Interface

A simple static site hosted on S3 with CloudFront:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Lego Train Control</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 20px; background: #1a1a2e; color: #eee; }
        .controls { margin: 20px auto; }
        button { font-size: 24px; padding: 15px 30px; margin: 5px; border-radius: 8px; border: none; cursor: pointer; }
        .forward { background: #4CAF50; color: white; }
        .stop { background: #f44336; color: white; }
        .reverse { background: #2196F3; color: white; }
        video { max-width: 640px; width: 100%; border-radius: 8px; margin: 20px 0; }
        h1 { color: #e94560; }
        .tree { font-size: 48px; }
    </style>
</head>
<body>
    <div class="tree">🎄</div>
    <h1>Lego Train Remote Control</h1>

    <video id="livestream" controls autoplay muted></video>

    <div class="controls">
        <button class="forward" onclick="sendCommand('forward')">🚂 Faster</button>
        <button class="stop" onclick="sendCommand('stop')">⏹ Stop</button>
        <button class="reverse" onclick="sendCommand('reverse')">⏪ Slower</button>
    </div>

    <p id="status">Connecting...</p>

    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>
        const API_URL = 'https://your-api-gateway-url/prod/train';

        async function sendCommand(command) {
            try {
                const response = await fetch(API_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command })
                });
                const result = await response.json();
                document.getElementById('status').textContent = `Command: ${command} ✓`;
            } catch (err) {
                document.getElementById('status').textContent = `Error: ${err.message}`;
            }
        }

        // Initialize HLS livestream
        async function initStream() {
            const response = await fetch(API_URL + '/stream');
            const { hlsUrl } = await response.json();

            if (Hls.isSupported()) {
                const hls = new Hls();
                hls.loadSource(hlsUrl);
                hls.attachMedia(document.getElementById('livestream'));
            }
        }

        initStream();
    </script>
</body>
</html>
```

## The Lambda Bridge

API Gateway calls this Lambda to publish commands to IoT:

```python
import json
import boto3

iot = boto3.client('iot-data')

def lambda_handler(event, context):
    body = json.loads(event.get('body', '{}'))
    command = body.get('command', 'stop')

    iot.publish(
        topic='train/commands',
        qos=1,
        payload=json.dumps({
            'command': command,
            'timestamp': int(time.time())
        })
    )

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'status': 'ok', 'command': command})
    }
```

## Lessons Learned

- Bluetooth range was the biggest challenge — the Pi needed to be within about 10 meters of the train hub, which meant running a long USB extension for the camera
- Kinesis Video Streams has a ~3-5 second latency for HLS playback, which is fine for watching but means the controls feel slightly delayed
- The Lego Powered Up Bluetooth protocol is well-documented by the community but quirky in practice
- IoT Core's MQTT is rock solid — zero dropped messages over the entire holiday season
- The kids (and honestly, the adults) loved being able to control the train from their phones
- Power management on the Pi was important — it ran 24/7 for three weeks

## Cost

The whole thing ran for about three weeks during the holidays:

- IoT Core: ~$0.50 (low message volume)
- Kinesis Video Streams: ~$15 (this was the biggest cost — streaming video adds up)
- Lambda + API Gateway: ~$0.10
- S3 + CloudFront: ~$0.50
- Total: ~$16 for three weeks of holiday fun

Not bad for a project that entertained the whole family and gave me an excuse to play with AWS IoT.

## What I'd Do Differently

- Use WebRTC instead of HLS for lower latency on the video feed
- Add a speed indicator to the web UI
- Add sound effects (the train horn would be great)
- Set up a schedule so the train runs automatically during certain hours
- Add a second camera angle

This was hands down the most fun AWS project I've done. There's something deeply satisfying about using cloud infrastructure to make a toy train go around a Christmas tree. If you're looking for a holiday project that combines hardware and AWS, I highly recommend it.

---

**References:**
- [AWS IoT Core](https://docs.aws.amazon.com/iot/latest/developerguide/what-is-aws-iot.html)
- [Kinesis Video Streams](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/what-is-kinesis-video.html)
- [Lego Powered Up Protocol](https://lego.github.io/lego-ble-wireless-protocol-docs/)
