# Piper voice attribution

The default voice is **en_GB-northern_english_male-medium** (British English, male, medium quality, 22,050 Hz).

- [Voice files and model card](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/northern_english_male/medium)
- The model card identifies [OpenSLR resource 83](https://www.openslr.org/83/) as the training dataset, licensed **Creative Commons Attribution-ShareAlike 4.0 International**.
- [CC BY-SA 4.0 license and conditions](https://creativecommons.org/licenses/by-sa/4.0/)
- The model card states it was fine-tuned from the U.S. English Lessac medium voice.

Preserve the source attribution and applicable license conditions when distributing voice files or derivatives. Voice files are downloaded separately, excluded from the Docker image and not included in source control. Check the model card and dataset license of any replacement voice; the TTS engine's license does not automatically cover every voice.

The installed [Piper engine](https://github.com/OHF-Voice/piper1-gpl) is **GPL-3.0**. Packaging or distributing this application with Piper must respect those license obligations. This project does not change or relicense Piper.
