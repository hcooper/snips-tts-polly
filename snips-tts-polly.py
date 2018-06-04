#!/usr/bin/env python3
import sys
import subprocess
import random
import string
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import json
import boto3
from pathlib import Path
import os
import hashlib
import toml

'''
This is meant to be a replacement for snips-tts, using the higher quality
AWS Polly service to produce audio from text.

It listens on the same MQTT topics as snips-tts. Both can run at the same time,
but it will cause duplicate audio output. Therefore stopping the existing
snips-tts service is probably best.

Initially developed from jarvis_listener.py by @tschmidty69
https://github.com/tschmidty69/homeassistant-config/blob/master/shell_command/jarvis_listener.py
'''

def log(msg):
    print(msg)


def on_connect(client, userdata, flags, rc):
    log("MQTT Connected")
    client.subscribe("hermes/tts/say")
    client.subscribe("hermes/audioServer/default/playFinished")


def _hash(text):
    return hashlib.md5(text.encode()).hexdigest()


def _random_id():
    return "".join(
        [random.choice(string.ascii_uppercase + string.digits) for i in range(16)]
    )


def _convert_mp3_to_wav(mp3_path, wav_path, delete=True):
    """ Uses mpg123 to convert mp3->wav, and delete the original mp3 """
    subprocess.run(["/usr/bin/mpg123", "-q", "-w", str(wav_path), str(mp3_path)])
    if delete:
        os.remove(str(mp3_path))


def tts_say(client, userdata, msg, voice="Raveena"):
    log(msg.topic + " " + str(msg.payload.decode()))
    data = json.loads(msg.payload.decode())

    sessionId = _random_id()  # We make a random one

    tmp_tts_dir = "/tmp/tts/"
    Path(tmp_tts_dir).mkdir(parents=True, exist_ok=True)

    common_filename = "{}-{}".format(voice, _hash(data["text"]))
    mp3_path = Path("{}{}.mp3".format(tmp_tts_dir, common_filename))
    wav_path = Path("{}{}.wav".format(tmp_tts_dir, common_filename))

    response = {}
    if not wav_path.is_file():
        log("No cached file found, querying polly.")

        response = aws_client.synthesize_speech(
            OutputFormat="mp3", Text=data["text"], VoiceId=voice
        )
        with mp3_path.open("wb") as mp3:
            mp3.write(response["AudioStream"].read())

        _convert_mp3_to_wav(mp3_path, wav_path)
    else:
        log("Using cached file: {}".format(wav_path))

    publish.single(
        "hermes/audioServer/default/playBytes/" + sessionId + "/",
        payload=wav_path.open("rb").read(),
        qos=0,
        retain=False,
        hostname=mqtt_host,
        port=mqtt_port,
        client_id="",
        keepalive=60,
        will=None,
        auth=None,
        tls=None,
        protocol=mqtt.MQTTv311,
    )

    # If 'data' contrains a sessionId the request came from a snips dialogue
    # so let it know we are done talking.
    if "sessionId" in data:
        publish.single(
            "hermes/tts/sayFinished",
            payload='{"siteId": "'
            + data["siteId"]
            + '", "sessionId": "'
            + data["sessionId"]
            + '", "id": "'
            + data["id"]
            + '"}',
            qos=0,
            retain=False,
            hostname=mqtt_host,
            port=mqtt_port,
            client_id="",
            keepalive=60,
            will=None,
            auth=None,
            tls=None,
            protocol=mqtt.MQTTv311,
        )


def playFinished(client, userdata, msg):
    log(msg.topic + " " + str(msg.payload.decode()))

# Read MQTT connection info from the central snips config.
config = toml.loads(open("/etc/snips.toml").read())

client = mqtt.Client()
client.on_connect = on_connect

client.message_callback_add("hermes/tts/say", tts_say)
client.message_callback_add("hermes/audioServer/default/playFinished", playFinished)

mqtt_host, mqtt_port = config["snips-common"]["mqtt"].split(":")
mqtt_port = int(mqtt_port)
client.connect(mqtt_host, mqtt_port, 60)

aws_client = boto3.client("polly")

client.loop_forever()
