# snips-tts-polly

This is meant to be a replacement for `snips-tts` (the text-to-speech component of snips).
Rather than using the local `pico2wav`, it uses the higher quality AWS Polly service to
produce audio.

It listens to the same MQTT topics as `snips-tts`. Both can run at the same time, but it
will cause duplicate audio output. Therefore stopping the existing `snips-tts` service
makes sense.

```
# Disable snips-tts
systemctl disable snips-tts
systemctl stop snips-tts

# Enable snips-tts-polly
systemctl enable snips-tts-polly
systemctl start snips-tts-polly
```

If you want to switch back to classic `snips-tts`, just invert the commands.

Initially developed from `jarvis_listener.py` by @tschmidty69
https://github.com/tschmidty69/homeassistant-config/blob/master/shell_command/jarvis_listener.py
