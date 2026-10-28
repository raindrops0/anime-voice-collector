# anime-voice-collector: online demo

The files that run the online demo of [anime-voice-collector](https://github.com/raindrops0/anime-voice-collector): two short made-up Japanese episodes, already processed, that every visitor labels in their own copy. Adding episodes and exporting are turned off. This folder is made by [scripts/demo/make_deploy.py](https://github.com/raindrops0/anime-voice-collector/blob/main/scripts/demo/make_deploy.py); do not edit it by hand.

- `Dockerfile`: the server, without torch, for a host with 512 MB of memory.
- `template/`: the demo workspace.
- `wheels/`: avoc itself.

The server listens on the port in the `PORT` environment variable (8000 unless set).

## Credits

The voices were made with VOICEVOX: VOICEVOX:ずんだもん, VOICEVOX:四国めたん, VOICEVOX:九州そら, VOICEVOX:中国うさぎ, VOICEVOX:中部つるぎ ([terms](https://zunko.jp/con_ongen_kiyaku.html)). The script and the music were written for this demo.
