#!/usr/bin/env python3
import hashlib
import json
import os
import random
import string
import subprocess
from pathlib import Path

import boto3
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import toml


"""
This is a replacement for `snips-tts`, using the higher quality
AWS Polly service to produce audio from text.

It listens on the same MQTT topics as snips-tts. Both can run at the same time,
but it will cause duplicate audio output. Therefore stopping the existing
snips-tts service is probably best (`systemctl stop|disable snips-tts`).

Initially developed from jarvis_listener.py by @tschmidty69
https://github.com/tschmidty69/homeassistant-config/blob/master/shell_command/jarvis_listener.py
"""


def on_connect(client, userdata, flags, rc):
    print("MQTT connected")
    client.subscribe("hermes/tts/say")


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _random_id() -> str:
    return "".join(
        [random.choice(string.ascii_uppercase + string.digits) for i in range(16)]
    )


def _convert_mp3_to_wav(mp3_path: Path, wav_path: Path, delete: bool = True) -> None:
    """ Uses mpg123 to convert mp3->wav, and delete the original mp3 """
    subprocess.run(["/usr/bin/mpg123", "-q", "-w", str(wav_path), str(mp3_path)])
    if delete:
        os.remove(str(mp3_path))


def tts_say(client, userdata, msg, voice="Raveena") -> None:
    data = json.loads(msg.payload.decode())

    tmp_tts_dir = "/tmp/tts/"
    Path(tmp_tts_dir).mkdir(parents=True, exist_ok=True)

    common_filename = "{}-{}".format(voice, _hash(data["text"]))
    mp3_path = Path("{}{}.mp3".format(tmp_tts_dir, common_filename))
    wav_path = Path("{}{}.wav".format(tmp_tts_dir, common_filename))

    response = {}
    if not wav_path.is_file():
        print("Cached file not found, querying polly.")

        response = aws_client.synthesize_speech(
            OutputFormat="mp3", Text=data["text"], VoiceId=voice
        )
        with mp3_path.open("wb") as mp3:
            mp3.write(response["AudioStream"].read())

        _convert_mp3_to_wav(mp3_path, wav_path)
    else:
        print("Using cached file: {}".format(wav_path))

    msgs = [
        {
            "topic": "hermes/audioServer/default/playBytes/{}".format(_random_id()),
            "payload": wav_path.open("rb").read(),
        },
        {
            "topic": "hermes/tts/sayFinished",
            "payload": json.dumps({"id": data["id"], "sessionId": data["sessionId"]}),
        },
    ]

    publish.multiple(msgs, hostname=mqtt_host, port=mqtt_port)


# Read MQTT connection info from the central snips config.
snips_config = toml.loads(open("/etc/snips.toml").read())

client = mqtt.Client()
client.on_connect = on_connect

client.message_callback_add("hermes/tts/say", tts_say)

mqtt_host, mqtt_port = snips_config["snips-common"]["mqtt"].split(":")
mqtt_port = int(mqtt_port)
client.connect(mqtt_host, mqtt_port, 60)

aws_client = boto3.client("polly")  # assuming boto3 is configured

client.loop_forever()
