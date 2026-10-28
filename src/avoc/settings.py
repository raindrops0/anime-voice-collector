"""Model choices shared by processing and labeling."""

DEFAULT_MODELS = ("anime-va", "anime-char", "redimnet2-b6")
"""The three voiceprints work best together."""

GROUPING_MODEL = "anime-va"
"""The Groups view uses only this one model. Its threshold of 0.70 was measured. The joined
voiceprint was not measured."""
