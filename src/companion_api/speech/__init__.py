"""The speech preview for adult operators (doc/adr-0006-speech-preview-development.md).

The team's speech service (Dua-a_stt) runs on this machine or a private network. This package calls it for
pronunciation practice (`recitation`, `game`), push-to-talk questions (`routes`, transcription only) and Robert's
voice (`robert_voice`). Audio is held in memory for one request and never written, logged or cached; a transcript
is returned once and never kept. The release gate's `voice` switch stays false: none of this is for children
until the gate's voice items are green.
"""
